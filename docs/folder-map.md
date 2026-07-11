# Folder Map

```text
agentic-forex-desk/
  app/
    api/routes/              FastAPI HTTP routes
    mcp/                     MCP-exposed tools
    config/                  settings and environment config
    db/                      SQL schema and migrations
    models/                  Pydantic request/response/domain models
    services/
      market_data/           broker/provider candle and quote retrieval
      technical_analysis/    trend, swings, fibs, S/R, scoring
      charting/              mplfinance/matplotlib chart generation
      risk/                  hard risk checks and position sizing
      trading/               previews, confirmation, trade flow
      reports/               9:00, 11:00, 1:30 CT scheduled scans
      logging/               audit and risk logs
    brokers/
      base.py                adapter interface
      paper/                 paper trading adapter
      tradelocker/           TradeLocker adapter, disabled until verified
    webhooks/                TradingView webhook receiver
    jobs/                    scheduled scan/report jobs
  tests/
    unit/
    integration/
    fixtures/
  storage/
    charts/
    logs/
```
