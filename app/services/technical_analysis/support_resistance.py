from app.models.market import Candle


def _pivot_prices(candles: list[Candle], window: int, attribute: str) -> list[float]:
    prices: list[float] = []
    for index in range(window, len(candles) - window):
        price = getattr(candles[index], attribute)
        neighbors = candles[index - window:index] + candles[index + 1:index + window + 1]
        neighbor_prices = [getattr(candle, attribute) for candle in neighbors]
        if attribute == "low" and price < min(neighbor_prices):
            prices.append(price)
        if attribute == "high" and price > max(neighbor_prices):
            prices.append(price)
    return prices


def detect_support_resistance(
    candles: list[Candle], window: int = 3, max_zones: int = 3
) -> tuple[list[float], list[float]]:
    """Return deterministic nearby pivot zones, nearest to the latest close first."""
    if not candles:
        return [], []
    if window < 1:
        raise ValueError("Pivot window must be at least 1.")

    supports = _pivot_prices(candles, window, "low")
    resistances = _pivot_prices(candles, window, "high")
    close = candles[-1].close
    supports = [price for price in supports if price <= close]
    resistances = [price for price in resistances if price >= close]
    supports = supports or [min(candle.low for candle in candles)]
    resistances = resistances or [max(candle.high for candle in candles)]

    def ranked(prices: list[float]) -> list[float]:
        unique = sorted(set(round(price, 6) for price in prices))
        return sorted(unique, key=lambda price: (abs(price - close), price))[:max_zones]

    return ranked(supports), ranked(resistances)
