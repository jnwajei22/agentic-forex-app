from app.models.market import Candle
from app.services.technical_analysis.indicators import candle_emas

def classify_trend(candles: list[Candle]) -> str:
    if len(candles) < 3:
        return "neutral"

    emas = candle_emas(candles)
    close = candles[-1].close
    midpoint = max(1, len(candles) // 2)
    earlier = candles[:midpoint]
    recent = candles[midpoint:]
    higher_structure = (
        max(c.high for c in recent) > max(c.high for c in earlier)
        and min(c.low for c in recent) > min(c.low for c in earlier)
    )
    lower_structure = (
        max(c.high for c in recent) < max(c.high for c in earlier)
        and min(c.low for c in recent) < min(c.low for c in earlier)
    )

    ema_20, ema_50 = emas["ema_20"], emas["ema_50"]
    if ema_20 is not None and ema_50 is not None:
        if close > ema_20 > ema_50 and higher_structure:
            return "bullish"
        if close < ema_20 < ema_50 and lower_structure:
            return "bearish"
        if abs(ema_20 - ema_50) / max(abs(close), 1e-12) < 0.001:
            return "choppy"

    if higher_structure and close > candles[0].close:
        return "bullish"
    if lower_structure and close < candles[0].close:
        return "bearish"
    if max(c.high for c in candles) - min(c.low for c in candles) > 0:
        return "choppy"
    return "neutral"
