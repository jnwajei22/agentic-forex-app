from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.routes.forex import router as forex_router
from app.webhooks.tradingview import router as tradingview_router
from app.mcp.server import mcp_app

app = FastAPI(
    title="Agentic Forex Desk",
    version="0.1.0",
    lifespan=mcp_app.lifespan,
)

app.include_router(health_router)
app.include_router(forex_router)
app.include_router(tradingview_router, prefix="/webhooks", tags=["webhooks"])
app.mount("/mcp", mcp_app)
