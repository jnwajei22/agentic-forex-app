from collections.abc import Mapping, Sequence

from app.models.analysis import SetupAnalysis
from app.models.enums import Direction, SetupStatus
from app.models.market import Candle
from app.services.technical_analysis.fibonacci import calculate_fib_levels
from app.services.technical_analysis.indicators import calculate_atr, calculate_rsi, candle_emas
from app.services.technical_analysis.scoring import score_setup
from app.services.technical_analysis.support_resistance import detect_support_resistance
from app.services.technical_analysis.swings import find_pivot_swings
from app.services.technical_analysis.trend import classify_trend


def analyze_pair_from_candles(
    pair: str,
    timeframe: str,
    candles: Sequence[Candle],
    strategy_profile: str | Mapping[str, object] | None = None,
    spread: float | None = None,
) -> SetupAnalysis:
    if len(candles) < 2:
        raise ValueError("At least two candles are required for analysis.")

    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    trend = classify_trend(ordered)
    if trend == "bullish":
        direction = Direction.long
    elif trend == "bearish":
        direction = Direction.short
    else:
        direction = Direction.long if ordered[-1].close >= ordered[0].close else Direction.short

    swing_low_candle, swing_high_candle = find_pivot_swings(ordered)
    swing_low = swing_low_candle.low if swing_low_candle else None
    swing_high = swing_high_candle.high if swing_high_candle else None
    fib_levels = (
        calculate_fib_levels(swing_low, swing_high, direction.value)
        if swing_low is not None and swing_high is not None and swing_high > swing_low
        else {}
    )
    support_zones, resistance_zones = detect_support_resistance(ordered)
    emas = candle_emas(ordered)
    rsi = calculate_rsi([candle.close for candle in ordered])
    atr = calculate_atr(ordered)

    aligned = trend in {"bullish", "bearish"}
    latest = ordered[-1]
    candle_confirms = latest.close > latest.open if direction == Direction.long else latest.close < latest.open
    score = score_setup(
        trend_alignment=30 if aligned else 12,
        fib_quality=15 if fib_levels else 0,
        sr_confluence=15 if support_zones and resistance_zones else 5,
        candle_confirmation=15 if candle_confirms else 5,
        reward_risk=10,
        spread_session=5,
        news_safety=0,
    )
    status = (
        SetupStatus.eligible_for_preview if score >= 80
        else SetupStatus.watch if score >= 65
        else SetupStatus.weak if score >= 50
        else SetupStatus.no_setup
    )
    profile_name = strategy_profile if isinstance(strategy_profile, str) else "default"
    ema_alignment = sum(
        1
        for value in emas.values()
        if value is not None
        and ((trend == "bullish" and latest.close > value) or (trend == "bearish" and latest.close < value))
    )
    trend_clarity = min(100, (60 if aligned else 30) + (ema_alignment * 12))
    guidance = (
        "Clean directional setup for analysis; confirm context and risk independently."
        if status in {SetupStatus.eligible_for_preview, SetupStatus.watch} and aligned
        else "No trade / no clean setup; structure is weak or mixed."
    )
    spread_bps = (spread / latest.close * 10_000) if spread is not None and latest.close else None
    spread_warning = (
        "Spread is unavailable; verify transaction-cost conditions independently."
        if spread is None
        else (
            f"Spread is elevated at {spread_bps:.2f} basis points."
            if spread_bps is not None and spread_bps > 2
            else None
        )
    )

    return SetupAnalysis(
        pair=pair,
        timeframe=timeframe,
        direction=direction,
        score=score,
        status=status,
        setup=f"{profile_name}_{direction.value}_technical",
        trend=trend,
        swing_high=swing_high,
        swing_low=swing_low,
        fib_levels=fib_levels,
        support_zones=support_zones,
        resistance_zones=resistance_zones,
        ema_20=emas["ema_20"],
        ema_50=emas["ema_50"],
        ema_200=emas["ema_200"],
        rsi_14=rsi,
        atr_14=atr,
        candle_range=latest.high - latest.low,
        spread=spread,
        spread_warning=spread_warning,
        trend_clarity=trend_clarity,
        guidance=guidance,
        summary=(
            f"{trend.capitalize()} structure; {direction.value} bias with "
            f"{len(support_zones)} support and {len(resistance_zones)} resistance zone(s)."
        ),
    )
