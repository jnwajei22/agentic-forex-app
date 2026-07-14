from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from app.config.settings import settings
from app.models.chart import ChartData


CHART_DIR = Path("storage/charts")
DISCLAIMER = "Preview only. Not financial advice."


def _candle_frame(chart_data: ChartData) -> pd.DataFrame:
    if not chart_data.candles:
        raise ValueError("ChartData must include candles for static rendering.")
    frame = pd.DataFrame(
        [
            {
                "Date": pd.to_datetime(candle.timestamp, unit="ms", utc=True),
                "Open": candle.open,
                "High": candle.high,
                "Low": candle.low,
                "Close": candle.close,
                "Volume": candle.volume,
            }
            for candle in chart_data.candles
        ]
    )
    frame["Date"] = pd.to_datetime(frame["Date"], utc=True).dt.tz_localize(None)
    return frame.set_index("Date")


def render_static_forex_chart(chart_data: ChartData) -> dict:
    """Render a static PNG from the shared structured ChartData object."""
    frame = _candle_frame(chart_data)
    generated_at = datetime.now(timezone.utc)
    chart_id = f"chart_{uuid4().hex[:10]}"
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / f"{chart_id}.png"

    ema_plots = []
    for name, color in (
        ("ema_20", "#1f77b4"),
        ("ema_50", "#ff7f0e"),
        ("ema_200", "#9467bd"),
    ):
        points = getattr(chart_data.indicators, name)
        values = {point.timestamp: point.value for point in points}
        series = [values.get(candle.timestamp) for candle in chart_data.candles]
        if any(value is not None for value in series):
            ema_plots.append(
                mpf.make_addplot(
                    pd.Series(series, index=frame.index),
                    color=color,
                    width=1.0,
                    label=name.replace("_", " ").upper(),
                )
            )

    plot_options = {
        "type": "candle",
        "style": mpf.make_mpf_style(base_mpf_style="charles", gridstyle=":"),
        "volume": False,
        "returnfig": True,
        "figsize": (13, 8),
        "datetime_format": "%m-%d %H:%M",
        "xrotation": 15,
        "warn_too_much_data": max(10_000, len(chart_data.candles) + 1),
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

    level(chart_data.latest_price, "black", "Current", "-")
    level(chart_data.fibonacci.swing_high, "darkorange", "Swing high")
    level(chart_data.fibonacci.swing_low, "darkorange", "Swing low")
    for name, value in chart_data.fibonacci.levels.items():
        level(value, "slateblue", f"Fib {name}", ":")
    for zone in chart_data.support_zones:
        level(zone.price, "green", "Support", "-.")
    for zone in chart_data.resistance_zones:
        level(zone.price, "firebrick", "Resistance", "-.")
    setup = chart_data.trade_setup
    level(setup.entry if setup else None, "dodgerblue", "Entry", "-")
    level(setup.stop_loss if setup else None, "red", "Stop", "-")
    level(setup.take_profit if setup else None, "green", "Target", "-")
    if setup:
        for index, target in enumerate(setup.additional_targets, start=2):
            level(target, "green", f"Target {index}", "-")
    for swing in chart_data.swings:
        moment = pd.to_datetime(swing.timestamp, unit="ms", utc=True).tz_localize(None)
        marker = "^" if swing.type == "low" else "v"
        price_axis.scatter(moment, swing.price, marker=marker, color="darkorange", zorder=5)

    if ema_plots:
        price_axis.legend(loc="upper left", fontsize=8)
    price_axis.set_title(
        f"{chart_data.pair} · {chart_data.timeframe} · "
        f"{chart_data.analysis.trend.upper()} · Current {chart_data.latest_price:.5f}",
        fontsize=13,
        pad=14,
    )
    price_axis.set_ylabel("Price")
    indicator_text = (
        f"RSI 14: {chart_data.analysis.rsi_14:.1f}"
        if chart_data.analysis.rsi_14 is not None
        else "RSI 14: n/a"
    )
    indicator_text += (
        f" | ATR 14: {chart_data.analysis.atr_14:.5f}"
        if chart_data.analysis.atr_14 is not None
        else " | ATR 14: n/a"
    )
    indicator_text += f" | Range: {(chart_data.analysis.candle_range or 0):.5f}"
    if chart_data.analysis.spread is not None:
        indicator_text += f" | Spread: {chart_data.analysis.spread:.5f}"
    fig.text(
        0.01,
        0.025,
        "Overlays: candlesticks, EMA, Fibonacci, support/resistance, swings | "
        + indicator_text,
        fontsize=8,
        color="dimgray",
    )
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

    return {
        "chart_id": chart_id,
        "public_chart_url": f"{settings.public_base_url.rstrip('/')}/charts/{chart_id}.png",
        "local_path": str(path),
        "path": str(path),
        "summary": (
            f"Static candlestick analysis chart for {chart_data.pair} {chart_data.timeframe}; "
            f"trend {chart_data.analysis.trend}, RSI {chart_data.analysis.rsi_14}, "
            f"ATR {chart_data.analysis.atr_14}. {DISCLAIMER}"
        ),
        "pair": chart_data.pair,
        "timeframe": chart_data.timeframe,
        "trend": chart_data.analysis.trend,
        "generated_at": generated_at,
        "chart_data_summary": {
            "candles_returned": chart_data.range.candles_returned,
            "display_points": chart_data.display.returned_points,
            "complete": chart_data.range.complete,
            "score": chart_data.analysis.score,
            "direction": chart_data.analysis.direction,
        },
    }
