from app.models.orders import OrderRequest
from app.models.enums import Direction
from app.services.risk.engine import validate_order_request
from app.services.trading.previews import create_order_preview
from app.config.settings import settings
from app.models.enums import OrderPreviewStatus

def test_long_stop_must_be_below_entry(monkeypatch):
    monkeypatch.setattr(settings, "kill_switch_enabled", False)
    order = OrderRequest(
        pair="EUR/USD",
        side=Direction.long,
        entry=1.1000,
        stop_loss=1.1010,
        take_profit=1.1100,
        risk_percent=0.5,
    )
    decision = validate_order_request(order)
    assert not decision.allowed
    assert any("Long stop loss" in v for v in decision.violations)

def test_short_stop_must_be_above_entry(monkeypatch):
    monkeypatch.setattr(settings, "kill_switch_enabled", False)
    order = OrderRequest(
        pair="EUR/USD", side=Direction.short, entry=1.1000,
        stop_loss=1.0990, take_profit=1.0900, risk_percent=0.5,
    )
    decision = validate_order_request(order)
    assert not decision.allowed
    assert any("Short stop loss" in v for v in decision.violations)

def test_kill_switch_rejects_order_preview(monkeypatch):
    monkeypatch.setattr(settings, "kill_switch_enabled", True)
    order = OrderRequest(
        pair="EUR/USD", side=Direction.long, entry=1.1000,
        stop_loss=1.0950, take_profit=1.1100, risk_percent=0.5,
    )
    preview = create_order_preview(order)
    assert preview.status == OrderPreviewStatus.rejected
    assert "Kill switch is enabled." in preview.violations
