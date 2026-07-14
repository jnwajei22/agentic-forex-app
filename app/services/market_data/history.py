from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.market import Candle
from app.services.market_data.candles import normalize_history_payload

MAX_CANDLES = 10_000
MAX_BATCH_SIZE = 300
MAX_PAGES = 50

# TradeLocker uses this exact, case-sensitive resolution vocabulary.
TIMEFRAME_DURATION_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1H": 3_600_000,
    "4H": 14_400_000,
    "1D": 86_400_000,
    "1W": 604_800_000,
    "1M": 2_592_000_000,
}

logger = logging.getLogger(__name__)
PageFetcher = Callable[[int, int], Awaitable[Any]]


def normalize_timeframe(timeframe: str) -> str:
    candidate = timeframe.strip()
    aliases = {"1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W"}
    candidate = aliases.get(candidate, candidate)
    if candidate not in TIMEFRAME_DURATION_MS:
        raise ValueError(f"Unsupported TradeLocker timeframe: {timeframe}.")
    return candidate


def estimate_candles(start_time_ms: int, end_time_ms: int, timeframe: str) -> int:
    if start_time_ms >= end_time_ms:
        raise ValueError("start_time must be earlier than end_time.")
    return max(1, math.ceil((end_time_ms - start_time_ms) / TIMEFRAME_DURATION_MS[timeframe]))


@dataclass
class PaginatedCandleResult:
    instrument_id: str
    timeframe: str
    requested_start_ms: int
    requested_end_ms: int
    estimated_candles: int
    candles: list[Candle] = field(default_factory=list)
    batches_requested: int = 0
    complete: bool = False
    warning: str | None = None
    stop_reason: str | None = None
    malformed_discarded: int = 0
    correlation_id: str | None = None


async def get_candles_paginated(
    *,
    instrument_id: str,
    timeframe: str,
    start_time_ms: int,
    end_time_ms: int,
    fetch_page: PageFetcher,
    requested_count: int | None = None,
    batch_size: int = MAX_BATCH_SIZE,
    max_candles: int = MAX_CANDLES,
    max_pages: int = MAX_PAGES,
) -> PaginatedCandleResult:
    """Retrieve bounded history backwards and normalize at each page boundary."""
    resolution = normalize_timeframe(timeframe)
    estimated = estimate_candles(start_time_ms, end_time_ms, resolution)
    if requested_count is not None and not 1 <= requested_count <= max_candles:
        raise ValueError(f"lookback must be between 1 and {max_candles}.")
    target = min(estimated, requested_count) if requested_count is not None else estimated
    if target > max_candles or estimated > max_candles:
        raise ValueError(f"Requested candle range exceeds the {max_candles} candle safety limit.")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}.")

    result = PaginatedCandleResult(
        instrument_id=str(instrument_id), timeframe=resolution,
        requested_start_ms=start_time_ms, requested_end_ms=end_time_ms,
        estimated_candles=estimated,
    )
    duration = TIMEFRAME_DURATION_MS[resolution]
    boundary = end_time_ms
    by_timestamp: dict[int, Candle] = {}
    previous_oldest: int | None = None
    range_fully_queried = False

    for _ in range(max_pages):
        if boundary < start_time_ms or len(by_timestamp) >= target:
            result.stop_reason = "requested_count_reached" if len(by_timestamp) >= target else "range_covered"
            break
        page_start = max(start_time_ms, boundary - duration * (batch_size - 1))
        result.batches_requested += 1
        try:
            payload = await fetch_page(page_start, boundary)
        except Exception as exc:
            if not by_timestamp:
                raise
            result.stop_reason = "upstream_error"
            result.correlation_id = uuid.uuid4().hex
            logger.warning(
                "TradeLocker candle pagination failed after partial retrieval correlation_id=%s error_type=%s",
                result.correlation_id, type(exc).__name__,
            )
            break

        page, discarded = normalize_history_payload(payload)
        result.malformed_discarded += discarded
        valid = [c for c in page if start_time_ms <= c.timestamp <= end_time_ms]
        if not valid:
            result.stop_reason = "provider_no_older_history"
            break
        oldest = min(c.timestamp for c in valid)
        for candle in valid:
            by_timestamp[candle.timestamp] = candle
        if previous_oldest is not None and oldest >= previous_oldest:
            result.stop_reason = "oldest_timestamp_stalled"
            break
        previous_oldest = oldest
        boundary = oldest - 1  # TradeLocker treats `to` as inclusive.
        if requested_count is None and page_start == start_time_ms:
            range_fully_queried = True
            result.stop_reason = "range_covered"
            break
    else:
        result.stop_reason = "max_pages_reached"

    ordered = sorted(by_timestamp.values(), key=lambda candle: candle.timestamp)
    if requested_count is not None and len(ordered) > requested_count:
        ordered = ordered[-requested_count:]
    result.candles = ordered[:max_candles]
    covered_range = range_fully_queried or (
        bool(ordered) and ordered[0].timestamp <= start_time_ms + duration
    )
    count_complete = requested_count is not None and len(ordered) >= requested_count
    result.complete = covered_range if requested_count is None else count_complete
    if result.complete:
        result.stop_reason = result.stop_reason or "range_covered"
    else:
        reason = {
            "upstream_error": "TradeLocker failed after partial historical retrieval.",
            "max_pages_reached": "The candle-history maximum page limit was reached.",
            "oldest_timestamp_stalled": "TradeLocker did not advance to older candle history.",
            "provider_no_older_history": "TradeLocker returned no older candle history.",
        }.get(result.stop_reason, "The requested candle range was not fully covered.")
        result.warning = f"{reason} Returned {len(ordered)} of approximately {target} candles."
    if result.malformed_discarded:
        suffix = f" Discarded {result.malformed_discarded} malformed candle(s)."
        result.warning = ((result.warning + suffix) if result.warning else suffix.strip())
    return result
