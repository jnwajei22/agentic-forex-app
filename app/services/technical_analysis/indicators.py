from collections.abc import Sequence

from app.models.market import Candle


def calculate_ema(values: Sequence[float], period: int) -> float | None:
    """Return the latest EMA, seeded with the first full-period SMA."""
    if period <= 0:
        raise ValueError("EMA period must be positive.")
    if len(values) < period:
        return None

    ema = sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    for value in values[period:]:
        ema = ((value - ema) * multiplier) + ema
    return ema


def candle_emas(candles: Sequence[Candle]) -> dict[str, float | None]:
    closes = [candle.close for candle in candles]
    return {
        "ema_20": calculate_ema(closes, 20),
        "ema_50": calculate_ema(closes, 50),
        "ema_200": calculate_ema(closes, 200),
    }
