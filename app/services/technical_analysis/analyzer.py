from collections.abc import Mapping, Sequence

from app.models.analysis import SetupAnalysis
from app.models.enums import Direction, SetupStatus
from app.models.market import Candle
from app.services.technical_analysis.fibonacci import calculate_fib_levels
from app.services.technical_analysis.scoring import score_setup
from app.services.technical_analysis.support_resistance import detect_support_resistance
from app.services.technical_analysis.swings import find_pivot_swings
from app.services.technical_analysis.trend import classify_trend


def analyze_pair_from_candles(
    pair: str,
    timeframe: str,
    candles: Sequence[Candle],
    strategy_profile: str | Mapping[str, object] | None = None,
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
        summary=(
            f"{trend.capitalize()} structure; {direction.value} bias with "
            f"{len(support_zones)} support and {len(resistance_zones)} resistance zone(s)."
        ),
    )
