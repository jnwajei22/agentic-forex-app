# Agentic Forex Desk

Agentic Forex Desk is a focused forex research and execution-data backend for ChatGPT. It retrieves and normalizes financial data and now includes a presentation-only MCP Apps chart widget. ChatGPT still calculates overlays, technical analysis, scenarios, forecasts, and final trade planning.

## Provider authority

- **TradeLocker** is authoritative for the connected user's broker account, symbols, bid/ask quotes, spreads, forex candles used for execution analysis, balance, equity, margin, positions, pending orders, and deterministic risk-reviewed order previews.
- **Finnhub** supplies optional economic-calendar events, concise market news, cross-market context, and explicitly selected secondary forex data when the configured subscription permits it.
- **FRED/ALFRED** supplies official macroeconomic metadata, observations, release dates, real-time periods, and revision-aware historical context.
- **ChatGPT** calculates indicators, Fibonacci levels, support/resistance, strategies, and forecasts. The MCP Apps widget only renders the supplied values.
- **TradingView webhook** is optional untrusted inbound alert data. It is disabled without a secret, is not verified market data, and cannot place trades.

Finnhub and FRED values never replace TradeLocker prices for entry, stops, sizing, margin, previews, or execution. Source disagreements remain separate and explicitly labeled; the backend never averages or synthesizes cross-provider prices.

## Interactive snapshot charts

PNG generation remains removed: no image, public chart URL, or chart file is generated. Phase 1 uses Lightweight Charts only as a locally bundled renderer inside a sandboxed ChatGPT iframe. Each chart is an interactive snapshot with candlesticks, zoom, pan, crosshair, optional volume, supplied price/line overlays, and markers. It does not poll or continuously update after the tool call.

When a user asks for a chart:

1. ChatGPT calls `get_market_candles` with the requested range.
2. It verifies `complete`, `actual_start`, `actual_end`, and `candles_returned`, then calculates any requested Fibonacci or indicator values.
3. It calls `render_market_chart` with the returned user-scoped `series_id` and those overlays.
4. It must not claim a chart exists unless `render_market_chart` succeeds and the iframe is visible.

## Main MCP tools

- `get_market_candles`: canonical TradeLocker or explicitly selected Finnhub OHLCV.
- `render_market_chart`: displays a cached series in the versioned interactive MCP Apps resource; it retrieves no data and calculates no indicators.
- `get_watchlist_market_data`: bounded close-only or selected-field TradeLocker series without ranking.
- `get_economic_calendar`, `get_market_news`: optional Finnhub data.
- `search_macro_series`, `get_macro_series`, `get_macro_release_calendar`: official FRED data.
- `get_forex_research_bundle`: bounded sections kept separate by source.
- TradeLocker connection, account, quote, symbols, positions, pending orders, preview, and kill-switch tools.

Example:

```json
{
  "name": "get_market_candles",
  "arguments": {
    "symbol": "EURUSD",
    "timeframe": "1H",
    "source": "tradelocker",
    "lookback": 300
  }
}
```

Canonical responses contain UTC ISO-8601 timestamps, oldest-to-newest candles, provider identity, requested and actual ranges, pagination metadata, completeness, warnings, and client-side rendering instructions. The default response is 300 candles and the maximum response is 2,000. The retrieval safety ceiling remains 10,000. Oversized requests return `response_too_large`; OHLC candles are never silently sampled or synthesized.

## Configuration

Copy `.env.example` and preserve the existing Auth0/OAuth, onboarding assertion, database, and `BROKER_SECRET_KEY` settings.

Finnhub keys are obtained from the Finnhub account dashboard. Enable it with `FINNHUB_ENABLED=true`. Economic calendar and forex endpoints may require paid capabilities; permission failures are cached and returned as `capability_unavailable`.

FRED keys are obtained from the St. Louis Fed API key page. Enable it with `FRED_ENABLED=true`. Configure currency mappings through `MACRO_CATALOG_JSON`; the repository intentionally ships no unverified default series IDs.

Both public providers use isolated in-process TTL caches. Successful market series are cached for ten minutes by authenticated user and cryptographic `series_id`, with a default global maximum of 100 entries. Credentials and authorization data are never cached. A persistent cache can replace the isolated interface later.

## Deployment

Build and test the locally bundled widget before starting or packaging the backend:

```text
npm --prefix widget ci
npm --prefix widget test
npm --prefix widget run build
```

Then install backend dependencies with `pip install -r requirements.txt` and restart the backend. Startup fails clearly if `widget/dist/index.html` is missing. No database migration is required. Disconnect and reconnect (or refresh) the ChatGPT app after deployment so it discovers the new tool metadata and `ui://widget/market-chart-v1.html` resource.

The Vercel onboarding frontend is unchanged; only the backend artifact now includes the built widget HTML. For Raspberry Pi deployments, keep system time synchronized, protect `.env`, use persistent PostgreSQL as already supported, and expect in-process caches to clear on restart.

Live trading remains disabled and the kill switch enabled:

```text
LIVE_TRADING_ENABLED=false
KILL_SWITCH_ENABLED=true
```

The backend does not implement autonomous execution, a Pine interpreter, a strategy engine, or a backtester.
