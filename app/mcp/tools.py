from typing import Any
from urllib.parse import quote

from app.brokers.tradelocker.adapter import get_tradelocker_adapter
from app.brokers.tradelocker.client import TradeLockerError
from app.auth.identity import get_current_user_sub
from app.config.settings import settings
from app.models.orders import OrderRequest
from app.services.charting.generator import generate_forex_chart
from app.services.market_data.service import get_candles, get_spread
from app.services.multi_timeframe import analyze_multi_timeframe_report
from app.services.scanner import scan_forex_watchlist as scan_watchlist
from app.services.technical_analysis.analyzer import analyze_pair_from_candles
from app.services.trading.previews import create_order_preview
from app.services.watchlist import get_default_watchlist, is_allowed_pair, normalize_pair
from app.storage.brokers import BrokerRepository, BrokerStorageError


def _setup_url() -> str:
    origin = settings.frontend_origin.rstrip("/")
    return (
        f"{origin}/connect-tradelocker?source=chatgpt&returnTo="
        f"{quote(settings.chatgpt_return_url, safe='')}"
    )


def _setup_required() -> dict[str, Any]:
    return {
        "status": "setup_required",
        "message": "TradeLocker setup required.",
        "setup_url": _setup_url(),
        "instruction": (
            "Open the setup URL, connect TradeLocker using the same login account, "
            "then return to ChatGPT and run this again."
        ),
    }


def _tradelocker_error_response(exc: TradeLockerError) -> dict[str, Any]:
    if exc.code == "setup_required" or exc.status_code in {401, 403}:
        return _setup_required()
    return exc.as_dict()


def _missing_user_connection() -> dict[str, Any] | None:
    user_sub = get_current_user_sub()
    if not user_sub:
        return None
    try:
        status = BrokerRepository().status(user_sub)
    except BrokerStorageError as exc:
        return {"status": "error", "error": "broker_storage_error", "message": str(exc)}
    return _setup_required() if status["status"] == "setup_required" else None


def get_tradelocker_connection_status() -> dict[str, Any]:
    """Return the current user's sanitized TradeLocker connection status."""
    user_sub = get_current_user_sub()
    if not user_sub:
        return {
            "connected": False,
            "selected_account": False,
            **_setup_required(),
        }
    try:
        status = BrokerRepository().status(user_sub)
    except BrokerStorageError as exc:
        return {"connected": False, "selected_account": False, "status": "error", "message": str(exc)}
    if status["status"] == "setup_required":
        return {"connected": False, "selected_account": False, **_setup_required()}
    selected = status["status"] == "connected"
    result: dict[str, Any] = {
        "connected": True,
        "selected_account": selected,
        "status": status["status"],
    }
    if selected:
        result["selected_account_summary"] = {
            "server": status["server"],
            "account_id": status["accountId"],
            "account_number": status["accNum"],
        }
    return result


def get_my_broker_connection_status() -> dict[str, Any]:
    """Backward-compatible alias for TradeLocker connection status."""
    return get_tradelocker_connection_status()


def _tradelocker_configured() -> bool:
    return bool(get_current_user_sub()) or settings.allow_env_broker_fallback and all(
        (
            settings.tradelocker_username,
            settings.tradelocker_password,
            settings.tradelocker_server,
            settings.tradelocker_account_id,
            settings.tradelocker_account_number,
        )
    )


def get_forex_watchlist() -> list[dict[str, Any]]:
    """Return the configured forex pairs available to mocked analysis."""
    return [item.model_dump(mode="json") for item in get_default_watchlist()]


async def scan_forex_watchlist(
    timeframes: list[str],
    strategy_profile: str = "default",
    max_results: int = 10,
) -> dict[str, Any]:
    """Rank trend clarity and report missing data, spread availability, and weak setups."""
    if settings.market_data_provider.lower() == "tradelocker":
        missing = _missing_user_connection()
        if missing:
            return missing
    if not timeframes:
        raise ValueError("At least one timeframe is required.")
    if max_results < 1:
        raise ValueError("max_results must be at least 1.")

    results = []
    warnings = []
    for timeframe in timeframes:
        candle_data = {}
        spreads = {}
        for item in get_default_watchlist():
            try:
                candles = await get_candles(item.pair, timeframe, 300)
            except (TradeLockerError, OSError, ValueError) as exc:
                candles = []
                warnings.append(f"Missing data for {item.pair} {timeframe}: {exc}")
            if len(candles) < 2:
                warnings.append(f"Missing data for {item.pair} {timeframe}.")
                continue
            candle_data[item.pair] = candles
            spreads[item.pair] = await get_spread(item.pair)
        results.extend(
            scan_watchlist(candle_data, timeframe, strategy_profile, spreads=spreads)
        )
    ranked = sorted(results, key=lambda setup: setup.score, reverse=True)[:max_results]
    strongest = sorted(results, key=lambda setup: setup.trend_clarity, reverse=True)[:5]
    serialized = [setup.model_dump(mode="json") for setup in ranked]
    return {
        "results": serialized,
        "strongest_pairs": [
            {
                "pair": setup.pair,
                "timeframe": setup.timeframe,
                "trend": setup.trend,
                "trend_clarity": setup.trend_clarity,
            }
            for setup in strongest
        ],
        "warnings": list(dict.fromkeys(warnings)),
        "summary": (
            "Ranked analysis candidates are available; review spread warnings and context."
            if serialized
            else "No trade / no clean setup: usable candle data is unavailable."
        ),
    }


async def generate_chart(
    pair: str,
    timeframe: str,
    overlays: list[str] | None = None,
    entry: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict[str, Any]:
    """Generate a local PNG analysis chart from mocked candles."""
    if settings.market_data_provider.lower() == "tradelocker":
        missing = _missing_user_connection()
        if missing:
            return missing
    normalized_pair = normalize_pair(pair)
    if not is_allowed_pair(normalized_pair):
        raise ValueError(f"Unknown forex pair: {pair}")
    candles = await get_candles(normalized_pair, timeframe, 300)
    if not candles:
        raise ValueError(f"No mocked candles found for pair: {normalized_pair}")
    spread = await get_spread(normalized_pair)
    analysis = analyze_pair_from_candles(
        normalized_pair, timeframe, candles, "chart", spread=spread
    )
    metadata = generate_forex_chart(
        normalized_pair,
        timeframe,
        candles,
        analysis,
        overlays,
        entry,
        stop_loss,
        take_profit,
    )
    metadata["generated_at"] = metadata["generated_at"].isoformat()
    return metadata


async def analyze_multi_timeframe(
    pair: str, timeframes: list[str] | None = None
) -> dict[str, Any]:
    """Analyze trend, levels, Fibonacci, RSI, ATR, and confluence across timeframes."""
    return await analyze_multi_timeframe_report(
        pair, timeframes or ["15m", "1h", "4h"]
    )


async def generate_multi_timeframe_report(pair: str) -> dict[str, Any]:
    """Generate the standard 15m, 1h, and 4h read-only analysis report."""
    return await analyze_multi_timeframe_report(pair, ["15m", "1h", "4h"])


def review_forex_order(order_request: dict[str, Any]) -> dict[str, Any]:
    """Create a risk-checked preview only; this never submits an order."""
    order = OrderRequest(**order_request)
    preview = create_order_preview(order)
    return preview.model_dump(mode="json")


async def get_account_status() -> dict[str, Any]:
    """Return paper status or read-only TradeLocker account state."""
    if _tradelocker_configured():
        try:
            return await get_tradelocker_adapter().get_account()
        except TradeLockerError as exc:
            return _tradelocker_error_response(exc)
    return {
        "environment": "paper",
        "app_env": settings.app_env,
        "live_trading_enabled": False,
        "kill_switch_enabled": settings.kill_switch_enabled,
        "broker_connected": False,
        "message": "Paper/development status only. No live broker is connected.",
    }


async def get_open_positions() -> list[dict[str, Any]] | dict[str, Any]:
    """Return paper positions or read-only TradeLocker positions."""
    if _tradelocker_configured():
        try:
            return await get_tradelocker_adapter().get_open_positions()
        except TradeLockerError as exc:
            return _tradelocker_error_response(exc)
    return []


async def get_tradelocker_config() -> dict[str, Any] | list[Any]:
    """Return account-specific TradeLocker config. Run get_tradelocker_accounts first."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().client.get_config()
    except TradeLockerError as exc:
        return _tradelocker_error_response(exc)


async def get_tradelocker_accounts() -> dict[str, Any]:
    """Discover TradeLocker accounts using login credentials only.

    Run this first without an account ID or account number. Copy an accountId and
    accNum from the sanitized result into TRADELOCKER_ACCOUNT_ID and
    TRADELOCKER_ACCOUNT_NUMBER in .env, then restart the server before calling
    account-specific TradeLocker tools.
    """
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().client.get_accounts()
    except TradeLockerError as exc:
        return _tradelocker_error_response(exc)


async def get_tradelocker_symbols() -> dict[str, Any] | list[Any]:
    """Return instruments available to the configured TradeLocker account."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().client.get_symbols()
    except TradeLockerError as exc:
        return _tradelocker_error_response(exc)


async def get_tradelocker_quote(symbol: str) -> dict[str, Any] | list[Any]:
    """Return a current read-only TradeLocker quote for a symbol."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().get_quote(symbol)
    except TradeLockerError as exc:
        return _tradelocker_error_response(exc)


async def get_tradelocker_candles(
    symbol: str, timeframe: str, lookback: int = 300
) -> dict[str, Any] | list[Any]:
    """Return raw read-only TradeLocker historical bars for a symbol."""
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().get_candles(symbol, timeframe, lookback)
    except TradeLockerError as exc:
        return _tradelocker_error_response(exc)


async def get_my_tradelocker_accounts() -> dict[str, Any]:
    return await get_tradelocker_accounts()


async def get_my_tradelocker_account_status() -> dict[str, Any]:
    missing = _missing_user_connection()
    if missing:
        return missing
    try:
        return await get_tradelocker_adapter().get_account()
    except TradeLockerError as exc:
        return _tradelocker_error_response(exc)


async def get_my_tradelocker_symbols() -> dict[str, Any] | list[Any]:
    return await get_tradelocker_symbols()


async def get_my_tradelocker_quote(symbol: str) -> dict[str, Any] | list[Any]:
    return await get_tradelocker_quote(symbol)


async def get_my_tradelocker_candles(
    symbol: str, timeframe: str, lookback: int = 300
) -> dict[str, Any] | list[Any]:
    return await get_tradelocker_candles(symbol, timeframe, lookback)


def get_trade_log(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return the paper journal; persistence and filtering are not implemented yet."""
    return []


def set_kill_switch(enabled: bool, reason: str) -> dict[str, Any]:
    """Enable the kill switch. Remote MCP callers cannot disable it."""
    if not reason.strip():
        raise ValueError("A reason is required to change the kill switch.")
    if not enabled:
        settings.kill_switch_enabled = True
        return {
            "changed": False,
            "kill_switch_enabled": True,
            "reason": reason,
            "message": "Remote MCP callers cannot disable the kill switch.",
        }
    changed = not settings.kill_switch_enabled
    settings.kill_switch_enabled = True
    return {
        "changed": changed,
        "kill_switch_enabled": True,
        "reason": reason,
        "message": "Kill switch enabled. Order previews will be rejected.",
    }
