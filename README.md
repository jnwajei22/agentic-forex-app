# Agentic Forex Desk

Agentic Forex Desk is a focused forex research and execution-data backend for ChatGPT. It retrieves and normalizes financial data; ChatGPT performs chart rendering, technical analysis, screening, backtesting, scenarios, forecasts, and final trade planning.

## Provider authority

- **TradeLocker** is authoritative for the connected user's broker account, symbols, bid/ask quotes, spreads, forex candles used for execution analysis, balance, equity, margin, positions, pending orders, and deterministic risk-reviewed order previews.
- **Finnhub** supplies optional economic-calendar events, concise market news, cross-market context, and explicitly selected secondary forex data when the configured subscription permits it.
- **FRED/ALFRED** supplies official macroeconomic metadata, observations, release dates, real-time periods, and revision-aware historical context.
- **ChatGPT** calculates indicators, Fibonacci levels, support/resistance, strategies, forecasts, and renders charts from canonical candles.
- **TradingView webhook** is optional untrusted inbound alert data. It is disabled without a secret, is not verified market data, and cannot place trades.

Finnhub and FRED values never replace TradeLocker prices for entry, stops, sizing, margin, previews, or execution. Source disagreements remain separate and explicitly labeled; the backend never averages or synthesizes cross-provider prices.

## Why server-side charting was removed

PNG generation duplicated work ChatGPT can perform interactively, created filesystem artifacts, enlarged the deployment, and encouraged the server to mix retrieval with analysis. The backend now returns canonical `MarketSeries` JSON only.

When a user asks for a chart:

1. ChatGPT calls `get_market_candles` with the requested range.
2. It verifies `complete`, `actual_start`, `actual_end`, and `candles_returned`.
3. It renders candles and calculates requested indicators client-side.
4. It must not claim a chart exists unless it visibly renders one.

## Main MCP tools

- `get_market_candles`: canonical TradeLocker or explicitly selected Finnhub OHLCV.
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

Both public providers use isolated in-process TTL caches. TradeLocker account state is never cached across users. A persistent cache can replace the small cache interface on a Raspberry Pi later without changing provider clients.

## Deployment

Install dependencies with `pip install -r requirements.txt`, add the optional provider variables, and restart the backend. No database migration is required. Disconnect and reconnect the ChatGPT app after deployment so it refreshes the MCP tool schema.

The Vercel onboarding frontend requires no code change. For Raspberry Pi deployments, keep system time synchronized, protect `.env`, use persistent PostgreSQL as already supported, and expect the in-process public-data cache to clear on restart.

Live trading remains disabled and the kill switch enabled:

```text
LIVE_TRADING_ENABLED=false
KILL_SWITCH_ENABLED=true
```

The backend does not implement autonomous execution, a Pine interpreter, a strategy engine, or a backtester.
