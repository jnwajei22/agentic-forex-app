from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.models.api import (
    ForexChartRequest,
    ForexChartResponse,
    ForexScanRequest,
    ForexScanResponse,
    OrderPreviewRequest,
    OrderPreviewResponse,
)
from app.models.market import ForexPairConfig
from app.services.charting.data import build_chart_data
from app.services.charting.generator import render_static_forex_chart
from app.brokers.tradelocker.client import TradeLockerError
from app.services.scanner import scan_forex_watchlist
from app.services.trading.previews import create_order_preview
from app.services.watchlist import get_default_watchlist, is_allowed_pair, normalize_pair


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
async def forex_chart(request: ForexChartRequest) -> ForexChartResponse:
    pair = normalize_pair(request.pair)
    if not is_allowed_pair(pair):
        raise HTTPException(status_code=400, detail="Pair is not allowed.")
    try:
        chart_data = await build_chart_data(
            pair=pair,
            timeframe=request.timeframe,
            lookback=request.lookback,
            start_time=request.start_time,
            end_time=request.end_time,
            overlays=request.overlays,
            entry=request.entry,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )
    except ValueError as exc:
        if "No candle data found" in str(exc):
            raise HTTPException(status_code=404, detail="No candles found for pair.") from exc
        raise HTTPException(status_code=503, detail="Market data is unavailable.") from exc
    except (OSError, TradeLockerError) as exc:
        raise HTTPException(status_code=503, detail="Market data is unavailable.") from exc
    metadata = render_static_forex_chart(chart_data)
    return ForexChartResponse(**metadata)


@router.post("/order-preview", response_model=OrderPreviewResponse)
def forex_order_preview(request: OrderPreviewRequest) -> OrderPreviewResponse:
    preview = create_order_preview(request)
    return OrderPreviewResponse.model_validate(preview, from_attributes=True)
