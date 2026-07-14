from __future__ import annotations

import math

from app.models.chart import (
    CandlePoint,
    ChartAnalysis,
    ChartData,
    ChartRange,
    DisplayMetadata,
    FibonacciData,
    IndicatorSeries,
    SeriesPoint,
    SupportResistanceZone,
    SwingPoint,
    TradeSetup,
)
from app.models.market import Candle
from app.services.market_data.history import iso_utc, normalize_timeframe
from app.services.market_data.service import get_candle_history, get_spread
from app.services.technical_analysis.analyzer import analyze_pair_from_candles
from app.services.technical_analysis.indicators import calculate_ema_series
from app.services.watchlist import is_allowed_pair, normalize_pair


DEFAULT_MAX_POINTS = 2_000


def _structure_indices(candles: list[Candle], max_points: int) -> list[int]:
    """Preserve endpoints and high/low structure with min/max bucket sampling."""
    count = len(candles)
    if count <= max_points:
        return list(range(count))
    if max_points < 2:
        raise ValueError("max_points must be at least 2.")
    interior_slots = max_points - 2
    if not interior_slots:
        return [0, count - 1]
    bucket_count = max(1, math.ceil(interior_slots / 2))
    bucket_width = (count - 2) / bucket_count
    selected = {0, count - 1}
    for bucket in range(bucket_count):
        start = 1 + math.floor(bucket * bucket_width)
        end = min(count - 1, 1 + math.floor((bucket + 1) * bucket_width))
        indices = list(range(start, max(start + 1, end)))
        selected.add(max(indices, key=lambda index: candles[index].high))
        selected.add(min(indices, key=lambda index: candles[index].low))
    ordered = sorted(selected)
    if len(ordered) > max_points:
        removable = ordered[1:-1]
        ranked = sorted(
            removable,
            key=lambda index: candles[index].high - candles[index].low,
            reverse=True,
        )[:interior_slots]
        ordered = [0, *sorted(ranked), count - 1]
    return ordered


def _candle_point(candle: Candle) -> CandlePoint:
    return CandlePoint(
        timestamp=candle.timestamp,
        iso_time=iso_utc(candle.timestamp),
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )


def _series(candles: list[Candle], period: int, indices: list[int]) -> list[SeriesPoint]:
    values = calculate_ema_series([candle.close for candle in candles], period)
    return [
        SeriesPoint(timestamp=candles[index].timestamp, value=value)
        for index in indices
        if (value := values[index]) is not None
    ]


def _trade_setup(
    direction: str | None,
    entry: float | None,
    stop_loss: float | None,
    take_profit: float | None,
) -> TradeSetup | None:
    if entry is None and stop_loss is None and take_profit is None:
        return None
    setup = TradeSetup(
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    if entry is None or stop_loss is None or take_profit is None:
        setup.validation_message = "Entry, stop loss, and take profit are all required."
        return setup
    if direction == "long":
        setup.risk = entry - stop_loss
        setup.reward = take_profit - entry
        valid_order = stop_loss < entry < take_profit
        ordering = "Long levels must satisfy stop_loss < entry < take_profit."
    elif direction == "short":
        setup.risk = stop_loss - entry
        setup.reward = entry - take_profit
        valid_order = take_profit < entry < stop_loss
        ordering = "Short levels must satisfy take_profit < entry < stop_loss."
    else:
        setup.validation_message = "Trade direction is unavailable."
        return setup
    setup.valid = valid_order and setup.risk > 0 and setup.reward > 0
    if setup.valid:
        setup.risk_reward = setup.reward / setup.risk
    else:
        setup.validation_message = ordering
    return setup


async def build_chart_data(
    *,
    pair: str,
    timeframe: str,
    lookback: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    overlays: list[str] | None = None,
    entry: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    max_points: int | None = DEFAULT_MAX_POINTS,
    include_candles: bool = True,
    include_indicator_series: bool = True,
) -> ChartData:
    """Build reusable chart/analysis data without rendering or filesystem writes."""
    normalized_pair = normalize_pair(pair)
    if not is_allowed_pair(normalized_pair):
        raise ValueError(f"Unknown forex pair: {pair}")
    resolution = normalize_timeframe(timeframe)
    if max_points is not None and max_points < 2:
        raise ValueError("max_points must be at least 2.")

    history = await get_candle_history(
        pair=normalized_pair,
        timeframe=resolution,
        lookback=None if start_time is not None else lookback,
        start_time=start_time,
        end_time=end_time,
    )
    candles = sorted(history.candles, key=lambda candle: candle.timestamp)
    if len(candles) < 2:
        raise ValueError(f"At least two candles are required for pair: {normalized_pair}")
    spread = await get_spread(normalized_pair)
    analysis = analyze_pair_from_candles(
        normalized_pair, resolution, candles, "chart", spread=spread
    )

    indices = (
        list(range(len(candles)))
        if max_points is None
        else _structure_indices(candles, max_points)
    )
    downsampled = len(indices) < len(candles)
    direction = analysis.direction.value if analysis.direction else None
    zones = lambda values, kind: [
        SupportResistanceZone(
            type=kind, price=value, lower_bound=value, upper_bound=value
        )
        for value in values
    ]
    swings = []
    if analysis.swing_low is not None and analysis.swing_low_timestamp is not None:
        swings.append(SwingPoint(timestamp=analysis.swing_low_timestamp, price=analysis.swing_low, type="low"))
    if analysis.swing_high is not None and analysis.swing_high_timestamp is not None:
        swings.append(SwingPoint(timestamp=analysis.swing_high_timestamp, price=analysis.swing_high, type="high"))

    return ChartData(
        pair=normalized_pair,
        symbol=normalized_pair.replace("/", ""),
        timeframe=resolution,
        range=ChartRange(
            requested_start=iso_utc(history.requested_start_ms),
            requested_end=iso_utc(history.requested_end_ms),
            actual_start=iso_utc(candles[0].timestamp),
            actual_end=iso_utc(candles[-1].timestamp),
            candles_returned=len(candles),
            batches_requested=history.batches_requested,
            complete=history.complete,
            stop_reason=history.stop_reason,
            warning=history.warning,
            malformed_candles_discarded=history.malformed_discarded,
        ),
        latest_price=candles[-1].close,
        analysis=ChartAnalysis(
            trend=analysis.trend,
            direction=direction,
            score=analysis.score,
            status=analysis.status.value,
            setup=analysis.setup,
            trend_clarity=analysis.trend_clarity,
            ema_20=analysis.ema_20,
            ema_50=analysis.ema_50,
            ema_200=analysis.ema_200,
            rsi_14=analysis.rsi_14,
            atr_14=analysis.atr_14,
            candle_range=analysis.candle_range,
            spread=analysis.spread,
            spread_warning=analysis.spread_warning,
            missing_data_warning=analysis.missing_data_warning,
            guidance=analysis.guidance,
            summary=analysis.summary,
        ),
        indicators=IndicatorSeries(
            ema_20=_series(candles, 20, indices) if include_indicator_series else [],
            ema_50=_series(candles, 50, indices) if include_indicator_series else [],
            ema_200=_series(candles, 200, indices) if include_indicator_series else [],
            rsi_14=analysis.rsi_14,
            atr_14=analysis.atr_14,
        ),
        fibonacci=FibonacciData(
            direction=direction,
            swing_low=analysis.swing_low,
            swing_high=analysis.swing_high,
            swing_low_timestamp=analysis.swing_low_timestamp,
            swing_high_timestamp=analysis.swing_high_timestamp,
            levels=analysis.fib_levels,
        ),
        support_zones=zones(analysis.support_zones, "support"),
        resistance_zones=zones(analysis.resistance_zones, "resistance"),
        swings=swings,
        trade_setup=_trade_setup(direction, entry, stop_loss, take_profit),
        display=DisplayMetadata(
            source_points=len(candles),
            returned_points=len(indices),
            downsampled=downsampled,
            downsampling_method="min_max_bucket" if downsampled else None,
        ),
        candles=[_candle_point(candles[index]) for index in indices] if include_candles else [],
    )
