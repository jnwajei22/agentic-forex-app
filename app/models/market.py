from pydantic import BaseModel
from datetime import datetime

class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

class ForexPairConfig(BaseModel):
    pair: str
    enabled: bool = True
    max_spread: float | None = None
    allowed_timeframes: list[str] = ["15m", "1h"]
    allowed_sessions: list[str] = ["london", "new_york"]
    max_risk_percent: float = 0.5
    max_open_trades_per_pair: int = 1
    news_blackout_enabled: bool = True
