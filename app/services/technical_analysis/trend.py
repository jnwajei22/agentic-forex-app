from app.models.market import Candle

def classify_trend(candles: list[Candle]) -> str:
    # Placeholder. Implement EMA 20/50/200 + structure/slope.
    if len(candles) < 200:
        return "neutral"
    return "neutral"
