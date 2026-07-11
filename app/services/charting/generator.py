from pathlib import Path
from uuid import uuid4

CHART_DIR = Path("storage/charts")

def generate_chart_placeholder(pair: str, timeframe: str) -> dict:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    chart_id = f"chart_{uuid4().hex[:10]}"
    path = CHART_DIR / f"{chart_id}.txt"
    path.write_text(f"Placeholder chart for {pair} {timeframe}\n")
    return {
        "chart_id": chart_id,
        "path": str(path),
        "summary": "Chart generation placeholder. Implement mplfinance candlestick output next.",
    }
