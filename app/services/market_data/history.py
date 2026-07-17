from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.models.market import Candle
from app.config.settings import settings
from app.services.market_data.candles import normalize_history_payload

MAX_CANDLES = settings.market_data_max_retrieval_candles
MAX_BATCH_SIZE = 300
MAX_PAGES = settings.market_data_max_pages

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
    aliases = {
        "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W",
        # These are accepted caller aliases. The provider always receives
        # TradeLocker's documented, case-sensitive value (1D).
        "D": "1D", "d": "1D", "day": "1D", "daily": "1D", "1440": "1D",
    }
    candidate = aliases.get(candidate, candidate)
    if candidate not in TIMEFRAME_DURATION_MS:
        raise ValueError(f"Unsupported TradeLocker timeframe: {timeframe}.")
    return candidate


def estimate_candles(start_time_ms: int, end_time_ms: int, timeframe: str) -> int:
    if start_time_ms >= end_time_ms:
        raise ValueError("start_time must be earlier than end_time.")
    return max(1, math.ceil((end_time_ms - start_time_ms) / TIMEFRAME_DURATION_MS[timeframe]))


def parse_utc_timestamp(value: str, name: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} must be a valid ISO-8601 UTC timestamp.") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{name} must include the UTC timezone.")
    return int(parsed.timestamp() * 1000)


def iso_utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


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
    requested_timeframe: str | None = None
    provider_timeframe_sent: str | None = None
    http_status: int | None = 200
    broker_error_category: str | None = None
    rows_received: int = 0
    mapping_failure: str | None = None
    source: str = "direct"
    fallback_diagnostics: dict[str, Any] | None = None

    def diagnostics(self) -> dict[str, Any]:
        result = {
            "requested_timeframe": self.requested_timeframe or self.timeframe,
            "provider_timeframe_sent": self.provider_timeframe_sent or self.timeframe,
            "http_status": self.http_status,
            "broker_error_category": self.broker_error_category,
            "rows_received": self.rows_received,
            "mapping_failure": self.mapping_failure,
            "candle_source": self.source,
        }
        if self.fallback_diagnostics is not None:
            result["fallback"] = self.fallback_diagnostics
        return result


def aggregate_hourly_candles_to_utc_days(
    candles: list[Candle], *, required_count: int
) -> tuple[list[Candle], list[str]]:
    """Aggregate only complete, canonical UTC days from verified 1H candles."""
    by_day: dict[int, dict[int, Candle]] = {}
    for candle in candles:
        day_start = candle.timestamp - (candle.timestamp % TIMEFRAME_DURATION_MS["1D"])
        by_day.setdefault(day_start, {})[candle.timestamp] = candle

    daily: list[Candle] = []
    incomplete: list[str] = []
    hour = TIMEFRAME_DURATION_MS["1H"]
    for day_start in sorted(by_day):
        rows = by_day[day_start]
        expected = {day_start + hour * index for index in range(24)}
        if set(rows) != expected:
            incomplete.append(iso_utc(day_start)[:10])
            continue
        ordered = [rows[timestamp] for timestamp in sorted(rows)]
        daily.append(Candle(
            timestamp=day_start,
            open=ordered[0].open,
            high=max(row.high for row in ordered),
            low=min(row.low for row in ordered),
            close=ordered[-1].close,
            volume=sum(row.volume for row in ordered),
        ))
    return daily[-required_count:], incomplete


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
    result.rows_received = len(result.candles)
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
        result.mapping_failure = f"{result.malformed_discarded} malformed candle row(s)"
        suffix = f" Discarded {result.malformed_discarded} malformed candle(s)."
        result.warning = ((result.warning + suffix) if result.warning else suffix.strip())
    return result
