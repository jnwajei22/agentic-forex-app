from app.models.orders import OrderRequest
from app.models.enums import Direction
from app.services.risk.engine import validate_order_request

def test_long_stop_must_be_below_entry():
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
