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


def calculate_ema_series(values: Sequence[float], period: int) -> list[float | None]:
    """Return an EMA series aligned to the input, with unavailable values as None."""
    if period <= 0:
        raise ValueError("EMA period must be positive.")
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    ema = sum(values[:period]) / period
    result[period - 1] = ema
    multiplier = 2 / (period + 1)
    for index in range(period, len(values)):
        ema = ((values[index] - ema) * multiplier) + ema
        result[index] = ema
    return result


def calculate_rsi(values: Sequence[float], period: int = 14) -> float | None:
    """Return Wilder's latest RSI value."""
    if period <= 0:
        raise ValueError("RSI period must be positive.")
    if len(values) < period + 1:
        return None
    changes = [current - previous for previous, current in zip(values, values[1:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for index in range(period, len(changes)):
        average_gain = ((average_gain * (period - 1)) + gains[index]) / period
        average_loss = ((average_loss * (period - 1)) + losses[index]) / period
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def calculate_atr(candles: Sequence[Candle], period: int = 14) -> float | None:
    """Return Wilder's latest Average True Range."""
    if period <= 0:
        raise ValueError("ATR period must be positive.")
    if len(candles) < period + 1:
        return None
    true_ranges = []
    for previous, current in zip(candles, candles[1:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    atr = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        atr = ((atr * (period - 1)) + true_range) / period
    return atr
