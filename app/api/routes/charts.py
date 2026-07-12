import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.charting import generator


router = APIRouter(tags=["charts"])
CHART_NAME = re.compile(r"^chart_[0-9a-f]{10}(?:\.png)?$")


@router.get("/charts/{chart_id}", response_class=FileResponse)
async def get_chart(chart_id: str) -> FileResponse:
    """Return a generated chart PNG without allowing arbitrary file access."""
    if not CHART_NAME.fullmatch(chart_id):
        raise HTTPException(status_code=404, detail="Chart not found.")
    filename = chart_id if chart_id.endswith(".png") else f"{chart_id}.png"
    path = generator.CHART_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Chart not found.")
    return FileResponse(path, media_type="image/png", filename=filename)
