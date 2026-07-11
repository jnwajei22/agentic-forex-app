def calculate_fib_levels(swing_low: float, swing_high: float, direction: str) -> dict:
    if swing_high <= swing_low:
        raise ValueError("swing_high must be greater than swing_low")

    diff = swing_high - swing_low

    if direction == "long":
        return {
            "0.236": swing_high - diff * 0.236,
            "0.382": swing_high - diff * 0.382,
            "0.500": swing_high - diff * 0.500,
            "0.618": swing_high - diff * 0.618,
            "0.786": swing_high - diff * 0.786,
            "1.000": swing_low,
            "1.272": swing_high + diff * 0.272,
            "1.618": swing_high + diff * 0.618,
        }

    if direction == "short":
        return {
            "0.236": swing_low + diff * 0.236,
            "0.382": swing_low + diff * 0.382,
            "0.500": swing_low + diff * 0.500,
            "0.618": swing_low + diff * 0.618,
            "0.786": swing_low + diff * 0.786,
            "1.000": swing_high,
            "1.272": swing_low - diff * 0.272,
            "1.618": swing_low - diff * 0.618,
        }

    raise ValueError("direction must be 'long' or 'short'")
