from typing import Any

from app.brokers.tradelocker.adapter import get_tradelocker_adapter
from app.brokers.tradelocker.client import TradeLockerError
from app.config.settings import settings
from app.models.market import Candle
from app.services.market_data.mock_provider import DEFAULT_MOCK_CANDLE_PATH, load_mock_candles


def _history_candles(payload: Any) -> list[Candle]:
    if isinstance(payload, list):
        return [Candle.model_validate(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict) or payload.get("status") == "not_implemented":
        return []
    source = payload.get("d", payload.get("data", payload))
    if isinstance(source, dict) and "barDetails" in source:
        return _history_candles(source["barDetails"])
    if not isinstance(source, dict):
        return []
    columns = {
        "timestamp": source.get("t", source.get("time", [])),
        "open": source.get("o", source.get("open", [])),
        "high": source.get("h", source.get("high", [])),
        "low": source.get("l", source.get("low", [])),
        "close": source.get("c", source.get("close", [])),
        "volume": source.get("v", source.get("volume", [])),
    }
    required = [columns[name] for name in ("timestamp", "open", "high", "low", "close")]
    if not all(isinstance(column, list) for column in required):
        return []
    candles = []
    for index in range(min(len(column) for column in required)):
        timestamp = columns["timestamp"][index]
        if isinstance(timestamp, (int, float)):
            timestamp = timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
        volume = columns["volume"]
        candles.append(
            Candle(
                timestamp=timestamp,
                open=columns["open"][index],
                high=columns["high"][index],
                low=columns["low"][index],
                close=columns["close"][index],
                volume=volume[index] if isinstance(volume, list) and index < len(volume) else None,
            )
        )
    return sorted(candles, key=lambda candle: candle.timestamp)


async def get_candles(pair: str, timeframe: str, lookback: int = 300) -> list[Candle]:
    provider = settings.market_data_provider.lower()
    if provider == "mock":
        return load_mock_candles(DEFAULT_MOCK_CANDLE_PATH).get(pair, [])[-lookback:]
    if provider == "tradelocker":
        payload = await get_tradelocker_adapter().get_candles(pair, timeframe, lookback)
        candles = _history_candles(payload)
        if not candles:
            raise TradeLockerError(
                "get_candles", "TradeLocker returned no usable candle data.", code="no_data"
            )
        return candles
    raise ValueError("MARKET_DATA_PROVIDER must be 'mock' or 'tradelocker'.")


def _quote_value(payload: Any, names: tuple[str, ...]) -> float | None:
    if isinstance(payload, dict):
        for name in names:
            value = payload.get(name)
            if isinstance(value, (int, float)):
                return float(value)
        for value in payload.values():
            found = _quote_value(value, names)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _quote_value(value, names)
            if found is not None:
                return found
    return None


async def get_spread(pair: str) -> float | None:
    """Return ask-minus-bid when the selected provider exposes a usable quote."""
    if settings.market_data_provider.lower() != "tradelocker":
        return None
    try:
        payload = await get_tradelocker_adapter().get_quote(pair)
    except TradeLockerError:
        return None
    ask = _quote_value(payload, ("ask", "askPrice", "ap"))
    bid = _quote_value(payload, ("bid", "bidPrice", "bp"))
    if ask is None or bid is None or ask < bid:
        return None
    return ask - bid
