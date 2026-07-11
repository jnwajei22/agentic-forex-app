from app.services.watchlist import get_default_watchlist
from app.services.charting.generator import generate_chart_placeholder
from app.models.orders import OrderRequest
from app.services.trading.previews import create_order_preview

def get_forex_watchlist():
    return [item.model_dump() for item in get_default_watchlist()]

def generate_chart(pair: str, timeframe: str, overlays: list[str]):
    return generate_chart_placeholder(pair, timeframe)

def review_forex_order(order_request: dict):
    order = OrderRequest(**order_request)
    preview = create_order_preview(order)
    return preview.model_dump()
