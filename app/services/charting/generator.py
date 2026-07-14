from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from app.models.analysis import SetupAnalysis
from app.models.market import Candle
from app.config.settings import settings
from app.services.technical_analysis.indicators import calculate_ema_series


CHART_DIR = Path("storage/charts")
DISCLAIMER = "Preview only. Not financial advice."


def _candle_frame(candles: list[Candle]) -> pd.DataFrame:
    if not candles:
        raise ValueError("Candles are required to generate a chart.")
    frame = pd.DataFrame(
        [
            {
                "Date": pd.to_datetime(candle.timestamp, unit="ms", utc=True),
                "Open": candle.open,
                "High": candle.high,
                "Low": candle.low,
                "Close": candle.close,
                "Volume": candle.volume or 0,
            }
            for candle in sorted(candles, key=lambda item: item.timestamp)
        ]
    )
    frame["Date"] = pd.to_datetime(frame["Date"], utc=True).dt.tz_localize(None)
    return frame.set_index("Date")


def generate_forex_chart(
    pair: str,
    timeframe: str,
    candles: list[Candle],
    analysis: SetupAnalysis,
    overlays: list[str] | None = None,
    entry: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Render a local static PNG from mocked candles and analyzer output."""
    ordered_candles = sorted(candles, key=lambda item: item.timestamp)
    frame = _candle_frame(ordered_candles)
    generated_at = datetime.now(timezone.utc)
    chart_id = f"chart_{uuid4().hex[:10]}"
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / f"{chart_id}.png"

    closes = [candle.close for candle in ordered_candles]
    ema_plots = []
    for period, color in ((20, "#1f77b4"), (50, "#ff7f0e"), (200, "#9467bd")):
        series = calculate_ema_series(closes, period)
        if any(value is not None for value in series):
            ema_plots.append(
                mpf.make_addplot(
                    pd.Series(series, index=frame.index),
                    color=color,
                    width=1.0,
                    label=f"EMA {period}",
                )
            )

    style = mpf.make_mpf_style(base_mpf_style="charles", gridstyle=":")
    plot_options = {
        "type": "candle",
        "style": style,
        "volume": False,
        "returnfig": True,
        "figsize": (13, 8),
        "datetime_format": "%m-%d %H:%M",
        "xrotation": 15,
    }
    if ema_plots:
        plot_options["addplot"] = ema_plots
    fig, axes = mpf.plot(frame, **plot_options)
    price_axis = axes[0]

    def level(value: float | None, color: str, label: str, linestyle: str = "--") -> None:
        if value is None:
            return
        price_axis.axhline(value, color=color, linestyle=linestyle, linewidth=0.9, alpha=0.8)
        price_axis.text(
            1.002,
            value,
            f" {label} {value:.5f}",
            color=color,
            fontsize=7,
            va="center",
            transform=price_axis.get_yaxis_transform(),
        )

    current_price = ordered_candles[-1].close
    level(current_price, "black", "Current", "-")
    level(analysis.swing_high, "darkorange", "Swing high")
    level(analysis.swing_low, "darkorange", "Swing low")
    for name, value in analysis.fib_levels.items():
        level(value, "slateblue", f"Fib {name}", ":")
    for value in analysis.support_zones:
        level(value, "green", "Support", "-.")
    for value in analysis.resistance_zones:
        level(value, "firebrick", "Resistance", "-.")
    level(entry, "dodgerblue", "Entry", "-")
    level(stop_loss, "red", "Stop", "-")
    level(take_profit, "green", "Target", "-")

    if ema_plots:
        price_axis.legend(loc="upper left", fontsize=8)

    price_axis.set_title(
        f"{pair} · {timeframe} · {analysis.trend.upper()} · Current {current_price:.5f}",
        fontsize=13,
        pad=14,
    )
    price_axis.set_ylabel("Price")
    indicator_text = (
        f"RSI 14: {analysis.rsi_14:.1f}" if analysis.rsi_14 is not None else "RSI 14: n/a"
    )
    indicator_text += (
        f" | ATR 14: {analysis.atr_14:.5f}" if analysis.atr_14 is not None else " | ATR 14: n/a"
    )
    indicator_text += f" | Range: {(analysis.candle_range or 0):.5f}"
    if analysis.spread is not None:
        indicator_text += f" | Spread: {analysis.spread:.5f}"
    overlay_text = (
        f"Overlays: candlesticks, EMA, Fibonacci, support/resistance, swings | {indicator_text}"
    )
    fig.text(0.01, 0.025, overlay_text, fontsize=8, color="dimgray")
    fig.text(
        0.99,
        0.025,
        f"{generated_at.isoformat()} · {DISCLAIMER}",
        ha="right",
        fontsize=8,
        color="dimgray",
    )
    fig.subplots_adjust(right=0.82, bottom=0.14, top=0.90)
    try:
        fig.savefig(path, dpi=140, bbox_inches="tight")
    finally:
        plt.close(fig)

    public_chart_url = (
        f"{settings.public_base_url.rstrip('/')}/charts/{chart_id}.png"
    )
    return {
        "chart_id": chart_id,
        "public_chart_url": public_chart_url,
        "local_path": str(path),
        "path": str(path),
        "summary": (
            f"Static candlestick analysis chart for {pair} {timeframe}; "
            f"trend {analysis.trend}, RSI {analysis.rsi_14}, ATR {analysis.atr_14}. {DISCLAIMER}"
        ),
        "pair": pair,
        "timeframe": timeframe,
        "trend": analysis.trend,
        "generated_at": generated_at,
    }
