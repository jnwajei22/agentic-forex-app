from fastapi.testclient import TestClient

from app.config.settings import settings
from app.main import app


client = TestClient(app)
SIGNAL = {
    "source": "tradingview",
    "pair": "EUR/USD",
    "timeframe": "1h",
    "signal": "buy",
    "price": 1.1,
    "strategy": "test",
    "timestamp": "2026-07-10T12:00:00Z",
}


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_ready():
    assert client.get("/ready").json() == {"status": "ready"}


def test_tradingview_webhook_secret_validation(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_webhook_secret", "test-secret")
    assert client.post("/webhooks/tradingview", json=SIGNAL).status_code == 401
    assert client.post(
        "/webhooks/tradingview",
        json=SIGNAL,
        headers={"X-TradingView-Secret": "wrong"},
    ).status_code == 401
    assert client.post(
        "/webhooks/tradingview",
        json=SIGNAL,
        headers={"X-TradingView-Secret": "test-secret"},
    ).status_code == 200


def test_tradingview_rejects_unknown_forex_pair(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_webhook_secret", "test-secret")
    response = client.post(
        "/webhooks/tradingview",
        json={**SIGNAL, "pair": "XYZ/ABC"},
        headers={"X-TradingView-Secret": "test-secret"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Pair is not allowed."
