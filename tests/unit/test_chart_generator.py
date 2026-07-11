from pathlib import Path

from app.services.charting import generator
from app.services.market_data.mock_provider import load_mock_candles
from app.services.technical_analysis.analyzer import analyze_pair_from_candles


FIXTURE = Path(__file__).parents[1] / "fixtures" / "mock_candles.json"


def chart_inputs():
    candles = load_mock_candles(FIXTURE)["EUR/USD"]
    analysis = analyze_pair_from_candles("EUR/USD", "1h", candles, "chart")
    return candles, analysis


def test_chart_png_file_is_created_without_trade_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    candles, analysis = chart_inputs()

    metadata = generator.generate_forex_chart(
        "EUR/USD", "1h", candles, analysis, overlays=["fib"]
    )

    path = Path(metadata["path"])
    assert path.exists()
    assert path.suffix == ".png"
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert metadata.keys() >= {"chart_id", "path", "summary"}


def test_chart_works_with_trade_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    candles, analysis = chart_inputs()

    metadata = generator.generate_forex_chart(
        "EUR/USD",
        "1h",
        candles,
        analysis,
        entry=1.1040,
        stop_loss=1.0990,
        take_profit=1.1120,
    )

    assert Path(metadata["path"]).is_file()
    assert metadata["pair"] == "EUR/USD"
    assert metadata["timeframe"] == "1h"
    assert metadata["trend"] == analysis.trend
    assert metadata["generated_at"]
