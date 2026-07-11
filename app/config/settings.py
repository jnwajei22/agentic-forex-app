from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    app_timezone: str = "America/Chicago"

    database_url: str | None = None
    tradingview_webhook_secret: str | None = None

    live_trading_enabled: bool = False
    kill_switch_enabled: bool = True

    default_max_risk_percent: float = 0.5
    default_max_daily_loss_percent: float = 2.0
    default_max_weekly_loss_percent: float = 5.0
    default_min_reward_risk: float = 1.5

    tradelocker_api_base_url: str | None = None
    tradelocker_api_key: str | None = None
    tradelocker_api_secret: str | None = None
    tradelocker_account_id: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
