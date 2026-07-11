from pydantic import BaseModel
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
    summary: str
