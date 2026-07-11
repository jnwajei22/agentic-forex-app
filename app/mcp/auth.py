import hmac
import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config.settings import settings


logger = logging.getLogger(__name__)
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _is_local_development_request(scope: Scope) -> bool:
    client = scope.get("client")
    client_host = client[0].lower() if client else ""
    host = (_header(scope, b"host") or "").lower()
    host_is_local = (
        host == "localhost"
        or host.startswith("localhost:")
        or host == "127.0.0.1"
        or host.startswith("127.0.0.1:")
        or host == "::1"
        or host.startswith("[::1]")
    )
    return settings.app_env == "development" and client_host in LOCAL_HOSTS and host_is_local


class MCPAuthMiddleware:
    """Protect only the remote MCP transport with bearer authentication."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        if not settings.mcp_shared_secret and settings.app_env == "development":
            logger.warning(
                "MCP authentication is disabled for localhost development access only."
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("path") == "/mcp" or scope.get("path", "").startswith("/mcp/")
        ):
            await self.app(scope, receive, send)
            return

        secret = settings.mcp_shared_secret
        if not secret:
            if _is_local_development_request(scope):
                await self.app(scope, receive, send)
                return
            await JSONResponse(
                {"detail": "MCP authentication is not configured."}, status_code=503
            )(scope, receive, send)
            return

        authorization = _header(scope, b"authorization")
        scheme, separator, token = (authorization or "").partition(" ")
        if (
            not separator
            or scheme.lower() != "bearer"
            or not hmac.compare_digest(token, secret)
        ):
            await JSONResponse(
                {"detail": "Invalid or missing MCP bearer token."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)
