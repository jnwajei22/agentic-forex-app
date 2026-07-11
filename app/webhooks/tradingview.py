from fastapi import APIRouter, Header, HTTPException
from app.config.settings import settings
from app.models.webhooks import TradingViewSignal
from app.services.watchlist import is_allowed_pair, normalize_pair

router = APIRouter()

@router.post("/tradingview")
async def receive_tradingview_signal(
    payload: TradingViewSignal,
    x_tradingview_secret: str | None = Header(default=None),
):
    if not settings.tradingview_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret is not configured.")

    if x_tradingview_secret != settings.tradingview_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")

    pair = normalize_pair(payload.pair)
    if not is_allowed_pair(pair):
        raise HTTPException(status_code=400, detail="Pair is not allowed.")

    return {
        "status": "accepted_untrusted",
        "pair": pair,
        "timeframe": payload.timeframe,
        "strategy": payload.strategy,
        "message": "Signal stored as untrusted until backend analysis confirms it.",
    }
