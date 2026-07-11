from typing import Any

from app.brokers.tradelocker.adapter import get_tradelocker_adapter
from app.brokers.tradelocker.client import TradeLockerError
from app.config.settings import settings
from app.models.orders import OrderRequest
from app.services.charting.generator import generate_forex_chart
from app.services.market_data.service import get_candles
from app.services.scanner import scan_forex_watchlist as scan_watchlist
from app.services.technical_analysis.analyzer import analyze_pair_from_candles
from app.services.trading.previews import create_order_preview
from app.services.watchlist import get_default_watchlist, is_allowed_pair, normalize_pair


def _tradelocker_configured() -> bool:
    return all(
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
) -> list[dict[str, Any]]:
    """Analyze local mocked candles and return the highest-ranked setups."""
    if not timeframes:
        raise ValueError("At least one timeframe is required.")
    if max_results < 1:
        raise ValueError("max_results must be at least 1.")

    results = []
    for timeframe in timeframes:
        candle_data = {
            item.pair: await get_candles(item.pair, timeframe, 300)
            for item in get_default_watchlist()
        }
        results.extend(scan_watchlist(candle_data, timeframe, strategy_profile))
    ranked = sorted(results, key=lambda setup: setup.score, reverse=True)[:max_results]
    return [setup.model_dump(mode="json") for setup in ranked]


async def generate_chart(
    pair: str,
    timeframe: str,
    overlays: list[str],
    entry: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict[str, Any]:
    """Generate a local PNG analysis chart from mocked candles."""
    normalized_pair = normalize_pair(pair)
    if not is_allowed_pair(normalized_pair):
        raise ValueError(f"Unknown forex pair: {pair}")
    candles = await get_candles(normalized_pair, timeframe, 300)
    if not candles:
        raise ValueError(f"No mocked candles found for pair: {normalized_pair}")
    analysis = analyze_pair_from_candles(normalized_pair, timeframe, candles, "chart")
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
            return exc.as_dict()
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
            return exc.as_dict()
    return []


async def get_tradelocker_config() -> dict[str, Any] | list[Any]:
    """Return TradeLocker's read-only API configuration and field definitions."""
    try:
        return await get_tradelocker_adapter().client.get_config()
    except TradeLockerError as exc:
        return exc.as_dict()


async def get_tradelocker_symbols() -> dict[str, Any] | list[Any]:
    """Return instruments available to the configured TradeLocker account."""
    try:
        return await get_tradelocker_adapter().client.get_symbols()
    except TradeLockerError as exc:
        return exc.as_dict()


async def get_tradelocker_quote(symbol: str) -> dict[str, Any] | list[Any]:
    """Return a current read-only TradeLocker quote for a symbol."""
    try:
        return await get_tradelocker_adapter().get_quote(symbol)
    except TradeLockerError as exc:
        return exc.as_dict()


async def get_tradelocker_candles(
    symbol: str, timeframe: str, lookback: int = 300
) -> dict[str, Any] | list[Any]:
    """Return raw read-only TradeLocker historical bars for a symbol."""
    try:
        return await get_tradelocker_adapter().get_candles(symbol, timeframe, lookback)
    except TradeLockerError as exc:
        return exc.as_dict()


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
