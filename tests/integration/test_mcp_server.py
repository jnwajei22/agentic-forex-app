from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from app.models.market import Candle
from app.mcp import tools
from app.mcp import auth
from app.mcp.server import mcp
from app.services.charting import generator


EXPECTED_TOOLS = {
    "get_forex_watchlist",
    "scan_forex_watchlist",
    "get_forex_chart_data",
    "generate_static_forex_chart",
    "generate_chart",
    "analyze_multi_timeframe",
    "generate_multi_timeframe_report",
    "review_forex_order",
    "get_account_status",
    "get_open_positions",
    "get_trade_log",
    "get_tradelocker_connection_status",
    "get_my_broker_connection_status",
    "get_my_tradelocker_accounts",
    "get_my_tradelocker_account_status",
    "get_my_tradelocker_symbols",
    "get_my_tradelocker_quote",
    "get_my_tradelocker_candles",
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
    monkeypatch.setattr(
        auth, "_verify_access_token", lambda token: {"sub": "auth0|test", "scope": scopes}
    )


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
        "authorization_servers": ["https://mcp.justinnwajei.com"],
        "scopes_supported": ["forex:read", "forex:preview"],
    }


def test_authorization_server_metadata_uses_agentic_forex_oauth_endpoints(monkeypatch):
    monkeypatch.setattr(settings, "auth_issuer", "https://tenant.auth0.com/")
    monkeypatch.setattr(settings, "auth_jwks_url", "https://tenant.auth0.com/.well-known/jwks.json")
    monkeypatch.setattr(settings, "oauth_authorization_url", "https://app.example.test/oauth/authorize")
    monkeypatch.setattr(settings, "oauth_token_url", None)
    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["authorization_endpoint"] == "https://app.example.test/oauth/authorize"
    assert metadata["token_endpoint"] == "https://mcp.justinnwajei.com/oauth/token"
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert metadata["client_id_metadata_document_supported"] is True
    assert "registration_endpoint" not in metadata


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
    assert "get_tradelocker_connection_status" in registered


@pytest.mark.asyncio
async def test_chart_data_tool_schema_and_scope_are_complete():
    chart_tool = next(tool for tool in await mcp.list_tools() if tool.name == "get_forex_chart_data")
    assert set(chart_tool.parameters["properties"]) == {
        "pair", "timeframe", "lookback", "start_time", "end_time", "overlays",
        "entry", "stop_loss", "take_profit", "max_points", "include_candles",
        "include_indicator_series",
    }
    assert auth.TOOL_SCOPES["get_forex_chart_data"] == "forex:read"
    assert "not an image" in chart_tool.description
    assert "override lookback" in chart_tool.description


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
    assert results["results"]
    assert [result["score"] for result in results["results"]] == sorted(
        [result["score"] for result in results["results"]], reverse=True
    )
    assert len(results["results"]) <= 5
    assert results["strongest_pairs"]
    assert "spread_warning" in results["results"][0]


@pytest.mark.asyncio
async def test_mcp_scan_reports_missing_timeframe_data(monkeypatch):
    async def no_candles(pair, timeframe, lookback):
        return []

    monkeypatch.setattr(tools, "get_candles", no_candles)

    report = await tools.scan_forex_watchlist(["15m"], max_results=5)

    assert report["results"] == []
    assert report["warnings"]
    assert all("Missing data" in warning for warning in report["warnings"])
    assert "No trade / no clean setup" in report["summary"]


@pytest.mark.asyncio
async def test_mcp_generate_chart_compatibility_returns_public_url_without_local_path(tmp_path, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(
            timestamp=start + timedelta(hours=index),
            open=1.1 + index * 0.0001,
            high=1.101 + index * 0.0001,
            low=1.099 + index * 0.0001,
            close=1.1005 + index * 0.0001,
        )
        for index in range(60)
    ]

    from app.services.charting import data as chart_data_service
    from app.services.market_data.history import PaginatedCandleResult

    async def history_source(**kwargs):
        return PaginatedCandleResult(
            instrument_id="77", timeframe="1H",
            requested_start_ms=candles[0].timestamp,
            requested_end_ms=candles[-1].timestamp,
            estimated_candles=len(candles), candles=candles,
            batches_requested=1, complete=True, stop_reason="range_covered",
        )

    async def spread_source(pair):
        return 0.0001

    monkeypatch.setattr(chart_data_service, "get_candle_history", history_source)
    monkeypatch.setattr(chart_data_service, "get_spread", spread_source)
    monkeypatch.setattr(settings, "market_data_provider", "mock")
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    monkeypatch.setattr(settings, "public_base_url", "https://charts.example.test")

    result = await tools.generate_chart("EUR/USD", "1h")

    assert result.keys() >= {
        "chart_id",
        "public_chart_url",
        "pair",
        "timeframe",
        "trend",
        "generated_at",
        "summary",
    }
    assert result["public_chart_url"] == (
        f"https://charts.example.test/charts/{result['chart_id']}.png"
    )
    assert "local_path" not in result and "path" not in result


@pytest.mark.asyncio
async def test_mcp_chart_data_serializes_same_object_used_by_static_renderer(tmp_path, monkeypatch):
    from app.services.charting.data import build_chart_data

    monkeypatch.setattr(settings, "market_data_provider", "mock")
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    chart_data = await build_chart_data(pair="EUR/USD", timeframe="1H")

    async def chart_source(**kwargs):
        return chart_data

    monkeypatch.setattr(tools, "build_chart_data", chart_source)
    structured = await tools.get_forex_chart_data("EUR/USD", "1H")
    static = generator.render_static_forex_chart(chart_data)

    assert structured == chart_data.model_dump(mode="json")
    assert Path(static["path"]).is_file()
    assert static["chart_data_summary"]["score"] == structured["analysis"]["score"]


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
