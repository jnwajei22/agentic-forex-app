from __future__ import annotations

from datetime import date
from typing import Any, Literal
from urllib.parse import quote

from app.auth.identity import get_current_user_sub
from app.brokers.tradelocker.adapter import get_tradelocker_adapter
from app.brokers.tradelocker.client import TradeLockerError
from app.config.settings import settings
from app.models.orders import OrderRequest
from app.services.market_data.librarian import (
    get_macro_results,
    get_market_series,
    macro_catalog,
    watchlist_market_data,
)
from app.services.providers.errors import ProviderError
from app.services.providers.finnhub import FinnhubClient, capability_status
from app.services.providers.fred import FredClient
from app.services.trading.previews import create_order_preview
from app.services.watchlist import get_default_watchlist
from app.storage.brokers import BrokerRepository, BrokerStorageError


def _setup_url() -> str:
    return (
        f"{settings.frontend_origin.rstrip('/')}/connect-tradelocker?source=chatgpt&returnTo="
        f"{quote(settings.chatgpt_return_url, safe='')}"
    )


def _setup_required() -> dict[str, Any]:
    return {
        "status": "setup_required", "message": "TradeLocker setup required.",
        "setup_url": _setup_url(),
        "instruction": (
            "Open the setup URL, connect TradeLocker using the same login account, "
            "then return to ChatGPT and run this again."
        ),
    }


def _missing_user_connection() -> dict[str, Any] | None:
    user_sub = get_current_user_sub()
    if not user_sub:
        return None
    try:
        status = BrokerRepository().status(user_sub)
    except BrokerStorageError as exc:
        return {"status": "error", "error": "broker_storage_error", "message": str(exc)}
    return _setup_required() if status["status"] == "not_connected" else None


def _tradelocker_error(exc: TradeLockerError) -> dict[str, Any]:
    if exc.code == "setup_required" or exc.status_code in {401, 403}:
        return _setup_required()
    return exc.as_dict()


def _date(value: str | None, name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name} must use YYYY-MM-DD format.") from None


def get_tradelocker_connection_status() -> dict[str, Any]:
    """Return the current user's sanitized, isolated TradeLocker connection status."""
    user_sub = get_current_user_sub()
    if not user_sub:
        return {"connected": False, "selected_account": False, **_setup_required()}
    try:
        status = BrokerRepository().status(user_sub)
    except BrokerStorageError as exc:
        return {"connected": False, "selected_account": False, "status": "error", "message": str(exc)}
    if status["status"] == "not_connected":
        return {"connected": False, "selected_account": False, **_setup_required()}
    selected = status["status"] == "ready"
    result: dict[str, Any] = {"connected": True, "selected_account": selected, "status": status["status"]}
    if selected:
        result["selected_account_summary"] = status["selected_account"]
    return result


def get_my_broker_connection_status() -> dict[str, Any]:
    """Deprecated compatibility alias for get_tradelocker_connection_status."""
    return get_tradelocker_connection_status()


def get_forex_watchlist() -> list[dict[str, Any]]:
    """Return configured forex symbols without analysis or ranking."""
    return [item.model_dump(mode="json") for item in get_default_watchlist()]


async def get_market_candles(
    symbol: str,
    timeframe: str,
    source: Literal["tradelocker", "finnhub"] = "tradelocker",
    lookback: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    max_candles: int | None = None,
) -> dict[str, Any]:
    """Return canonical provider-identified OHLCV for client-side charting and analysis; explicit dates override lookback."""
    if source == "tradelocker":
        missing = _missing_user_connection()
        if missing:
            return missing
    try:
        result = await get_market_series(
            symbol=symbol, timeframe=timeframe, source=source, lookback=lookback,
            start_time=start_time, end_time=end_time, max_candles=max_candles,
        )
        return result.model_dump(mode="json")
    except ProviderError as exc:
        return exc.as_dict()
    except TradeLockerError as exc:
        return _tradelocker_error(exc)
    except ValueError as exc:
        return ProviderError(source, "invalid_request", str(exc)).as_dict()


async def get_watchlist_market_data(
    symbols: list[str], timeframe: str, lookback: int = 100,
    fields: list[str] | None = None, max_symbols: int = 10,
) -> dict[str, Any]:
    """Return bounded TradeLocker series for client-side screening without ranking or recommendations."""
    missing = _missing_user_connection()
    if missing:
        return missing
    return await watchlist_market_data(symbols, timeframe, lookback, fields, max_symbols)


async def get_economic_calendar(
    start_date: str, end_date: str, countries: list[str] | None = None,
    currencies: list[str] | None = None, limit: int = 100,
) -> dict[str, Any]:
    """Return normalized Finnhub economic events when the configured plan permits access."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500.")
    client = FinnhubClient()
    try:
        events = await client.economic_calendar(_date(start_date, "start_date"), _date(end_date, "end_date"), limit)
        country_set = {value.upper() for value in countries or []}
        currency_set = {value.upper() for value in currencies or []}
        events = [event for event in events if (not country_set or (event.country or "").upper() in country_set) and (not currency_set or (event.currency or "").upper() in currency_set)]
        return {"source": "finnhub", "capability": "economic_calendar", "events": [event.model_dump(mode="json") for event in events[:limit]]}
    except ProviderError as exc:
        return exc.as_dict()
    finally:
        await client.aclose()


async def get_market_news(
    symbols: list[str] | None = None, currencies: list[str] | None = None,
    category: str = "forex", start_date: str | None = None,
    end_date: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """Return bounded Finnhub headlines and concise summaries, never full articles."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    start = _date(start_date, "start_date")
    end = _date(end_date, "end_date")
    client = FinnhubClient()
    try:
        items = await client.market_news(category, limit=100)
        wanted = {value.upper() for value in (symbols or []) + (currencies or [])}
        filtered = []
        for item in items:
            published = item.published_at.date()
            if start and published < start or end and published > end:
                continue
            searchable = {value.upper() for value in item.related_symbols}
            searchable.update(item.headline.upper().split())
            if wanted and not any(value in searchable or value in item.headline.upper() for value in wanted):
                continue
            filtered.append(item)
        return {"source": "finnhub", "capability": "market_news", "items": [item.model_dump(mode="json") for item in filtered[:limit]]}
    except ProviderError as exc:
        return exc.as_dict()
    finally:
        await client.aclose()


async def search_macro_series(query: str, limit: int = 25) -> dict[str, Any]:
    """Search official FRED series metadata; no series identifiers are fabricated."""
    client = FredClient()
    try:
        results = await client.search_series(query, limit)
        return {"source": "fred", "results": [item.model_dump(mode="json") for item in results]}
    except ProviderError as exc:
        return exc.as_dict()
    finally:
        await client.aclose()


async def get_macro_series(
    series_ids: list[str], observation_start: str | None = None,
    observation_end: str | None = None, realtime_start: str | None = None,
    realtime_end: str | None = None, limit: int = 1000,
) -> dict[str, Any]:
    """Return official FRED metadata and observations with real-time periods preserved."""
    if not 1 <= limit <= 5000 or not 1 <= len(series_ids) <= 10:
        raise ValueError("Request up to 10 series and 1 to 5000 observations per series.")
    try:
        results = await get_macro_results(
            series_ids, _date(observation_start, "observation_start"),
            _date(observation_end, "observation_end"), _date(realtime_start, "realtime_start"),
            _date(realtime_end, "realtime_end"), limit,
        )
        return {"source": "fred", "series": [item.model_dump(mode="json") for item in results]}
    except ProviderError as exc:
        return exc.as_dict()


async def get_macro_release_calendar(
    start_date: str | None = None, end_date: str | None = None, limit: int = 100,
) -> dict[str, Any]:
    """Return official FRED release dates."""
    client = FredClient()
    try:
        dates = await client.release_dates(_date(start_date, "start_date"), _date(end_date, "end_date"), limit)
        return {"source": "fred", "release_dates": [item.model_dump(mode="json") for item in dates]}
    except ProviderError as exc:
        return exc.as_dict()
    finally:
        await client.aclose()


async def get_forex_research_bundle(
    symbol: str, timeframe: str, lookback: int | None = None,
    start_time: str | None = None, end_time: str | None = None,
    include_quote: bool = True, include_account_exposure: bool = True,
    include_calendar: bool = True, include_news: bool = True, include_macro: bool = True,
    news_limit: int = 10, event_limit: int = 20,
    macro_series_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Retrieve bounded, separate forex research inputs without analysis, prediction, or recommendations."""
    market = await get_market_candles(symbol, timeframe, "tradelocker", lookback, start_time, end_time, settings.market_data_max_response_candles)
    if market.get("status") in {"error", "setup_required"}:
        return market
    warnings: list[str] = []
    quote_data: Any = None
    exposure: Any = None
    if include_quote:
        quote_data = await get_tradelocker_quote(symbol)
    if include_account_exposure:
        exposure = await get_open_positions()
    calendar: Any = None
    news: Any = None
    macro: Any = None
    today = date.today().isoformat()
    if include_calendar:
        calendar = await get_economic_calendar(today, today, limit=event_limit)
        if calendar.get("status") == "error":
            warnings.append(calendar["message"])
    if include_news:
        news = await get_market_news(symbols=[symbol], limit=news_limit)
        if news.get("status") == "error":
            warnings.append(news["message"])
    if include_macro:
        ids = macro_series_ids or macro_catalog().currencies.get(symbol[:3].upper(), []) + macro_catalog().currencies.get(symbol[-3:].upper(), [])
        macro = await get_macro_series(list(dict.fromkeys(ids))[:10], limit=500) if ids else {"source": "fred", "series": [], "warning": "No macro series IDs were requested or configured."}
        if macro.get("status") == "error":
            warnings.append(macro["message"])
    return {
        "symbol": symbol, "market": market, "quote": quote_data,
        "account_exposure": exposure, "economic_calendar": calendar,
        "news": news, "macro": macro, "warnings": warnings,
        "sources": {"execution": "tradelocker", "calendar": "finnhub", "news": "finnhub", "macro": "fred"},
    }


async def get_account_status() -> dict[str, Any]:
    """Return current TradeLocker account state without cross-user caching."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().get_account()
    except TradeLockerError as exc:
        return _tradelocker_error(exc)


async def get_open_positions() -> list[dict[str, Any]] | dict[str, Any]:
    """Return current TradeLocker positions without shared caching."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().get_open_positions()
    except TradeLockerError as exc:
        return _tradelocker_error(exc)


async def get_pending_orders() -> dict[str, Any] | list[Any]:
    """Return current TradeLocker pending orders when the endpoint is available."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().client.get_orders()
    except TradeLockerError as exc:
        return _tradelocker_error(exc)


async def get_trade_history(limit: int = 100) -> dict[str, Any]:
    """Report TradeLocker trade-history capability without inventing an undocumented route."""
    missing = _missing_user_connection()
    if missing:
        return missing
    return {
        "status": "error", "provider": "tradelocker",
        "error": "capability_unavailable",
        "message": "Trade history is not exposed by the currently verified TradeLocker client routes.",
        "capability": "trade_history", "retryable": False,
        "requested_limit": limit,
    }


async def get_tradelocker_config() -> dict[str, Any] | list[Any]:
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().client.get_config()
    except TradeLockerError as exc:
        return _tradelocker_error(exc)


async def get_tradelocker_accounts() -> dict[str, Any]:
    """Discover sanitized TradeLocker accounts before account selection."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().client.get_accounts()
    except TradeLockerError as exc:
        return _tradelocker_error(exc)


async def get_tradelocker_symbols() -> dict[str, Any] | list[Any]:
    """Return symbols for the connected TradeLocker account."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().client.get_symbols()
    except TradeLockerError as exc:
        return _tradelocker_error(exc)


async def get_tradelocker_quote(symbol: str) -> dict[str, Any] | list[Any]:
    """Return the authoritative TradeLocker execution quote for a symbol."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().get_quote(symbol)
    except TradeLockerError as exc:
        return _tradelocker_error(exc)


def review_forex_order(order_request: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic risk-reviewed preview; never submit an order."""
    return create_order_preview(OrderRequest(**order_request)).model_dump(mode="json")


def set_kill_switch(enabled: bool, reason: str) -> dict[str, Any]:
    """Enable the kill switch; remote callers cannot disable it."""
    if not reason.strip():
        raise ValueError("A reason is required to change the kill switch.")
    if not enabled:
        settings.kill_switch_enabled = True
        return {"changed": False, "kill_switch_enabled": True, "reason": reason, "message": "Remote MCP callers cannot disable the kill switch."}
    changed = not settings.kill_switch_enabled
    settings.kill_switch_enabled = True
    return {"changed": changed, "kill_switch_enabled": True, "reason": reason, "message": "Kill switch enabled."}


def get_provider_capabilities() -> dict[str, Any]:
    """Return configured public-provider capability state without exposing secrets."""
    return {"finnhub_enabled": settings.finnhub_enabled, "finnhub": capability_status(), "fred_enabled": settings.fred_enabled}


# Temporary compatibility aliases used by the current ChatGPT onboarding integration.
async def get_my_tradelocker_accounts() -> dict[str, Any]:
    """Deprecated alias for get_tradelocker_accounts."""
    return await get_tradelocker_accounts()


async def get_my_tradelocker_account_status() -> dict[str, Any]:
    """Deprecated alias for get_account_status."""
    return await get_account_status()


async def get_my_tradelocker_symbols() -> dict[str, Any] | list[Any]:
    """Deprecated alias for get_tradelocker_symbols."""
    return await get_tradelocker_symbols()


async def get_my_tradelocker_quote(symbol: str) -> dict[str, Any] | list[Any]:
    """Deprecated alias for get_tradelocker_quote."""
    return await get_tradelocker_quote(symbol)


async def get_my_tradelocker_candles(
    symbol: str, timeframe: str, lookback: int | None = None,
    start_time: str | None = None, end_time: str | None = None,
) -> dict[str, Any]:
    """Deprecated alias for get_market_candles using TradeLocker."""
    return await get_market_candles(symbol, timeframe, "tradelocker", lookback, start_time, end_time)
