from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.api.routes.platform import current_claims, validated_onboarding_status
from app.config.settings import settings
from app.storage.oauth import OAuthRepository, OAuthStorageError
from app.oauth.cimd import CIMDError, cimd_loader


router = APIRouter(tags=["oauth"])
ALLOWED_CALLBACK_ORIGINS = {"https://chatgpt.com", "https://chat.openai.com"}
ALLOWED_SCOPES = {"openid", "profile", "email", "forex:read", "forex:preview"}


def oauth_repository() -> OAuthRepository:
    try:
        return OAuthRepository()
    except OAuthStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


def _validate_callback(value: str) -> str:
    parsed = urlparse(value)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if parsed.scheme != "https" or origin not in ALLOWED_CALLBACK_ORIGINS:
        raise HTTPException(status_code=400, detail="OAuth callback URL is not allowed.")
    return value


@router.get("/oauth/authorize")
async def authorize(
    client_id: str, redirect_uri: str, response_type: str, state: str,
    code_challenge: str, code_challenge_method: str, scope: str = "forex:read",
    nonce: str | None = None, resource: str | None = None,
) -> RedirectResponse:
    if (not client_id or not state or response_type != "code"
            or code_challenge_method != "S256" or not 43 <= len(code_challenge) <= 128):
        raise HTTPException(status_code=400, detail="Authorization code flow with PKCE S256 is required.")
    configured_clients = {item.strip() for item in (settings.oauth_allowed_client_ids or "").split(",") if item.strip()}
    if client_id.startswith(("https://", "http://")):
        try:
            client_metadata = await cimd_loader.load(client_id)
        except CIMDError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        client_id = client_metadata.client_id
        if redirect_uri not in client_metadata.redirect_uris:
            raise HTTPException(status_code=400, detail="OAuth redirect URI is not registered in the CIMD document.")
    elif client_id not in configured_clients:
        raise HTTPException(status_code=400, detail="Static OAuth client is not allowed.")
    requested_scopes = set(scope.split())
    if not requested_scopes or not requested_scopes <= ALLOWED_SCOPES:
        raise HTTPException(status_code=400, detail="Unsupported OAuth scope.")
    callback = _validate_callback(redirect_uri)
    expected_resource = settings.public_base_url.rstrip("/")
    if resource != expected_resource:
        raise HTTPException(status_code=400, detail="OAuth resource is missing or invalid.")
    reference = oauth_repository().create_transaction(
        client_id=client_id, redirect_uri=callback, state=state, scope=scope,
        code_challenge=code_challenge, code_challenge_method=code_challenge_method,
        resource=expected_resource, nonce=nonce,
    )
    frontend = settings.frontend_origin.rstrip("/")
    return RedirectResponse(f"{frontend}/oauth/start?{urlencode({'transaction': reference})}", status_code=302)


class TransactionRequest(BaseModel):
    transaction: str


class CompletionRequest(TransactionRequest):
    csrf_token: str


@router.post("/api/oauth/onboarding/bind")
async def bind_transaction(payload: TransactionRequest, claims: dict = Depends(current_claims)) -> dict:
    transaction = oauth_repository().bind_user(payload.transaction, claims["sub"])
    if transaction is None:
        raise HTTPException(status_code=403, detail="The onboarding transaction is invalid, expired, or belongs to another user.")
    return {"status": "bound"}


@router.post("/api/oauth/onboarding/status")
async def oauth_onboarding_status(payload: TransactionRequest, claims: dict = Depends(current_claims)) -> dict:
    transaction = oauth_repository().get_transaction(payload.transaction)
    if transaction is None:
        raise HTTPException(status_code=410, detail="The ChatGPT sign-in request expired. Restart sign-in from ChatGPT.")
    if transaction.user_sub != claims["sub"]:
        raise HTTPException(status_code=403, detail="This onboarding transaction belongs to another user.")
    status = await validated_onboarding_status(claims["sub"])
    return {**status.model_dump(mode="json"), "transaction_valid": True,
            "csrf_token": transaction.csrf_token}


@router.post("/api/oauth/onboarding/complete")
async def complete_authorization(payload: CompletionRequest, claims: dict = Depends(current_claims)) -> dict:
    repo = oauth_repository()
    transaction = repo.get_transaction(payload.transaction)
    if transaction is None:
        raise HTTPException(status_code=410, detail="The ChatGPT sign-in request expired. Restart sign-in from ChatGPT.")
    if transaction.user_sub != claims["sub"]:
        raise HTTPException(status_code=403, detail="This onboarding transaction belongs to another user.")
    if payload.csrf_token != transaction.csrf_token:
        raise HTTPException(status_code=403, detail="Invalid onboarding request.")
    status = await validated_onboarding_status(claims["sub"])
    if status.status != "ready":
        raise HTTPException(status_code=409, detail="A valid TradeLocker account must be selected before authorization.")
    issued = repo.issue_code(payload.transaction, claims["sub"])
    if issued is None:
        raise HTTPException(status_code=409, detail="The authorization request could not be completed.")
    code, original = issued
    separator = "&" if "?" in original.redirect_uri else "?"
    callback_url = f"{original.redirect_uri}{separator}{urlencode({'code': code, 'state': original.state})}"
    return {"redirect_url": callback_url}


@router.post("/oauth/token")
async def exchange_token(request: Request) -> JSONResponse:
    form = {key: values[-1] for key, values in parse_qs((await request.body()).decode()).items()}
    if form.get("grant_type") != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    result = oauth_repository().exchange_code(
        code=form.get("code", ""), client_id=form.get("client_id", ""),
        redirect_uri=form.get("redirect_uri", ""), code_verifier=form.get("code_verifier", ""),
        resource=form.get("resource", ""),
    )
    if result is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    return JSONResponse(result, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
