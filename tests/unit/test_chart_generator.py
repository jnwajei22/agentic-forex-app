from pathlib import Path

import pytest

from app.config.settings import settings
from app.services.charting import generator
from app.services.charting.data import build_chart_data


@pytest.mark.asyncio
async def test_static_chart_consumes_chart_data_and_creates_png(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "market_data_provider", "mock")
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    monkeypatch.setattr(generator.settings, "public_base_url", "https://charts.example.test")
    chart_data = await build_chart_data(pair="EUR/USD", timeframe="1h")

    metadata = generator.render_static_forex_chart(chart_data)

    path = Path(metadata["path"])
    assert path.exists() and path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert metadata["public_chart_url"] == (
        f"https://charts.example.test/charts/{metadata['chart_id']}.png"
    )
    assert metadata["chart_data_summary"]["candles_returned"] == 3
    assert "Ã" not in metadata["summary"]


@pytest.mark.asyncio
async def test_static_chart_works_with_valid_trade_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "market_data_provider", "mock")
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    chart_data = await build_chart_data(
        pair="EUR/USD", timeframe="1h", entry=1.104, stop_loss=1.099, take_profit=1.112
    )

    metadata = generator.render_static_forex_chart(chart_data)

    assert Path(metadata["path"]).is_file()
    assert chart_data.trade_setup is not None and chart_data.trade_setup.valid
    assert metadata["trend"] == chart_data.analysis.trend
