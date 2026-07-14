from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CandlePoint(BaseModel):
    timestamp: int
    iso_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class SeriesPoint(BaseModel):
    timestamp: int
    value: float


class IndicatorSeries(BaseModel):
    ema_20: list[SeriesPoint] = Field(default_factory=list)
    ema_50: list[SeriesPoint] = Field(default_factory=list)
    ema_200: list[SeriesPoint] = Field(default_factory=list)
    rsi_14: float | None = None
    atr_14: float | None = None


class FibonacciData(BaseModel):
    direction: str | None = None
    swing_low: float | None = None
    swing_high: float | None = None
    swing_low_timestamp: int | None = None
    swing_high_timestamp: int | None = None
    levels: dict[str, float] = Field(default_factory=dict)


class SupportResistanceZone(BaseModel):
    type: Literal["support", "resistance"]
    price: float
    lower_bound: float
    upper_bound: float
    strength: float | None = None
    touches: int | None = None


class SwingPoint(BaseModel):
    timestamp: int
    price: float
    type: Literal["high", "low"]


class TradeSetup(BaseModel):
    direction: str | None = None
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    additional_targets: list[float] = Field(default_factory=list)
    risk: float | None = None
    reward: float | None = None
    risk_reward: float | None = None
    valid: bool = False
    validation_message: str | None = None
    source: str = "user_supplied"


class ChartRange(BaseModel):
    requested_start: str
    requested_end: str
    actual_start: str | None = None
    actual_end: str | None = None
    candles_returned: int
    batches_requested: int
    complete: bool
    stop_reason: str | None = None
    warning: str | None = None
    malformed_candles_discarded: int = 0


class ChartAnalysis(BaseModel):
    trend: str
    direction: str | None = None
    score: int
    status: str
    setup: str
    trend_clarity: int
    ema_20: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    candle_range: float | None = None
    spread: float | None = None
    spread_warning: str | None = None
    missing_data_warning: str | None = None
    guidance: str
    summary: str


class DisplayMetadata(BaseModel):
    source_points: int
    returned_points: int
    downsampled: bool
    downsampling_method: str | None = None


class ChartData(BaseModel):
    pair: str
    symbol: str
    timeframe: str
    range: ChartRange
    latest_price: float
    analysis: ChartAnalysis
    indicators: IndicatorSeries
    fibonacci: FibonacciData
    support_zones: list[SupportResistanceZone] = Field(default_factory=list)
    resistance_zones: list[SupportResistanceZone] = Field(default_factory=list)
    swings: list[SwingPoint] = Field(default_factory=list)
    trade_setup: TradeSetup | None = None
    display: DisplayMetadata
    candles: list[CandlePoint] = Field(default_factory=list)
