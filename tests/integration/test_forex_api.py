import json
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.routes import forex
from app.services.charting import generator
from app.brokers.tradelocker.adapter import TradeLockerAdapter
from app.config.settings import settings
from app.main import app
from app.services.watchlist import DEFAULT_FOREX_WATCHLIST


client = TestClient(app)
FIXTURE = Path(__file__).parents[1] / "fixtures" / "mock_candles.json"


def test_get_forex_watchlist():
    response = client.get("/forex/watchlist")

    assert response.status_code == 200
    assert [item["pair"] for item in response.json()] == DEFAULT_FOREX_WATCHLIST


def test_post_forex_scan_returns_ranked_results():
    candle_data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    response = client.post(
        "/forex/scan", json={"candle_data": candle_data, "timeframe": "1h"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scan_id"].startswith("fxscan_")
    assert body["disclaimer"] == forex.DISCLAIMER
    assert body["timestamp"]
    assert len(body["results"]) == 2
    scores = [result["score"] for result in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_post_forex_chart_returns_valid_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "market_data_provider", "mock")
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    response = client.post(
        "/forex/chart",
        json={
            "pair": "EUR/USD",
            "timeframe": "1h",
            "overlays": ["fib"],
            "entry": 1.104,
            "stop_loss": 1.099,
            "take_profit": 1.112,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["chart_id"].startswith("chart_")
    assert Path(body["path"]).is_file()
    assert "Static candlestick analysis chart" in body["summary"]
    assert body["pair"] == "EUR/USD"
    assert body["timeframe"] == "1h"
    assert body["trend"] in {"bullish", "bearish", "neutral", "choppy"}
    assert body["generated_at"]


def test_post_forex_chart_rejects_invalid_or_missing_pair(monkeypatch):
    monkeypatch.setattr(settings, "market_data_provider", "mock")
    invalid = client.post("/forex/chart", json={"pair": "XYZ/ABC"})
    missing = client.post("/forex/chart", json={"pair": "USD/JPY"})

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "Pair is not allowed."
    assert missing.status_code == 404
    assert missing.json()["detail"] == "No candles found for pair."


def test_order_preview_returns_rejected_object_with_risk_violations(monkeypatch):
    monkeypatch.setattr(settings, "kill_switch_enabled", False)
    response = client.post(
        "/forex/order-preview",
        json={
            "pair": "EUR/USD",
            "side": "long",
            "entry": 1.1000,
            "stop_loss": 1.1010,
            "take_profit": 1.1100,
            "risk_percent": 0.5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert any("Long stop loss" in violation for violation in body["violations"])
    assert set(body) == {
        "preview_id", "status", "pair", "side", "entry", "stop_loss",
        "take_profit", "lot_size", "pip_risk", "risk_amount",
        "reward_risk", "violations", "expires_at",
    }


def test_forex_routes_never_invoke_live_trading(monkeypatch):
    submit_order = AsyncMock(side_effect=AssertionError("live broker invoked"))
    monkeypatch.setattr(TradeLockerAdapter, "submit_order", submit_order)
    monkeypatch.setattr(settings, "kill_switch_enabled", True)

    response = client.post(
        "/forex/order-preview",
        json={
            "pair": "EUR/USD",
            "side": "short",
            "entry": 1.1000,
            "stop_loss": 1.1050,
            "take_profit": 1.0900,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    submit_order.assert_not_awaited()
