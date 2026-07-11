import json
from pathlib import Path

import pytest

from app.services.scanner import scan_forex_watchlist


FIXTURE = Path(__file__).parents[1] / "fixtures" / "mock_candles.json"


def test_scan_forex_watchlist_returns_ranked_technical_setups():
    candle_data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    setups = scan_forex_watchlist(candle_data, timeframe="1h")

    assert len(setups) == 2
    assert [setup.score for setup in setups] == sorted(
        [setup.score for setup in setups], reverse=True
    )
    assert setups[0].model_dump().keys() >= {
        "pair", "timeframe", "direction", "score", "setup", "status"
    }
    assert {setup.direction.value for setup in setups} == {"long", "short"}
    assert all(setup.fib_levels for setup in setups)


def test_scan_rejects_unknown_pair():
    candle = {
        "timestamp": "2026-07-10T12:00:00Z",
        "open": 1,
        "high": 2,
        "low": 0.5,
        "close": 1.5,
    }
    with pytest.raises(ValueError, match="Unknown forex pair"):
        scan_forex_watchlist({"XYZ/ABC": [candle, candle]})
