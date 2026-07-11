from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.brokers.tradelocker.adapter import TradeLockerAdapter
from app.config.settings import settings
from app.main import app
from app.mcp import tools
from app.mcp.server import mcp


EXPECTED_TOOLS = {
    "get_forex_watchlist",
    "scan_forex_watchlist",
    "generate_chart",
    "review_forex_order",
    "get_account_status",
    "get_open_positions",
    "get_trade_log",
    "set_kill_switch",
}


def test_mcp_endpoint_initializes_and_advertises_tools():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=payload,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
        tool_response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"tools":{"listChanged":true}' in response.text
    assert '"name":"Agentic Forex Desk"' in response.text
    assert tool_response.status_code == 200
    for tool_name in EXPECTED_TOOLS:
        assert f'"name":"{tool_name}"' in tool_response.text


@pytest.mark.asyncio
async def test_mcp_server_registers_expected_tools():
    registered = {tool.name for tool in await mcp.list_tools()}
    assert registered == EXPECTED_TOOLS


def test_mcp_watchlist_and_scan_are_usable_and_ranked():
    watchlist = tools.get_forex_watchlist()
    results = tools.scan_forex_watchlist(["1h"], "default", 5)

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
