from fastmcp import FastMCP

from app.mcp import tools


mcp = FastMCP(
    "Agentic Forex Desk",
    instructions=(
        "This server retrieves financial data; it does not render charts or provide "
        "technical analysis, forecasts, or trade recommendations. When the user asks "
        "for a chart: call get_market_candles for the requested symbol, timeframe, and "
        "range; verify complete, actual_start, actual_end, and candles_returned; then "
        "render the chart and calculate requested indicators client-side. Never say a "
        "chart was generated unless it is visibly rendered in the conversation. If the "
        "client cannot render it, state that limitation. Never use Finnhub or FRED as a "
        "TradeLocker execution price. For setup_required responses, give the setup_url "
        "to the user and ask them to connect with the same Auth0 account before retrying."
    ),
)

mcp.tool(tools.get_forex_watchlist)
mcp.tool(tools.get_market_candles)
mcp.tool(tools.get_watchlist_market_data)
mcp.tool(tools.get_economic_calendar)
mcp.tool(tools.get_market_news)
mcp.tool(tools.search_macro_series)
mcp.tool(tools.get_macro_series)
mcp.tool(tools.get_macro_release_calendar)
mcp.tool(tools.get_forex_research_bundle)
mcp.tool(tools.get_provider_capabilities)
mcp.tool(tools.review_forex_order)
mcp.tool(tools.set_kill_switch)
mcp.tool(tools.get_account_status)
mcp.tool(tools.get_open_positions)
mcp.tool(tools.get_pending_orders)
mcp.tool(tools.get_trade_history)
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

mcp_app = mcp.http_app(path="/", stateless_http=True)
