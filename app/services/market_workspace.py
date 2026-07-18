from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Awaitable

from app.services.providers.errors import ProviderError
from app.services.providers.finnhub import FinnhubClient
from app.services.providers.fred import FredClient


DEFAULT_SYMBOLS = ("OANDA:EUR_USD", "OANDA:GBP_USD", "OANDA:USD_JPY", "OANDA:XAU_USD")
MACRO_SERIES = ("DFF", "CPIAUCSL", "UNRATE")


class MarketWorkspaceService:
    """Provider-agnostic market reads with partial-failure responses safe for browsers."""

    def __init__(self, finnhub: FinnhubClient | None = None, fred: FredClient | None = None) -> None:
        self.finnhub = finnhub or FinnhubClient()
        self.fred = fred or FredClient()

    @staticmethod
    async def _partial(provider: str, request: Awaitable[Any], fallback: Any) -> tuple[Any, dict | None]:
        try:
            return await request, None
        except ProviderError as exc:
            return fallback, exc.as_dict()
        except Exception:
            return fallback, {"provider": provider, "error": "upstream_failure",
                              "message": f"{provider} data is temporarily unavailable.", "retryable": True}

    async def search(self, query: str, limit: int = 25) -> dict[str, Any]:
        results, warning = await self._partial("Finnhub", self.finnhub.symbol_search(query, limit), [])
        return {"query": query, "results": results, "sources": ["Finnhub"],
                "warnings": [warning] if warning else []}

    async def overview(self, symbols: list[str] | None = None) -> dict[str, Any]:
        requested = (symbols or list(DEFAULT_SYMBOLS))[:12]
        rows = await asyncio.gather(*(self._partial("Finnhub", self.finnhub.quote(symbol), None)
                                      for symbol in requested))
        return {"quotes": [value for value, _ in rows if value], "sources": ["Finnhub"],
                "warnings": [warning for _, warning in rows if warning]}

    async def news(self, category: str = "general", limit: int = 20) -> dict[str, Any]:
        items, warning = await self._partial("Finnhub", self.finnhub.market_news(category, limit), [])
        return {"items": [item.model_dump(mode="json") for item in items], "sources": ["Finnhub"],
                "warnings": [warning] if warning else []}

    async def calendar(self, start: date, end: date, limit: int = 50) -> dict[str, Any]:
        items, warning = await self._partial("Finnhub", self.finnhub.economic_calendar(start, end, limit), [])
        return {"items": [item.model_dump(mode="json") for item in items], "sources": ["Finnhub"],
                "warnings": [warning] if warning else []}

    async def macro(self) -> dict[str, Any]:
        async def series(series_id: str) -> dict[str, Any]:
            metadata, observations = await asyncio.gather(
                self.fred.series_metadata(series_id),
                self.fred.observations(series_id, observation_start=date.today() - timedelta(days=550), limit=550),
            )
            latest = next((item for item in reversed(observations) if item.value is not None), None)
            return {"series": metadata.model_dump(mode="json"),
                    "latest": latest.model_dump(mode="json") if latest else None, "source": "FRED"}

        rows = await asyncio.gather(*(self._partial("FRED", series(series_id), None)
                                      for series_id in MACRO_SERIES))
        return {"indicators": [value for value, _ in rows if value], "sources": ["FRED"],
                "warnings": [warning for _, warning in rows if warning]}

    async def symbol(self, symbol: str) -> dict[str, Any]:
        quote, warning = await self._partial("Finnhub", self.finnhub.quote(symbol), None)
        return {"symbol": symbol, "quote": quote, "tradingview_symbol": symbol.replace(":", ":"),
                "sources": ["Finnhub", "TradingView"], "warnings": [warning] if warning else []}

    async def aclose(self) -> None:
        await asyncio.gather(self.finnhub.aclose(), self.fred.aclose())
