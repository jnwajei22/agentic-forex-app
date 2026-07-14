from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.market import Candle
from app.mcp import tools
from app.services.charting import generator
from app.services.market_data.candles import normalize_candle, normalize_history_payload
from app.services.market_data.history import (
    MAX_CANDLES,
    PaginatedCandleResult,
    TIMEFRAME_DURATION_MS,
    get_candles_paginated,
)
from app.services.technical_analysis.analyzer import analyze_pair_from_candles


HOUR = TIMEFRAME_DURATION_MS["1H"]
END = int(datetime(2026, 7, 13, tzinfo=timezone.utc).timestamp() * 1000)


def raw(timestamp: int, *, abbreviated: bool = True) -> dict:
    values = {"timestamp": timestamp, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 10}
    if not abbreviated:
        return values
    return {"t": timestamp, "o": 1.1, "h": 1.2, "l": 1.0, "c": 1.15, "v": 10}


def provider(timestamps: list[int], calls: list[tuple[int, int]], *, fail_after: int | None = None):
    async def fetch(start: int, end: int):
        calls.append((start, end))
        if fail_after is not None and len(calls) > fail_after:
            raise TimeoutError("provider timeout")
        selected = [value for value in timestamps if start <= value <= end][-300:]
        return [raw(value) for value in selected]
    return fetch


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [25, 300])
async def test_one_batch_and_exactly_300(count):
    start = END - HOUR * count
    timestamps = [start + HOUR * index for index in range(1, count + 1)]
    calls = []
    result = await get_candles_paginated(
        instrument_id="77", timeframe="1H", start_time_ms=start, end_time_ms=END,
        requested_count=count, fetch_page=provider(timestamps, calls),
    )
    assert len(result.candles) == count
    assert result.complete
    assert result.batches_requested == 1


@pytest.mark.asyncio
async def test_three_month_hourly_paginates_backward_deduplicates_sorts_and_charts(tmp_path, monkeypatch):
    count = 24 * 91
    start = END - HOUR * count
    timestamps = [start + HOUR * index for index in range(1, count + 1)]
    calls = []

    async def inclusive_provider(page_start: int, page_end: int):
        calls.append((page_start, page_end))
        selected = [value for value in timestamps if page_start <= value <= page_end][-300:]
        if selected:
            selected.append(selected[-1])
        return [raw(value) for value in reversed(selected)]

    result = await get_candles_paginated(
        instrument_id="77", timeframe="1h", start_time_ms=start, end_time_ms=END,
        fetch_page=inclusive_provider,
    )
    assert len(result.candles) == count > 300
    assert result.complete and result.batches_requested == 8
    assert [c.timestamp for c in result.candles] == sorted(set(timestamps))
    assert all(calls[index + 1][1] < calls[index][1] for index in range(len(calls) - 1))

    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    analysis = analyze_pair_from_candles("EUR/USD", "1H", result.candles, "history-test")
    chart = generator.generate_forex_chart("EUR/USD", "1H", result.candles, analysis)
    assert Path(chart["path"]).is_file()


@pytest.mark.asyncio
async def test_range_filter_empty_second_page_and_incomplete_metadata():
    start = END - HOUR * 600
    available = [END - HOUR * index for index in range(200)]
    calls = []
    result = await get_candles_paginated(
        instrument_id="77", timeframe="1H", start_time_ms=start, end_time_ms=END,
        fetch_page=provider(available + [start - HOUR, END + HOUR], calls),
    )
    assert result.batches_requested == 2
    assert not result.complete
    assert result.stop_reason == "provider_no_older_history"
    assert all(start <= candle.timestamp <= END for candle in result.candles)
    assert "no older" in result.warning.lower()


@pytest.mark.asyncio
async def test_stalled_oldest_timestamp_stops_without_looping():
    start = END - HOUR * 600
    fixed = [END - HOUR * index for index in range(300)]
    calls = []

    async def ignores_boundaries(page_start: int, page_end: int):
        calls.append((page_start, page_end))
        return [raw(value) for value in fixed]

    result = await get_candles_paginated(
        instrument_id="77", timeframe="1H", start_time_ms=start, end_time_ms=END,
        fetch_page=ignores_boundaries,
    )
    assert result.stop_reason == "oldest_timestamp_stalled"
    assert result.batches_requested == 2
    assert len(result.candles) == 300


@pytest.mark.asyncio
async def test_maximum_candle_and_page_limits():
    with pytest.raises(ValueError, match="safety limit"):
        await get_candles_paginated(
            instrument_id="77", timeframe="1H", start_time_ms=END - HOUR * (MAX_CANDLES + 1),
            end_time_ms=END, fetch_page=provider([], []),
        )
    timestamps = [END - HOUR * index for index in range(1000)]
    result = await get_candles_paginated(
        instrument_id="77", timeframe="1H", start_time_ms=END - HOUR * 1000,
        end_time_ms=END, fetch_page=provider(timestamps, []), max_pages=2,
    )
    assert result.stop_reason == "max_pages_reached"
    assert not result.complete


@pytest.mark.asyncio
async def test_partial_result_survives_later_upstream_failure():
    start = END - HOUR * 600
    timestamps = [start + HOUR * index for index in range(1, 601)]
    result = await get_candles_paginated(
        instrument_id="77", timeframe="1H", start_time_ms=start, end_time_ms=END,
        fetch_page=provider(timestamps, [], fail_after=1),
    )
    assert len(result.candles) == 300
    assert not result.complete and result.stop_reason == "upstream_error"
    assert result.correlation_id and "partial" in result.warning.lower()


def test_normalizes_abbreviated_expanded_seconds_missing_volume_and_rejects_malformed():
    seconds = END // 1000
    abbreviated = normalize_candle({"t": seconds, "o": 1, "h": 2, "l": 0.5, "c": 1.5})
    expanded = normalize_candle(raw(END, abbreviated=False))
    assert abbreviated.timestamp == END and abbreviated.volume == 0
    assert expanded.model_dump() == raw(END, abbreviated=False)
    for bad in (
        {"t": END, "o": "1", "h": 2, "l": 1, "c": 1.5},
        {"t": END, "o": 1, "h": 0, "l": 1, "c": 1.5},
        {"o": 1, "h": 2, "l": 1, "c": 1.5},
    ):
        with pytest.raises(ValueError):
            normalize_candle(bad)


def test_malformed_history_rows_are_discarded_at_boundary():
    candles, discarded = normalize_history_payload([raw(END), {"t": END - HOUR, "o": 1}])
    assert len(candles) == 1 and discarded == 1
    assert set(candles[0].model_dump()) == {"timestamp", "open", "high", "low", "close", "volume"}


@pytest.mark.asyncio
async def test_mcp_explicit_range_overrides_lookback_and_serializes_metadata(monkeypatch):
    captured = {}

    class Adapter:
        async def get_candles(self, symbol, timeframe, lookback, **kwargs):
            captured.update(symbol=symbol, timeframe=timeframe, lookback=lookback, **kwargs)
            return PaginatedCandleResult(
                instrument_id="77", timeframe="1H", requested_start_ms=END - HOUR,
                requested_end_ms=END, estimated_candles=1,
                candles=[Candle(**raw(END, abbreviated=False))], batches_requested=1, complete=True,
                stop_reason="range_covered",
            )

    monkeypatch.setattr(tools, "_missing_user_connection", lambda: None)
    monkeypatch.setattr(tools, "get_tradelocker_adapter", lambda: Adapter())
    result = await tools.get_my_tradelocker_candles(
        "EUR/USD", "1H", lookback=5,
        start_time="2026-07-12T23:00:00Z", end_time="2026-07-13T00:00:00Z",
    )
    assert captured["lookback"] is None
    assert captured["start_time_ms"] == END - HOUR and captured["end_time_ms"] == END
    assert result["candles_returned"] == 1 and result["candles"][0]["timestamp"] == END
    assert result["complete"] and result["warning"] is None


@pytest.mark.asyncio
async def test_mcp_rejects_invalid_range_and_non_utc_time(monkeypatch):
    monkeypatch.setattr(tools, "_missing_user_connection", lambda: None)
    invalid_range = await tools.get_my_tradelocker_candles(
        "EUR/USD", "1H", start_time="2026-07-13T01:00:00Z", end_time="2026-07-13T00:00:00Z"
    )
    non_utc = await tools.get_my_tradelocker_candles(
        "EUR/USD", "1H", start_time="2026-07-12T23:00:00-05:00"
    )
    assert invalid_range["error"] == "invalid_candle_request"
    assert "earlier" in invalid_range["message"]
    assert non_utc["error"] == "invalid_candle_request"
    assert "UTC" in non_utc["message"]
