# Claude Code Handoff

You are implementing Agentic Forex Desk.

Work ticket-by-ticket. Do not freelance live execution.

## Non-Negotiables

- Live execution is disabled by default.
- Never store credentials in code, prompts, TradingView alerts, or logs.
- All order submission paths must route through the risk engine.
- Every live action requires exact confirmation binding to preview ID, pair, side, entry, stop loss, take profit, lot size, risk amount, and timestamp.
- No stop loss means no trade.
- Expired preview means no trade.
- Kill switch enabled means no trade.
- Unknown pair means no trade.
- Risk violations must return structured errors.
- Broker adapter must be isolated and swappable.

## First Implementation Target

Build a runnable FastAPI + MCP skeleton with:
- health endpoints,
- TradingView webhook receiver,
- watchlist service,
- placeholder market data service,
- technical analysis service stubs,
- chart generation stub,
- risk engine stubs,
- order preview models,
- paper trading adapter,
- test scaffolding.

Do not implement live TradeLocker order submission until API access is verified.
