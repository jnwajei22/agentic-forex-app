from fastapi import FastAPI, HTTPException
from app.api.routes.health import router as health_router
from app.api.routes.forex import router as forex_router
from app.api.routes.charts import router as charts_router
from app.api.routes.platform import router as platform_router
from app.webhooks.tradingview import router as tradingview_router
from app.mcp.server import mcp_app
from app.mcp.auth import MCPAuthMiddleware
from app.config.settings import settings
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.storage.brokers import BrokerStorageError

app = FastAPI(
    title="Agentic Forex Desk",
    version="0.1.0",
    lifespan=mcp_app.lifespan,
)
app.add_middleware(MCPAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(BrokerStorageError)
async def broker_storage_error_handler(request, exc: BrokerStorageError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_metadata() -> dict[str, object]:
    if settings.mcp_require_oauth and not settings.auth_issuer:
        raise HTTPException(
            status_code=503,
            detail=(
                "OAuth is required but AUTH_ISSUER is not configured. "
                "Set AUTH_ISSUER to the issuer URL of a real OIDC/OAuth provider."
            ),
        )
    return {
        "resource": "https://mcp.justinnwajei.com",
        "authorization_servers": [settings.auth_issuer] if settings.auth_issuer else [],
        "scopes_supported": ["forex:read", "forex:preview"],
    }

app.include_router(health_router)
app.include_router(charts_router)
app.include_router(forex_router)
app.include_router(platform_router)
app.include_router(tradingview_router, prefix="/webhooks", tags=["webhooks"])
app.mount("/mcp", mcp_app)
