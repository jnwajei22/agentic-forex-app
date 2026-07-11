from fastmcp import FastMCP

from app.mcp import tools


mcp = FastMCP(
    "Agentic Forex Desk",
    instructions=(
        "Mocked-data forex analysis and risk-checked previews only. "
        "Live trading and broker execution are disabled. For TradeLocker, run "
        "get_tradelocker_accounts first, configure the returned accountId and accNum "
        "as TRADELOCKER_ACCOUNT_ID and TRADELOCKER_ACCOUNT_NUMBER, then restart."
    ),
)

mcp.tool(tools.get_forex_watchlist)
mcp.tool(tools.scan_forex_watchlist)
mcp.tool(tools.generate_chart)
mcp.tool(tools.review_forex_order)
mcp.tool(tools.get_account_status)
mcp.tool(tools.get_open_positions)
mcp.tool(tools.get_trade_log)
mcp.tool(tools.get_tradelocker_accounts)
mcp.tool(tools.get_tradelocker_config)
mcp.tool(tools.get_tradelocker_symbols)
mcp.tool(tools.get_tradelocker_quote)
mcp.tool(tools.get_tradelocker_candles)

mcp_app = mcp.http_app(path="/", stateless_http=True)
