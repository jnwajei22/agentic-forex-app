from app.services.watchlist import get_default_watchlist
from app.services.charting.generator import generate_chart_placeholder
from app.models.orders import OrderRequest
from app.services.trading.previews import create_order_preview
from app.services.scanner import scan_forex_watchlist as scan_watchlist

def get_forex_watchlist():
    return [item.model_dump() for item in get_default_watchlist()]

def generate_chart(pair: str, timeframe: str, overlays: list[str]):
    return generate_chart_placeholder(pair, timeframe)

def scan_forex_watchlist(candle_data: dict, timeframe: str = "1h"):
    return [
        setup.model_dump(mode="json")
        for setup in scan_watchlist(candle_data, timeframe)
    ]

def review_forex_order(order_request: dict):
    order = OrderRequest(**order_request)
    preview = create_order_preview(order)
    return preview.model_dump()
