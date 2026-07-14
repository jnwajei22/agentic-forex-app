from fastmcp import FastMCP

from app.mcp import tools


mcp = FastMCP(
    "Agentic Forex Desk",
    instructions=(
        "Use get_tradelocker_connection_status to check setup. When a tool returns "
        "setup_required, give the setup_url to the user. They should connect "
        "TradeLocker with the same Auth0 account, return to ChatGPT, and retry."
    ),
)

mcp.tool(tools.get_forex_watchlist)
mcp.tool(tools.scan_forex_watchlist)
mcp.tool(tools.get_forex_chart_data)
mcp.tool(tools.generate_static_forex_chart)
mcp.tool(tools.generate_chart)
mcp.tool(tools.analyze_multi_timeframe)
mcp.tool(tools.generate_multi_timeframe_report)
mcp.tool(tools.review_forex_order)
mcp.tool(tools.get_account_status)
mcp.tool(tools.get_open_positions)
mcp.tool(tools.get_trade_log)
mcp.tool(tools.get_tradelocker_connection_status)
mcp.tool(tools.get_my_broker_connection_status)
mcp.tool(tools.get_my_tradelocker_accounts)
mcp.tool(tools.get_my_tradelocker_account_status)
mcp.tool(tools.get_my_tradelocker_symbols)
mcp.tool(tools.get_my_tradelocker_quote)
mcp.tool(tools.get_my_tradelocker_candles)
mcp.tool(tools.get_tradelocker_accounts)
mcp.tool(tools.get_tradelocker_config)
mcp.tool(tools.get_tradelocker_symbols)
mcp.tool(tools.get_tradelocker_quote)
mcp.tool(tools.get_tradelocker_candles)

mcp_app = mcp.http_app(path="/", stateless_http=True)
