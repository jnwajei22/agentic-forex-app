from collections.abc import Mapping, Sequence

from app.models.analysis import SetupAnalysis
from app.models.market import Candle
from app.services.market_data.mock_provider import parse_mock_candles
from app.services.technical_analysis.analyzer import analyze_pair_from_candles
from app.services.watchlist import is_allowed_pair, normalize_pair


def scan_forex_watchlist(
    candle_data: Mapping[str, Sequence[Candle | dict]],
    timeframe: str = "1h",
    strategy_profile: str = "default",
) -> list[SetupAnalysis]:
    """Analyze and rank setups from caller-supplied mocked candles."""
    setups: list[SetupAnalysis] = []
    parsed_data = parse_mock_candles(candle_data)

    for raw_pair, candles in parsed_data.items():
        pair = normalize_pair(raw_pair)
        if not is_allowed_pair(pair):
            raise ValueError(f"Unknown forex pair: {raw_pair}")

        if len(candles) < 2:
            continue
        setups.append(
            analyze_pair_from_candles(pair, timeframe, candles, strategy_profile)
        )

    return sorted(setups, key=lambda setup: setup.score, reverse=True)
