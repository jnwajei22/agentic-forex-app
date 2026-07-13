from typing import Any
import logging
import uuid

import anyio
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, Field

from app.brokers.tradelocker.client import TradeLockerClient, TradeLockerError
from app.config.settings import settings
from app.storage.brokers import BrokerRepository, BrokerStorageError
from app.models.onboarding import (
    SelectedTradeLockerAccount,
    TradeLockerConnectionStatus,
    TradeLockerOnboardingStatus,
)
from app.auth.identity import normalize_auth0_subject


router = APIRouter(prefix="/api", tags=["platform"])
logger = logging.getLogger(__name__)


class TradeLockerCredentials(BaseModel):
    base_url: str = Field(
        default_factory=lambda: settings.tradelocker_base_url,
        validation_alias=AliasChoices("base_url", "baseUrl"),
    )
    username: str
    password: str = Field(repr=False)
    server: str


class AccountSelection(BaseModel):
    account_id: str = Field(validation_alias=AliasChoices("account_id", "accountId"))
    account_number: str = Field(
        validation_alias=AliasChoices("account_number", "accountNumber", "accNum")
    )


async def current_claims(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    scheme, separator, token = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="OAuth access token is required.")
    from app.mcp.auth import _verify_access_token

    try:
        claims = await anyio.to_thread.run_sync(_verify_access_token, token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid OAuth access token.") from None
    try:
        claims["sub"] = normalize_auth0_subject(claims.get("sub"))
    except ValueError:
        raise HTTPException(status_code=401, detail="OAuth subject claim is required.")
    return claims


def repository() -> BrokerRepository:
    try:
        return BrokerRepository()
    except BrokerStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.get("/me")
async def me(claims: dict = Depends(current_claims)) -> dict:
    repository().ensure_user(claims["sub"], claims.get("email"))
    return {"sub": claims["sub"], "email": claims.get("email")}


@router.get("/broker/status")
async def broker_status(claims: dict = Depends(current_claims)) -> dict:
    return (await validated_onboarding_status(claims["sub"])).model_dump(mode="json")


@router.post("/broker/onboarding-status")
async def onboarding_status(claims: dict = Depends(current_claims)) -> dict:
    return (await validated_onboarding_status(claims["sub"])).model_dump(mode="json")


async def validated_onboarding_status(user_sub: str) -> TradeLockerOnboardingStatus:
    repo = repository()
    connection = repo.get_connection(user_sub)
    if connection is None:
        return TradeLockerOnboardingStatus(
            status=TradeLockerConnectionStatus.NOT_CONNECTED,
            connected=False,
        )
    try:
        async with TradeLockerClient(
            base_url=connection.base_url, username=connection.username,
            password=connection.password, server=connection.server,
            account_id=None, account_number=None,
        ) as client:
            discovered = await client.get_accounts()
    except TradeLockerError as exc:
        expired = exc.code in {"expired", "token_expired", "session_expired"}
        rejected = exc.status_code in {400, 401, 403} or exc.code in {
            "unauthorized", "invalid_credentials", "authentication_failed"
        }
        if expired or rejected:
            return TradeLockerOnboardingStatus(
                status=(TradeLockerConnectionStatus.EXPIRED if expired
                        else TradeLockerConnectionStatus.INVALID_CREDENTIALS),
                connected=False,
                message="Reconnect TradeLocker credentials to continue.",
            )
        logger.warning(
            "TradeLocker route=onboarding_status response_status=%s safe_code=%s",
            exc.status_code, exc.code,
        )
        return TradeLockerOnboardingStatus(
            status=TradeLockerConnectionStatus.UNAVAILABLE,
            connected=False,
            message="TradeLocker connection status is temporarily unavailable.",
            retryable=True,
        )
    if not connection.account_id or not connection.account_number:
        return TradeLockerOnboardingStatus(
            status=TradeLockerConnectionStatus.CONNECTED_NO_ACCOUNT,
            connected=True,
        )
    accounts = discovered.get("accounts", []) if isinstance(discovered, dict) else []
    selected_exists = any(
        str(account.get("accountId")) == connection.account_id
        and str(account.get("accNum")) == connection.account_number
        for account in accounts if isinstance(account, dict)
    )
    if not selected_exists:
        return TradeLockerOnboardingStatus(
            status=TradeLockerConnectionStatus.CONNECTED_NO_ACCOUNT,
            connected=True,
        )
    return TradeLockerOnboardingStatus(
        status=TradeLockerConnectionStatus.READY,
        connected=True,
        selected_account=SelectedTradeLockerAccount(
            account_id=connection.account_id,
            account_number=connection.account_number,
            server=connection.server,
        ),
    )


@router.post("/broker/tradelocker/save-credentials")
async def save_credentials(
    payload: TradeLockerCredentials, claims: dict = Depends(current_claims)
):
    request_id = uuid.uuid4().hex
    try:
        async with TradeLockerClient(
            base_url=payload.base_url, username=payload.username,
            password=payload.password, server=payload.server,
            account_id=None, account_number=None,
        ) as client:
            await client.get_accounts()
    except TradeLockerError as exc:
        return _discovery_error_response(exc, request_id, "save_credentials")
    repository().save_connection(
        claims["sub"], base_url=payload.base_url, username=payload.username,
        password=payload.password, server=payload.server, email=claims.get("email"),
    )
    return TradeLockerOnboardingStatus(
        status=TradeLockerConnectionStatus.CONNECTED_NO_ACCOUNT,
        connected=True,
    ).model_dump(mode="json")


@router.post("/broker/tradelocker/discover-accounts")
async def discover_accounts(claims: dict = Depends(current_claims)):
    connection = repository().get_connection(claims["sub"])
    if connection is None:
        return TradeLockerOnboardingStatus(
            status=TradeLockerConnectionStatus.NOT_CONNECTED,
            connected=False,
        ).model_dump(mode="json")
    try:
        async with TradeLockerClient(
            base_url=connection.base_url, username=connection.username,
            password=connection.password, server=connection.server,
            account_id=None, account_number=None,
        ) as client:
            return await client.get_accounts()
    except TradeLockerError as exc:
        return _discovery_error_response(
            exc, uuid.uuid4().hex, "discover_accounts"
        )


def _discovery_error_response(
    exc: TradeLockerError, request_id: str, route_name: str
) -> JSONResponse:
    rejected = exc.status_code in {400, 401, 403}
    status_code = 401 if rejected else 502
    error = (
        "tradelocker_credentials_rejected"
        if rejected
        else "tradelocker_account_discovery_failed"
    )
    message = (
        "TradeLocker rejected the credentials or server selection."
        if rejected
        else "Unable to retrieve TradeLocker accounts."
    )
    logger.warning(
        "TradeLocker route=%s response_status=%s safe_code=%s request_id=%s",
        route_name, exc.status_code, exc.code, request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "message": message,
            "status": status_code,
            "request_id": request_id,
        },
    )


@router.post("/broker/tradelocker/select-account")
async def select_account(
    payload: AccountSelection, claims: dict = Depends(current_claims)
) -> dict:
    if not repository().select_account(
        claims["sub"], payload.account_id, payload.account_number
    ):
        return TradeLockerOnboardingStatus(
            status=TradeLockerConnectionStatus.NOT_CONNECTED,
            connected=False,
        ).model_dump(mode="json")
    connection = repository().get_connection(claims["sub"])
    return TradeLockerOnboardingStatus(
        status=TradeLockerConnectionStatus.READY,
        connected=True,
        selected_account=SelectedTradeLockerAccount(
            account_id=payload.account_id,
            account_number=payload.account_number,
            server=connection.server if connection else "TradeLocker",
        ),
    ).model_dump(mode="json")


@router.delete("/broker/tradelocker")
async def delete_broker(claims: dict = Depends(current_claims)) -> dict:
    repository().delete_connection(claims["sub"])
    return {"status": "deleted", "provider": "tradelocker"}
