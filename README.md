# Agentic Forex Desk

Private chat-based forex scanner, charting, paper-trading, and controlled execution backend.

The first usable version should **not place live trades**. It should scan, chart, explain, create risk-checked previews, and paper trade. Live execution stays disabled until broker API access, paper tests, risk tests, kill switch, and strict confirmation handling are verified.

## MVP Build Order

1. MCP server skeleton
2. Watchlist + candle retrieval
3. Technical analysis engine
4. Fibonacci + support/resistance
5. Chart generation
6. Chat scan tool
7. Order preview tool
8. Risk engine
9. Paper trading
10. Broker adapter
11. Live submit with strict confirmation

## Core Rule

No live order is submitted unless:
- live mode is enabled server-side,
- kill switch is disabled,
- preview is valid and unexpired,
- risk engine passes,
- the exact confirmation phrase is provided,
- broker adapter returns a valid order response.

Vague confirmations like `yes`, `go ahead`, `do it`, or `bet` must never execute a live trade.
