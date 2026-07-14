from typing import Any

from app.brokers.tradelocker.adapter import get_tradelocker_adapter
from app.brokers.tradelocker.client import TradeLockerError
from app.config.settings import settings
from app.models.market import Candle
from app.services.market_data.mock_provider import DEFAULT_MOCK_CANDLE_PATH, load_mock_candles
from app.services.market_data.candles import normalize_history_payload
from app.services.market_data.history import PaginatedCandleResult


def _history_candles(payload: Any) -> list[Candle]:
    if isinstance(payload, PaginatedCandleResult):
        return payload.candles
    candles, _ = normalize_history_payload(payload)
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
