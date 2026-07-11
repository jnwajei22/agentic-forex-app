from pydantic import BaseModel
from datetime import datetime

class TradingViewSignal(BaseModel):
    source: str
    pair: str
    timeframe: str
    signal: str
    price: float
    strategy: str
    timestamp: datetime
