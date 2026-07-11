from app.brokers.base import BrokerAdapter
from app.models.orders import OrderPreview

class TradeLockerAdapter(BrokerAdapter):
    async def submit_order(self, preview: OrderPreview) -> dict:
        # Do not implement until the user's specific TradeLocker broker/provider API access is verified.
        raise NotImplementedError("Live TradeLocker execution is intentionally disabled.")
