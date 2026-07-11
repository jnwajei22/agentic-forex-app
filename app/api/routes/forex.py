from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter

from app.models.api import (
    ForexChartRequest,
    ForexChartResponse,
    ForexScanRequest,
    ForexScanResponse,
    OrderPreviewRequest,
    OrderPreviewResponse,
)
from app.models.market import ForexPairConfig
from app.services.charting.generator import generate_chart_placeholder
from app.services.scanner import scan_forex_watchlist
from app.services.trading.previews import create_order_preview
from app.services.watchlist import get_default_watchlist


router = APIRouter(prefix="/forex", tags=["forex"])
DISCLAIMER = "This is analysis, not financial advice. Live trading carries risk."


@router.get("/watchlist", response_model=list[ForexPairConfig])
def forex_watchlist() -> list[ForexPairConfig]:
    return get_default_watchlist()


@router.post("/scan", response_model=ForexScanResponse)
def forex_scan(request: ForexScanRequest) -> ForexScanResponse:
    results = scan_forex_watchlist(request.candle_data, request.timeframe)
    return ForexScanResponse(
        scan_id=f"fxscan_{uuid4().hex[:12]}",
        results=results,
        timestamp=datetime.now(timezone.utc),
        disclaimer=DISCLAIMER,
    )


@router.post("/chart", response_model=ForexChartResponse)
def forex_chart(request: ForexChartRequest) -> ForexChartResponse:
    # Overlays are accepted for forward compatibility but charting remains a stub.
    return ForexChartResponse(
        **generate_chart_placeholder(request.pair, request.timeframe)
    )


@router.post("/order-preview", response_model=OrderPreviewResponse)
def forex_order_preview(request: OrderPreviewRequest) -> OrderPreviewResponse:
    preview = create_order_preview(request)
    return OrderPreviewResponse.model_validate(preview, from_attributes=True)
