from datetime import datetime, timezone

import pytest

from app.models.market import Candle
from app.services.charting import data as service
from app.services.market_data.history import PaginatedCandleResult
from app.services.technical_analysis.indicators import calculate_ema


START = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
HOUR = 3_600_000


def candles(count: int, *, descending: bool = False) -> list[Candle]:
    result = []
    for index in range(count):
        movement = (-index if descending else index) * 0.0001
        close = 1.1 + movement + (0.00005 if index % 4 < 2 else -0.00005)
        result.append(
            Candle(
                timestamp=START + index * HOUR,
                open=close - (-0.00003 if descending else 0.00003),
                high=close + 0.0005 + (0.0002 if index % 17 == 0 else 0),
                low=close - 0.0005 - (0.0002 if index % 19 == 0 else 0),
                close=close,
                volume=100 + index,
            )
        )
    return result


def history(values: list[Candle], *, batches: int = 1) -> PaginatedCandleResult:
    return PaginatedCandleResult(
        instrument_id="77",
        timeframe="1H",
        requested_start_ms=values[0].timestamp,
        requested_end_ms=values[-1].timestamp,
        estimated_candles=len(values),
        candles=values,
        batches_requested=batches,
        complete=True,
        stop_reason="range_covered",
    )


async def build(monkeypatch, values, **kwargs):
    result = history(values, batches=kwargs.pop("batches", 1))

    async def history_source(**request):
        return result

    async def spread_source(pair):
        return 0.00008

    monkeypatch.setattr(service, "get_candle_history", history_source)
    monkeypatch.setattr(service, "get_spread", spread_source)
    return await service.build_chart_data(pair="EUR/USD", timeframe="1H", **kwargs)


@pytest.mark.asyncio
async def test_chart_data_serialization_one_batch_and_analysis_fields(monkeypatch):
    chart = await build(monkeypatch, candles(240))
    payload = chart.model_dump(mode="json")
    assert payload["range"]["batches_requested"] == 1
    assert payload["range"]["candles_returned"] == 240
    assert payload["latest_price"] == chart.candles[-1].close
    assert payload["analysis"].keys() >= {
        "direction", "score", "status", "setup", "trend", "trend_clarity",
        "rsi_14", "atr_14", "spread", "spread_warning", "guidance", "summary",
    }
    assert payload["candles"][0]["iso_time"].endswith("Z")


@pytest.mark.asyncio
async def test_multi_batch_three_month_data_returns_more_than_300(monkeypatch):
    chart = await build(monkeypatch, candles(2184), batches=8)
    assert chart.range.candles_returned == 2184
    assert chart.range.batches_requested == 8
    assert chart.display.source_points == 2184
    assert 300 < chart.display.returned_points <= 2000


@pytest.mark.asyncio
async def test_explicit_range_and_lookback_are_forwarded_with_range_precedence(monkeypatch):
    values = candles(60)
    captured = {}

    async def history_source(**request):
        captured.update(request)
        return history(values)

    async def no_spread(pair):
        return None

    monkeypatch.setattr(service, "get_candle_history", history_source)
    monkeypatch.setattr(service, "get_spread", no_spread)
    await service.build_chart_data(
        pair="EURUSD", timeframe="1h", lookback=5,
        start_time="2026-01-01T00:00:00Z", end_time="2026-01-03T11:00:00Z",
    )
    assert captured["lookback"] is None
    assert captured["start_time"] and captured["end_time"]


@pytest.mark.asyncio
async def test_timestamp_aligned_ema_series(monkeypatch):
    chart = await build(monkeypatch, candles(240), max_points=None)
    assert len(chart.indicators.ema_20) == 221
    assert len(chart.indicators.ema_50) == 191
    assert len(chart.indicators.ema_200) == 41
    assert chart.indicators.ema_20[0].timestamp == chart.candles[19].timestamp
    assert chart.indicators.ema_50[0].timestamp == chart.candles[49].timestamp
    assert chart.indicators.ema_200[0].timestamp == chart.candles[199].timestamp


@pytest.mark.asyncio
async def test_fibonacci_zones_swings_score_and_indicators_are_structured(monkeypatch):
    chart = await build(monkeypatch, candles(240))
    assert chart.fibonacci.levels
    assert chart.fibonacci.swing_low_timestamp is not None
    assert chart.fibonacci.swing_high_timestamp is not None
    assert {swing.type for swing in chart.swings} == {"low", "high"}
    assert all(zone.lower_bound == zone.price == zone.upper_bound for zone in chart.support_zones)
    assert all(zone.type == "resistance" for zone in chart.resistance_zones)
    assert chart.analysis.score >= 0 and chart.analysis.trend_clarity >= 0
    assert chart.indicators.rsi_14 is not None and chart.indicators.atr_14 is not None


@pytest.mark.asyncio
async def test_valid_and_invalid_long_trade_metrics(monkeypatch):
    valid = await build(
        monkeypatch, candles(240), entry=1.12, stop_loss=1.11, take_profit=1.14
    )
    assert valid.trade_setup.valid
    assert valid.trade_setup.risk == pytest.approx(0.01)
    assert valid.trade_setup.reward == pytest.approx(0.02)
    assert valid.trade_setup.risk_reward == pytest.approx(2)
    invalid = await build(
        monkeypatch, candles(240), entry=1.12, stop_loss=1.13, take_profit=1.14
    )
    assert not invalid.trade_setup.valid
    assert "Long levels" in invalid.trade_setup.validation_message


@pytest.mark.asyncio
async def test_valid_and_invalid_short_trade_metrics(monkeypatch):
    values = candles(240, descending=True)
    valid = await build(
        monkeypatch, values, entry=1.08, stop_loss=1.09, take_profit=1.06
    )
    assert valid.analysis.direction == "short" and valid.trade_setup.valid
    assert valid.trade_setup.risk_reward == pytest.approx(2)
    invalid = await build(
        monkeypatch, values, entry=1.08, stop_loss=1.07, take_profit=1.06
    )
    assert not invalid.trade_setup.valid
    assert "Short levels" in invalid.trade_setup.validation_message


@pytest.mark.asyncio
async def test_absent_levels_do_not_fabricate_trade_setup(monkeypatch):
    chart = await build(monkeypatch, candles(60))
    assert chart.trade_setup is None


@pytest.mark.asyncio
async def test_downsampling_preserves_endpoints_and_analysis_uses_full_data(monkeypatch):
    values = candles(2500)
    chart = await build(monkeypatch, values, max_points=100)
    assert chart.display.model_dump() == {
        "source_points": 2500,
        "returned_points": 100,
        "downsampled": True,
        "downsampling_method": "min_max_bucket",
    }
    assert chart.candles[0].timestamp == values[0].timestamp
    assert chart.candles[-1].timestamp == values[-1].timestamp
    assert chart.analysis.ema_200 == pytest.approx(
        calculate_ema([candle.close for candle in values], 200)
    )


@pytest.mark.asyncio
async def test_no_downsampling_below_cap_and_optional_series_controls(monkeypatch):
    chart = await build(
        monkeypatch, candles(1561), max_points=2000,
        include_candles=False, include_indicator_series=False,
    )
    assert not chart.display.downsampled and chart.display.returned_points == 1561
    assert chart.candles == [] and chart.indicators.ema_20 == []
