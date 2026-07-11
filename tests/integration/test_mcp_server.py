from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.brokers.tradelocker.adapter import TradeLockerAdapter
from app.brokers.tradelocker.client import TradeLockerError
from app.config.settings import settings
from app.main import app
from app.mcp import tools
from app.mcp import auth
from app.mcp.server import mcp


EXPECTED_TOOLS = {
    "get_forex_watchlist",
    "scan_forex_watchlist",
    "generate_chart",
    "review_forex_order",
    "get_account_status",
    "get_open_positions",
    "get_trade_log",
    "get_tradelocker_accounts",
    "get_tradelocker_config",
    "get_tradelocker_symbols",
    "get_tradelocker_quote",
    "get_tradelocker_candles",
}
INITIALIZE_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1.0"},
    },
}
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _enable_test_oauth(monkeypatch, scopes="forex:read forex:preview"):
    monkeypatch.setattr(settings, "mcp_require_oauth", True)
    monkeypatch.setattr(auth, "_verify_access_token", lambda token: {"scope": scopes})


def test_missing_auth_issuer_is_invalid_when_oauth_is_required(monkeypatch):
    monkeypatch.setattr(settings, "mcp_require_oauth", True)
    monkeypatch.setattr(settings, "auth_issuer", None)
    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 503
    assert "AUTH_ISSUER is not configured" in response.json()["detail"]
    assert "authorization_servers" not in response.json()


def test_protected_resource_metadata_contains_oauth_configuration(monkeypatch):
    monkeypatch.setattr(settings, "mcp_require_oauth", True)
    monkeypatch.setattr(settings, "auth_issuer", "https://tenant.auth0.com/")
    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    assert response.json() == {
        "resource": "https://mcp.justinnwajei.com",
        "authorization_servers": ["https://tenant.auth0.com/"],
        "scopes_supported": ["forex:read", "forex:preview"],
    }


def test_mcp_endpoint_initializes_and_advertises_tools(monkeypatch):
    _enable_test_oauth(monkeypatch)
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post(
            "/mcp",
            json=INITIALIZE_PAYLOAD,
            headers={**MCP_HEADERS, "Authorization": "Bearer valid-jwt"},
        )
        tool_response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={**MCP_HEADERS, "Authorization": "Bearer valid-jwt"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"tools":{"listChanged":true}' in response.text
    assert '"name":"Agentic Forex Desk"' in response.text
    assert tool_response.status_code == 200
    assert '"name":"get_tradelocker_accounts"' in tool_response.text
    for tool_name in EXPECTED_TOOLS:
        assert f'"name":"{tool_name}"' in tool_response.text


def test_mcp_missing_token_returns_oauth_challenge(monkeypatch):
    monkeypatch.setattr(settings, "mcp_require_oauth", True)
    with TestClient(app) as client:
        response = client.post("/mcp", json=INITIALIZE_PAYLOAD, headers=MCP_HEADERS)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        'Bearer resource_metadata="https://mcp.justinnwajei.com/'
        '.well-known/oauth-protected-resource"'
    )


def test_mcp_invalid_auth_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "mcp_require_oauth", True)
    monkeypatch.setattr(
        auth,
        "_verify_access_token",
        lambda token: (_ for _ in ()).throw(auth.jwt.InvalidTokenError()),
    )
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=INITIALIZE_PAYLOAD,
            headers={**MCP_HEADERS, "Authorization": "Bearer wrong-secret"},
        )

    assert response.status_code == 401


def test_mcp_valid_jwt_is_accepted(monkeypatch):
    _enable_test_oauth(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=INITIALIZE_PAYLOAD,
            headers={**MCP_HEADERS, "Authorization": "Bearer valid-jwt"},
        )

    assert response.status_code == 200
    assert '"name":"Agentic Forex Desk"' in response.text


def test_jwt_verification_checks_signature_issuer_audience_and_expiry(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://tenant.auth0.com/"
    audience = "https://mcp.justinnwajei.com"
    monkeypatch.setattr(settings, "auth_issuer", issuer)
    monkeypatch.setattr(settings, "auth_audience", audience)
    monkeypatch.setattr(settings, "auth_jwks_url", "https://tenant.auth0.com/.well-known/jwks.json")
    monkeypatch.setitem(
        auth._jwks_clients,
        settings.auth_jwks_url,
        SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(
                key=private_key.public_key()
            )
        ),
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "exp": now + timedelta(minutes=5),
            "scope": "forex:read",
        },
        private_key,
        algorithm="RS256",
    )

    assert auth._verify_access_token(token)["scope"] == "forex:read"

    expired = jwt.encode(
        {"iss": issuer, "aud": audience, "exp": now - timedelta(minutes=1)},
        private_key,
        algorithm="RS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        auth._verify_access_token(expired)


def test_public_no_auth_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "mcp_require_oauth", True)
    monkeypatch.setattr(settings, "mcp_allow_public_no_auth", False)
    with TestClient(app, base_url="https://public.example") as client:
        response = client.post("/mcp", json=INITIALIZE_PAYLOAD, headers=MCP_HEADERS)

    assert response.status_code == 401


def test_insufficient_scope_is_rejected(monkeypatch):
    _enable_test_oauth(monkeypatch, scopes="forex:read")
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "review_forex_order", "arguments": {}},
            },
            headers={**MCP_HEADERS, "Authorization": "Bearer read-only-jwt"},
        )

    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]
    assert 'scope="forex:preview"' in response.headers["www-authenticate"]


def test_shared_secret_remains_available_for_explicit_manual_mode(monkeypatch):
    monkeypatch.setattr(settings, "mcp_require_oauth", False)
    monkeypatch.setattr(settings, "mcp_shared_secret", "test-mcp-secret")
    monkeypatch.setattr(settings, "mcp_allow_public_no_auth", False)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=INITIALIZE_PAYLOAD,
            headers={**MCP_HEADERS, "Authorization": "Bearer test-mcp-secret"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_mcp_server_registers_expected_tools():
    listed_tools = await mcp.list_tools()
    registered = {tool.name for tool in listed_tools}
    assert registered == EXPECTED_TOOLS
    discovery = next(tool for tool in listed_tools if tool.name == "get_tradelocker_accounts")
    assert "Run this first" in discovery.description
    assert "TRADELOCKER_ACCOUNT_ID" in discovery.description
    assert "restart the server" in discovery.description


@pytest.mark.asyncio
async def test_mcp_account_discovery_tool_returns_client_result(monkeypatch):
    result = {"accounts": [{"accountId": 12345, "accNum": 2}]}
    client = SimpleNamespace(get_accounts=AsyncMock(return_value=result))
    monkeypatch.setattr(
        tools,
        "get_tradelocker_adapter",
        lambda: SimpleNamespace(client=client),
    )

    assert await tools.get_tradelocker_accounts() == result
    client.get_accounts.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_mcp_account_discovery_tool_rejects_missing_login_config(monkeypatch):
    client = SimpleNamespace(
        get_accounts=AsyncMock(
            side_effect=TradeLockerError(
                "get_accounts",
                "TradeLocker login configuration is incomplete: TRADELOCKER_PASSWORD.",
                code="not_configured",
            )
        )
    )
    monkeypatch.setattr(
        tools,
        "get_tradelocker_adapter",
        lambda: SimpleNamespace(client=client),
    )

    result = await tools.get_tradelocker_accounts()

    assert result["status"] == "error"
    assert result["error"] == "not_configured"
    assert "TRADELOCKER_PASSWORD" in result["message"]


@pytest.mark.asyncio
async def test_mcp_watchlist_and_scan_are_usable_and_ranked(monkeypatch):
    monkeypatch.setattr(settings, "market_data_provider", "mock")
    watchlist = tools.get_forex_watchlist()
    results = await tools.scan_forex_watchlist(["1h"], "default", 5)

    assert watchlist
    assert watchlist[0]["pair"] == "EUR/USD"
    assert results
    assert [result["score"] for result in results] == sorted(
        [result["score"] for result in results], reverse=True
    )
    assert len(results) <= 5


def test_mcp_order_review_is_rejected_without_live_submission(monkeypatch):
    submit_order = AsyncMock(side_effect=AssertionError("TradeLocker invoked"))
    monkeypatch.setattr(TradeLockerAdapter, "submit_order", submit_order)
    monkeypatch.setattr(settings, "kill_switch_enabled", True)

    preview = tools.review_forex_order(
        {
            "pair": "EUR/USD",
            "side": "long",
            "entry": 1.1000,
            "stop_loss": 1.0950,
            "take_profit": 1.1100,
            "risk_percent": 0.5,
        }
    )

    assert preview["status"] == "rejected"
    assert "Kill switch is enabled." in preview["violations"]
    submit_order.assert_not_awaited()


def test_remote_mcp_cannot_disable_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "kill_switch_enabled", True)
    result = tools.set_kill_switch(False, "remote request")

    assert result["changed"] is False
    assert result["kill_switch_enabled"] is True
    assert settings.kill_switch_enabled is True
