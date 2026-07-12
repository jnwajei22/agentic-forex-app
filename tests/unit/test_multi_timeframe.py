from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle
from app.services import multi_timeframe


def _candles(count: int = 60) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            timestamp=start + timedelta(minutes=15 * index),
            open=1.0 + index * 0.001,
            high=1.002 + index * 0.001,
            low=0.999 + index * 0.001,
            close=1.001 + index * 0.001,
        )
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_multi_timeframe_report_handles_missing_15m(monkeypatch):
    async def candles(pair, timeframe, lookback):
        return [] if timeframe == "15m" else _candles()

    async def spread(pair):
        return 0.0001

    monkeypatch.setattr(multi_timeframe, "get_candles", candles)
    monkeypatch.setattr(multi_timeframe, "get_spread", spread)

    report = await multi_timeframe.analyze_multi_timeframe_report("EUR/USD")

    assert "warning" in report["timeframes"]["15m"]
    assert any("15m" in warning for warning in report["warnings"])
    assert report["timeframes"]["1h"]["rsi_14"] is not None


@pytest.mark.asyncio
async def test_multi_timeframe_report_returns_confluence_summary(monkeypatch):
    async def candles(pair, timeframe, lookback):
        return _candles()

    async def spread(pair):
        return None

    monkeypatch.setattr(multi_timeframe, "get_candles", candles)
    monkeypatch.setattr(multi_timeframe, "get_spread", spread)

    report = await multi_timeframe.analyze_multi_timeframe_report("EUR/USD")

    assert "align bullish" in report["confluence_summary"]
    assert report["strongest_timeframe_bias"]["trend"] == "bullish"
