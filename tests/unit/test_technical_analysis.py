from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle
from app.services.technical_analysis.analyzer import analyze_pair_from_candles
from app.services.technical_analysis.indicators import (
    calculate_atr,
    calculate_ema,
    calculate_rsi,
    candle_emas,
)
from app.services.technical_analysis.support_resistance import detect_support_resistance
from app.services.technical_analysis.swings import find_pivot_swings
from app.services.technical_analysis.trend import classify_trend


def make_candles(closes: list[float]) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            timestamp=start + timedelta(hours=index),
            open=close - 0.1 if index == 0 or close >= closes[index - 1] else close + 0.1,
            high=close + 0.2,
            low=close - 0.2,
            close=close,
        )
        for index, close in enumerate(closes)
    ]


def test_ema_calculation_and_standard_period_availability():
    assert calculate_ema([1, 2, 3, 4], 3) == pytest.approx(3.0)
    assert calculate_ema([1, 2], 3) is None
    emas = candle_emas(make_candles([float(value) for value in range(1, 61)]))
    assert emas["ema_20"] is not None
    assert emas["ema_50"] is not None
    assert emas["ema_200"] is None


def test_rsi_calculation():
    assert calculate_rsi([float(value) for value in range(1, 16)]) == pytest.approx(100.0)
    assert calculate_rsi([1.0] * 15) == pytest.approx(50.0)
    assert calculate_rsi([1.0, 2.0], period=14) is None


def test_atr_calculation():
    candles = make_candles([float(value) for value in range(1, 17)])
    assert calculate_atr(candles) == pytest.approx(1.2)
    assert calculate_atr(candles[:10]) is None


def test_trend_classification_bullish():
    assert classify_trend(make_candles([float(value) for value in range(1, 61)])) == "bullish"


def test_trend_classification_bearish():
    assert classify_trend(make_candles([float(value) for value in range(60, 0, -1)])) == "bearish"


def test_default_window_pivot_swing_detection():
    candles = make_candles([5, 4, 3, 2, 5, 8, 7, 6, 5, 4, 3])
    swing_low, swing_high = find_pivot_swings(candles)

    assert swing_low is not None and swing_low.close == 2
    assert swing_high is not None and swing_high.close == 8


def test_support_resistance_zones_are_deterministic():
    candles = make_candles([5, 3, 5, 7, 5, 4])
    first = detect_support_resistance(candles, window=1)
    second = detect_support_resistance(candles, window=1)

    assert first == second
    assert first == ([2.8], [7.2])


def test_analyzer_returns_required_analysis_fields():
    analysis = analyze_pair_from_candles(
        "EUR/USD", "1h", make_candles([float(value) for value in range(1, 61)]), "trend"
    )
    payload = analysis.model_dump()

    assert payload.keys() >= {
        "pair", "timeframe", "direction", "score", "status", "setup", "trend",
        "swing_high", "swing_low", "fib_levels", "support_zones",
        "resistance_zones", "summary",
    }
    assert analysis.direction.value == "long"
    assert analysis.trend == "bullish"
