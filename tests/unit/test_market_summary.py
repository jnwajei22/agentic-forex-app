import pytest
from datetime import datetime, timezone

from app.services.market_workspace import MarketWorkspaceService
from app.services.providers.errors import ProviderError


class Finnhub:
    async def quote(self, symbol):
        assert symbol == "OANDA:EUR_USD"
        return {"symbol":symbol,"price":1.1234,"change":.0012,"change_percent":.11,
            "open":1.121,"high":1.125,"low":1.1195,"previous_close":1.1222,"timestamp":datetime.now(timezone.utc).timestamp()}
    async def aclose(self): pass

class Unavailable(Finnhub):
    async def quote(self, symbol):
        raise ProviderError("finnhub","upstream_failure","Unavailable",retryable=True)

class Fred:
    async def aclose(self): pass


@pytest.mark.asyncio
async def test_finnhub_summary_normalizes_and_attributes_without_fake_values():
    result = await MarketWorkspaceService(Finnhub(),Fred()).summary("forex:EUR/USD")
    assert result["quote"]["price"] == 1.1234
    assert result["instrument"]["canonical_id"] == "forex:EUR/USD"
    assert result["sources"][0]["provider"] == "finnhub" and result["partial"] is False


@pytest.mark.asyncio
async def test_finnhub_unavailable_is_structured_partial():
    result = await MarketWorkspaceService(Unavailable(),Fred()).summary("forex:EUR/USD")
    assert result["quote"] is None and result["partial"] is True
    assert result["sources"][0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_unsupported_instrument_returns_no_fake_quote():
    result = await MarketWorkspaceService(Finnhub(),Fred()).summary("energy:UNKNOWN")
    assert result["quote"] is None and result["partial"] is True
    assert result["sources"][0]["status"] == "unsupported"
