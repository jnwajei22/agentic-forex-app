from datetime import datetime

from pydantic import BaseModel, Field

from app.models.analysis import SetupAnalysis
from app.models.enums import Direction, OrderPreviewStatus
from app.models.market import Candle
from app.models.orders import OrderRequest


class ForexScanRequest(BaseModel):
    candle_data: dict[str, list[Candle]]
    timeframe: str = "1h"


class ForexScanResponse(BaseModel):
    scan_id: str
    results: list[SetupAnalysis]
    timestamp: datetime
    disclaimer: str


class ForexChartRequest(BaseModel):
    pair: str
    timeframe: str = "1h"
    overlays: list[str] = Field(default_factory=list)


class ForexChartResponse(BaseModel):
    chart_id: str
    path: str
    summary: str


class OrderPreviewRequest(OrderRequest):
    pass


class OrderPreviewResponse(BaseModel):
    preview_id: str
    status: OrderPreviewStatus
    pair: str
    side: Direction
    entry: float
    stop_loss: float
    take_profit: float
    lot_size: float
    pip_risk: float
    risk_amount: float
    reward_risk: float
    violations: list[str]
    expires_at: datetime
