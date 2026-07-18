from __future__ import annotations

import asyncio
from datetime import date, timedelta
from datetime import datetime, timezone
from typing import Any, Awaitable

from app.services.providers.errors import ProviderError
from app.services.providers.finnhub import FinnhubClient
from app.services.providers.fred import FredClient
from app.services.instruments import DEFAULT_FOREX_MAJORS, InstrumentMappingError, instrument_mapper


DEFAULT_SYMBOLS = tuple(f"forex:{symbol}" for symbol in DEFAULT_FOREX_MAJORS[:3])
MACRO_SERIES = ("DFF", "CPIAUCSL", "UNRATE")


class MarketWorkspaceService:
    """Provider-agnostic market reads with partial-failure responses safe for browsers."""

    def __init__(self, finnhub: FinnhubClient | None = None, fred: FredClient | None = None) -> None:
        self.finnhub = finnhub or FinnhubClient()
        self.fred = fred or FredClient()

    @staticmethod
    def _stamp(payload: dict[str, Any]) -> dict[str, Any]:
        return {**payload, "last_updated": datetime.now(timezone.utc).isoformat()}

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
        canonical = [instrument for row in results if (instrument := instrument_mapper.from_finnhub(row))]
        if not canonical and query:
            try:
                canonical = [instrument_mapper.resolve(instrument_mapper.canonical_id("forex", query))]
            except InstrumentMappingError:
                canonical = []
        return self._stamp({"query": query, "results": [item.model_dump() for item in canonical[:limit]], "sources": ["Finnhub"],
                "warnings": [warning] if warning else []})

    async def overview(self, symbols: list[str] | None = None) -> dict[str, Any]:
        requested = (symbols or list(DEFAULT_SYMBOLS))[:12]
        mapped = []
        for canonical_id in requested:
            try:
                instrument = instrument_mapper.resolve(canonical_id)
            except InstrumentMappingError:
                continue
            provider_symbol = instrument.provider_symbols.get("finnhub")
            if provider_symbol:
                mapped.append((instrument, provider_symbol))
        rows = await asyncio.gather(*(self._partial("Finnhub", self.finnhub.quote(symbol), None)
                                      for _, symbol in mapped))
        quotes = [{**value, "canonical_id": instrument.canonical_id, "symbol": instrument.symbol}
                  for (instrument, _), (value, _) in zip(mapped, rows) if value]
        return self._stamp({"quotes": quotes, "sources": ["Finnhub"],
                "warnings": [warning for _, warning in rows if warning]})

    async def news(self, category: str = "general", limit: int = 20) -> dict[str, Any]:
        items, warning = await self._partial("Finnhub", self.finnhub.market_news(category, limit), [])
        return self._stamp({"items": [item.model_dump(mode="json") for item in items], "sources": ["Finnhub"],
                "warnings": [warning] if warning else []})

    async def calendar(self, start: date, end: date, limit: int = 50) -> dict[str, Any]:
        items, warning = await self._partial("Finnhub", self.finnhub.economic_calendar(start, end, limit), [])
        return self._stamp({"items": [item.model_dump(mode="json") for item in items], "sources": ["Finnhub"],
                "warnings": [warning] if warning else []})

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
        return self._stamp({"indicators": [value for value, _ in rows if value], "sources": ["FRED"],
                "warnings": [warning for _, warning in rows if warning]})

    async def symbol(self, canonical_id: str) -> dict[str, Any]:
        instrument = instrument_mapper.resolve(canonical_id)
        finnhub_symbol = instrument.provider_symbols.get("finnhub")
        quote, warning = await self._partial("Finnhub", self.finnhub.quote(finnhub_symbol), None) if finnhub_symbol else (None, {
            "provider": "Finnhub", "error": "capability_unavailable", "message": "This instrument is unsupported.", "retryable": False})
        return self._stamp({"instrument": instrument.model_dump(), "quote": quote,
                "tradingview_symbol": instrument.provider_symbols.get("tradingview"),
                "sources": ["Finnhub", "TradingView"], "warnings": [warning] if warning else []})

    async def summary(self, canonical_id: str) -> dict[str, Any]:
        instrument = instrument_mapper.resolve(canonical_id)
        symbol = instrument.provider_symbols.get("finnhub")
        updated_at = datetime.now(timezone.utc).isoformat()
        if not symbol:
            return {"instrument": instrument.model_dump(), "quote": None,
                "market_status": {"state": "unknown", "label": "Market Status Unavailable"},
                "sources": [{"provider": "finnhub", "status": "unsupported",
                    "message": "Quote summary is unavailable for this instrument."}], "partial": True}
        quote, warning = await self._partial("Finnhub", self.finnhub.quote(symbol), None)
        if warning or not quote or quote.get("price") is None:
            status = "unsupported" if warning and warning.get("error") in {"capability_unavailable", "invalid_request"} else "unavailable"
            return {"instrument": instrument.model_dump(), "quote": None,
                "market_status": {"state": "unknown", "label": "Market Status Unavailable"},
                "sources": [{"provider": "finnhub", "status": status, "updated_at": updated_at,
                    "message": warning.get("message") if warning else "Finnhub returned no quote data."}], "partial": True}
        normalized = {key: quote.get(key) for key in ("price", "change", "change_percent", "open", "high", "low", "previous_close")}
        normalized["timestamp"] = datetime.fromtimestamp(quote["timestamp"], timezone.utc).isoformat() if quote.get("timestamp") else None
        stale = bool(quote.get("timestamp") and datetime.now(timezone.utc).timestamp() - float(quote["timestamp"]) > 300)
        return {"instrument": instrument.model_dump(), "quote": normalized,
            "market_status": {"state": "unknown", "label": "Market status not provided by this quote source"},
            "sources": [{"provider": "finnhub", "status": "stale" if stale else "available", "updated_at": normalized["timestamp"] or updated_at,
                "message": "Quote data is delayed or stale." if stale else None}], "partial": stale}

    async def aclose(self) -> None:
        await asyncio.gather(self.finnhub.aclose(), self.fred.aclose())
