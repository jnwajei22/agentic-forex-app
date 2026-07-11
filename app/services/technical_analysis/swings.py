from app.models.market import Candle

def find_pivot_swings(candles: list[Candle], window: int = 3) -> tuple[Candle | None, Candle | None]:
    if window < 1:
        raise ValueError("Pivot window must be at least 1.")
    if not candles:
        return None, None
    if len(candles) < (window * 2 + 1):
        return min(candles, key=lambda candle: candle.low), max(
            candles, key=lambda candle: candle.high
        )

    swing_highs = []
    swing_lows = []

    for i in range(window, len(candles) - window):
        center = candles[i]
        neighbors = candles[i-window:i] + candles[i+1:i+window+1]

        if all(center.high > c.high for c in neighbors):
            swing_highs.append(center)

        if all(center.low < c.low for c in neighbors):
            swing_lows.append(center)

    last_high = swing_highs[-1] if swing_highs else max(
        candles, key=lambda candle: candle.high
    )
    last_low = swing_lows[-1] if swing_lows else min(
        candles, key=lambda candle: candle.low
    )
    return last_low, last_high
