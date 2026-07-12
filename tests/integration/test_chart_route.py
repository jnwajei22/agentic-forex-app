from fastapi.testclient import TestClient

from app.main import app
from app.services.charting import generator


def test_chart_route_returns_png(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    chart_id = "chart_abcdef1234"
    png = b"\x89PNG\r\n\x1a\nmock-png"
    (tmp_path / f"{chart_id}.png").write_bytes(png)

    with TestClient(app) as client:
        response = client.get(f"/charts/{chart_id}.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == png


def test_chart_route_rejects_invalid_identifier(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "CHART_DIR", tmp_path)
    with TestClient(app) as client:
        response = client.get("/charts/not-a-chart.png")

    assert response.status_code == 404
