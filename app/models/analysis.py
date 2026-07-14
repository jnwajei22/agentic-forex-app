from pydantic import BaseModel, Field
from app.models.enums import Direction, SetupStatus

class FibLevels(BaseModel):
    level_0236: float
    level_0382: float
    level_0500: float
    level_0618: float
    level_0786: float
    level_1000: float
    ext_1272: float | None = None
    ext_1618: float | None = None

class SetupAnalysis(BaseModel):
    pair: str
    timeframe: str
    direction: Direction | None = None
    score: int
    status: SetupStatus
    setup: str
    trend: str
    swing_high: float | None = None
    swing_low: float | None = None
    swing_high_timestamp: int | None = None
    swing_low_timestamp: int | None = None
    fib_levels: dict[str, float] = Field(default_factory=dict)
    support_zones: list[float] = Field(default_factory=list)
    resistance_zones: list[float] = Field(default_factory=list)
    ema_20: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    candle_range: float | None = None
    spread: float | None = None
    spread_warning: str | None = None
    missing_data_warning: str | None = None
    trend_clarity: int = 0
    guidance: str = "No trade / no clean setup."
    summary: str
