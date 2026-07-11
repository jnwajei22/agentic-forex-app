from app.brokers.base import BrokerAdapter
from app.brokers.tradelocker.client import TradeLockerClient
from app.config.settings import settings
from app.models.orders import OrderPreview


class TradeLockerAdapter(BrokerAdapter):
    def __init__(self, client: TradeLockerClient | None = None) -> None:
        self.client = client or TradeLockerClient(
            base_url=settings.tradelocker_base_url,
            username=settings.tradelocker_username,
            password=settings.tradelocker_password,
            server=settings.tradelocker_server,
            account_id=settings.tradelocker_account_id,
            account_number=settings.tradelocker_account_number,
        )

    async def get_account(self) -> dict:
        return await self.client.get_account_status()

    async def get_open_positions(self) -> list[dict] | dict:
        return await self.client.get_open_positions()

    async def get_quote(self, pair: str) -> dict:
        return await self.client.get_quote(pair)

    async def get_candles(self, pair: str, timeframe: str, lookback: int) -> list[dict] | dict:
        return await self.client.get_candles(pair, timeframe, lookback)

    async def submit_order(self, preview: OrderPreview) -> dict:
        raise NotImplementedError("Live TradeLocker execution is intentionally disabled.")


_adapter: TradeLockerAdapter | None = None
_adapter_config: tuple[str | None, ...] | None = None


def get_tradelocker_adapter() -> TradeLockerAdapter:
    global _adapter, _adapter_config
    config = (
        settings.tradelocker_base_url,
        settings.tradelocker_username,
        settings.tradelocker_password,
        settings.tradelocker_server,
        settings.tradelocker_account_id,
        settings.tradelocker_account_number,
    )
    if _adapter is None or config != _adapter_config:
        _adapter = TradeLockerAdapter()
        _adapter_config = config
    return _adapter
