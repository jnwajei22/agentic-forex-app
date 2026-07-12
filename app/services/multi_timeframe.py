from collections.abc import Sequence
from typing import Any

from app.brokers.tradelocker.client import TradeLockerError
from app.services.market_data.service import get_candles, get_spread
from app.services.technical_analysis.analyzer import analyze_pair_from_candles
from app.services.watchlist import is_allowed_pair, normalize_pair


DEFAULT_TIMEFRAMES = ("15m", "1h", "4h")


async def analyze_multi_timeframe_report(
    pair: str, timeframes: Sequence[str] = DEFAULT_TIMEFRAMES
) -> dict[str, Any]:
    normalized_pair = normalize_pair(pair)
    if not is_allowed_pair(normalized_pair):
        raise ValueError(f"Unknown forex pair: {pair}")
    if not timeframes:
        raise ValueError("At least one timeframe is required.")

    spread = await get_spread(normalized_pair)
    analyses: dict[str, Any] = {}
    warnings: list[str] = []
    available = []
    for timeframe in timeframes:
        try:
            candles = await get_candles(normalized_pair, timeframe, 300)
        except (TradeLockerError, OSError, ValueError) as exc:
            candles = []
            warning = f"Missing data for {normalized_pair} {timeframe}: {exc}"
            warnings.append(warning)
            analyses[timeframe] = {"warning": warning}
            continue
        if len(candles) < 2:
            warning = f"Missing data for {normalized_pair} {timeframe}."
            warnings.append(warning)
            analyses[timeframe] = {"warning": warning}
            continue

        analysis = analyze_pair_from_candles(
            normalized_pair, timeframe, candles, "multi_timeframe", spread=spread
        )
        fib_values = [
            value
            for key, value in analysis.fib_levels.items()
            if key in {"0.382", "0.500", "0.618"}
        ]
        result = {
            "trend": analysis.trend,
            "support": analysis.support_zones,
            "resistance": analysis.resistance_zones,
            "fib_zone": (
                {"low": min(fib_values), "high": max(fib_values)}
                if fib_values
                else None
            ),
            "rsi_14": analysis.rsi_14,
            "atr_14": analysis.atr_14,
            "trend_clarity": analysis.trend_clarity,
            "summary": analysis.summary,
        }
        analyses[timeframe] = result
        available.append((timeframe, analysis))

    trend_counts: dict[str, int] = {}
    for _, analysis in available:
        trend_counts[analysis.trend] = trend_counts.get(analysis.trend, 0) + 1
    if available:
        dominant_trend = max(trend_counts, key=trend_counts.get)
        aligned = trend_counts[dominant_trend]
        confluence = (
            f"{aligned} of {len(available)} available timeframes align {dominant_trend}. "
            + (
                "Directional confluence is present."
                if aligned > len(available) / 2
                else "No clean multi-timeframe confluence; conditions are mixed."
            )
        )
        strongest_timeframe, strongest = max(
            available, key=lambda item: item[1].trend_clarity
        )
        strongest_bias = {
            "timeframe": strongest_timeframe,
            "trend": strongest.trend,
            "trend_clarity": strongest.trend_clarity,
        }
    else:
        confluence = "No clean multi-timeframe setup because candle data is unavailable."
        strongest_bias = None

    return {
        "pair": normalized_pair,
        "timeframes": analyses,
        "confluence_summary": confluence,
        "strongest_timeframe_bias": strongest_bias,
        "warnings": warnings,
        "spread": spread,
        "disclaimer": "Analysis only. Not financial advice.",
    }
