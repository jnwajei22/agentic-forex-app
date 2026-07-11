from collections.abc import Mapping, Sequence

from app.models.analysis import SetupAnalysis
from app.models.enums import Direction, SetupStatus
from app.models.market import Candle
from app.services.watchlist import is_allowed_pair, normalize_pair


def scan_forex_watchlist(
    candle_data: Mapping[str, Sequence[Candle | dict]],
    timeframe: str = "1h",
) -> list[SetupAnalysis]:
    """Rank deterministic placeholder setups from supplied (typically mocked) candles."""
    setups: list[SetupAnalysis] = []

    for raw_pair, raw_candles in candle_data.items():
        pair = normalize_pair(raw_pair)
        if not is_allowed_pair(pair):
            raise ValueError(f"Unknown forex pair: {raw_pair}")

        candles = [
            candle if isinstance(candle, Candle) else Candle.model_validate(candle)
            for candle in raw_candles
        ]
        if len(candles) < 2:
            continue

        first_close = candles[0].close
        last_close = candles[-1].close
        direction = Direction.long if last_close >= first_close else Direction.short
        move = abs(last_close - first_close)
        observed_range = max(c.high for c in candles) - min(c.low for c in candles)
        strength = move / observed_range if observed_range else 0.0
        score = min(85, 50 + round(strength * 35))
        status = (
            SetupStatus.eligible_for_preview if score >= 65 else SetupStatus.weak
        )

        setups.append(
            SetupAnalysis(
                pair=pair,
                timeframe=timeframe,
                direction=direction,
                score=score,
                setup=f"placeholder_{direction.value}_momentum",
                status=status,
                trend=direction.value,
                summary="Placeholder setup derived from mocked candle direction and range.",
            )
        )

    return sorted(setups, key=lambda setup: setup.score, reverse=True)
