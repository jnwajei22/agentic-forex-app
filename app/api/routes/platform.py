from typing import Any, Literal
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
from app.models.autonomous import ExecutionMode, ExecutionSettingsUpdate
from app.services.autonomous.execution import AutonomousDemoService, AutonomousExecutionError
from app.storage.execution import ExecutionRepository
from app.auth.identity import normalize_auth0_subject
from app.services.tradelocker.config_cache import tradelocker_config_cache


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
    environment: Literal["demo", "live"] | None = None
    connection_id: str | None = Field(default=None, validation_alias=AliasChoices("connection_id", "connectionId"))
    label: str | None = None
    create_new: bool = Field(default=False, validation_alias=AliasChoices("create_new", "createNew"))


class AccountSelection(BaseModel):
    account_id: str = Field(validation_alias=AliasChoices("account_id", "accountId"))
    account_number: str = Field(
        validation_alias=AliasChoices("account_number", "accountNumber", "accNum")
    )
    connection_id: str | None = Field(default=None, validation_alias=AliasChoices("connection_id", "connectionId"))


class AccountAliasUpdate(BaseModel):
    alias: str = Field(min_length=1, max_length=64)


class ExecutionProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    account_id: str = Field(validation_alias=AliasChoices("account_id", "accountId"))
    strategy_template_id: str = "strategy_hourly_forex_v1"
    execution_mode: Literal["read_only", "demo_enabled", "disabled"] = "read_only"
    risk: dict[str, Any] = Field(default_factory=dict)
    allowed_instruments: list[str] = Field(default_factory=list)
    session_rules: dict[str, Any] = Field(default_factory=dict)
    news_filter_enabled: bool = True


class ExecutionProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    execution_mode: Literal["read_only", "demo_enabled", "disabled"] | None = None
    enabled: bool | None = None


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
    repo.sync_accounts(user_sub, connection.connection_ref, discovered)
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
            environment=connection.environment,
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
            discovered = await client.get_accounts()
    except TradeLockerError as exc:
        return _discovery_error_response(exc, request_id, "save_credentials")
    repo = repository()
    connection = repo.save_connection(
        claims["sub"], base_url=payload.base_url, username=payload.username,
        password=payload.password, server=payload.server, environment=payload.environment,
        email=claims.get("email"), connection_ref=payload.connection_id,
        label=payload.label, create_new=payload.create_new,
    )
    repo.sync_accounts(claims["sub"], connection.connection_ref, discovered)
    tradelocker_config_cache.invalidate_user(claims["sub"])
    return TradeLockerOnboardingStatus(
        status=TradeLockerConnectionStatus.CONNECTED_NO_ACCOUNT,
        connected=True,
    ).model_dump(mode="json")


@router.post("/broker/tradelocker/discover-accounts")
async def discover_accounts(connection_id: str | None = None, claims: dict = Depends(current_claims)):
    repo = repository()
    connection = repo.get_connection(claims["sub"], connection_id)
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
            discovered = await client.get_accounts()
            repo.sync_accounts(claims["sub"], connection.connection_ref, discovered)
            # Legacy onboarding still needs the broker pair for its immediate selection POST.
            # Durable account listings use /api/broker/accounts and expose only safe IDs.
            return discovered
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
        claims["sub"], payload.account_id, payload.account_number, payload.connection_id
    ):
        return TradeLockerOnboardingStatus(
            status=TradeLockerConnectionStatus.NOT_CONNECTED,
            connected=False,
        ).model_dump(mode="json")
    tradelocker_config_cache.invalidate_user(claims["sub"])
    connection = repository().get_connection(claims["sub"])
    return TradeLockerOnboardingStatus(
        status=TradeLockerConnectionStatus.READY,
        connected=True,
        selected_account=SelectedTradeLockerAccount(
            account_id=payload.account_id,
            account_number=payload.account_number,
            server=connection.server if connection else "TradeLocker",
            environment=connection.environment if connection else None,
        ),
    ).model_dump(mode="json")


@router.delete("/broker/tradelocker")
async def delete_broker(claims: dict = Depends(current_claims)) -> dict:
    repository().delete_connection(claims["sub"])
    tradelocker_config_cache.invalidate_user(claims["sub"])
    return {"status": "deleted", "provider": "tradelocker"}


@router.get("/broker/connections")
async def list_connections(claims: dict = Depends(current_claims)) -> dict:
    return {"connections": repository().list_connections(claims["sub"])}


@router.get("/broker/accounts")
async def list_accounts(claims: dict = Depends(current_claims)) -> dict:
    return {"accounts": repository().list_accounts(claims["sub"])}


@router.put("/broker/accounts/{account_id}/alias")
async def rename_account(account_id: str, payload: AccountAliasUpdate, claims: dict = Depends(current_claims)) -> dict:
    try:
        changed = repository().rename_account(claims["sub"], account_id, payload.alias)
    except BrokerStorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if not changed: raise HTTPException(status_code=404, detail="Account not found.")
    return {"status": "updated", "account_id": account_id}


@router.put("/broker/accounts/{account_id}/default")
async def default_account(account_id: str, claims: dict = Depends(current_claims)) -> dict:
    if not repository().set_default_account(claims["sub"], account_id):
        raise HTTPException(status_code=404, detail="Account not found.")
    tradelocker_config_cache.invalidate_user(claims["sub"])
    return {"status": "updated", "account_id": account_id}


@router.put("/broker/accounts/{account_id}/disable")
async def disable_account(account_id: str, claims: dict = Depends(current_claims)) -> dict:
    if not repository().set_account_enabled(claims["sub"], account_id, False):
        raise HTTPException(status_code=404, detail="Account not found.")
    tradelocker_config_cache.invalidate_user(claims["sub"])
    return {"status": "disabled", "account_id": account_id}


@router.put("/broker/connections/{connection_id}/disable")
async def disable_connection(connection_id: str, claims: dict = Depends(current_claims)) -> dict:
    if not repository().disable_connection(claims["sub"], connection_id):
        raise HTTPException(status_code=404, detail="Connection not found.")
    tradelocker_config_cache.invalidate_user(claims["sub"])
    return {"status": "disabled", "connection_id": connection_id}


@router.get("/execution-profiles")
async def list_execution_profiles(claims: dict = Depends(current_claims)) -> dict:
    return {"profiles": repository().list_profiles(claims["sub"])}


@router.post("/execution-profiles", status_code=201)
async def create_execution_profile(payload: ExecutionProfileCreate, claims: dict = Depends(current_claims)) -> dict:
    try:
        return repository().create_profile(claims["sub"], name=payload.name, account_ref=payload.account_id,
            strategy_template_id=payload.strategy_template_id, execution_mode=payload.execution_mode,
            risk=payload.risk, allowed_instruments=payload.allowed_instruments,
            session_rules=payload.session_rules, news_filter_enabled=payload.news_filter_enabled)
    except BrokerStorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.put("/execution-profiles/{profile_id}")
async def update_execution_profile(profile_id: str, payload: ExecutionProfileUpdate, claims: dict = Depends(current_claims)) -> dict:
    try:
        changed = repository().update_profile(claims["sub"], profile_id, name=payload.name,
            execution_mode=payload.execution_mode, enabled=payload.enabled)
    except BrokerStorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if not changed: raise HTTPException(status_code=404, detail="Profile not found.")
    return {"status":"updated","profile_id":profile_id}


@router.delete("/execution-profiles/{profile_id}")
async def delete_execution_profile(profile_id: str, claims: dict = Depends(current_claims)) -> dict:
    if not repository().delete_profile(claims["sub"],profile_id):
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {"status":"deleted","profile_id":profile_id}


@router.get("/broker/tradelocker/execution-settings")
async def get_execution_settings(claims: dict = Depends(current_claims)) -> dict:
    connection = repository().get_connection(claims["sub"])
    if not connection or not connection.account_id or not connection.account_number:
        raise HTTPException(status_code=409, detail="Select a TradeLocker account first.")
    value = ExecutionRepository().get_or_create_settings(
        claims["sub"], connection.connection_id, connection.account_id, connection.account_number
    )
    return {
        "execution_mode": value["execution_mode"], "account_id": connection.account_id,
        "acc_num": connection.account_number, "environment": connection.environment,
        "strategy_name": value["strategy_name"], "strategy_version": value["strategy_version"],
    }


@router.put("/broker/tradelocker/execution-settings")
async def update_execution_settings(
    payload: ExecutionSettingsUpdate, claims: dict = Depends(current_claims)
) -> dict:
    try:
        context = await AutonomousDemoService().context(claims["sub"], require_mode=False)
    except AutonomousExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    value = ExecutionRepository().set_mode(
        claims["sub"], context.connection_id, context.account_id, context.acc_num,
        payload.execution_mode,
    )
    logger.info(
        "TradeLocker execution_mode_changed user_id=%s connection_id=%s account_id=%s acc_num=%s environment=demo mode=%s",
        claims["sub"], context.connection_id, context.account_id, context.acc_num,
        payload.execution_mode.value,
    )
    return {"status": "updated", "execution_mode": value["execution_mode"], "environment": "demo"}
