from typing import Any

from app.config.settings import settings
from app.models.orders import OrderRequest
from app.services.charting.generator import generate_forex_chart
from app.services.market_data.mock_provider import DEFAULT_MOCK_CANDLE_PATH, load_mock_candles
from app.services.scanner import scan_forex_watchlist as scan_watchlist
from app.services.technical_analysis.analyzer import analyze_pair_from_candles
from app.services.trading.previews import create_order_preview
from app.services.watchlist import get_default_watchlist, is_allowed_pair, normalize_pair


def get_forex_watchlist() -> list[dict[str, Any]]:
    """Return the configured forex pairs available to mocked analysis."""
    return [item.model_dump(mode="json") for item in get_default_watchlist()]


def scan_forex_watchlist(
    timeframes: list[str],
    strategy_profile: str = "default",
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Analyze local mocked candles and return the highest-ranked setups."""
    if not timeframes:
        raise ValueError("At least one timeframe is required.")
    if max_results < 1:
        raise ValueError("max_results must be at least 1.")

    candle_data = load_mock_candles(DEFAULT_MOCK_CANDLE_PATH)
    results = [
        setup
        for timeframe in timeframes
        for setup in scan_watchlist(candle_data, timeframe, strategy_profile)
    ]
    ranked = sorted(results, key=lambda setup: setup.score, reverse=True)[:max_results]
    return [setup.model_dump(mode="json") for setup in ranked]


def generate_chart(
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
    candles = load_mock_candles(DEFAULT_MOCK_CANDLE_PATH).get(normalized_pair)
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


def get_account_status() -> dict[str, Any]:
    """Return development paper-mode status without contacting a broker."""
    return {
        "environment": "paper",
        "app_env": settings.app_env,
        "live_trading_enabled": False,
        "kill_switch_enabled": settings.kill_switch_enabled,
        "broker_connected": False,
        "message": "Paper/development status only. No live broker is connected.",
    }


def get_open_positions() -> list[dict[str, Any]]:
    """Return paper-mode positions; persistence is not implemented yet."""
    return []


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
