from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    app_timezone: str = "America/Chicago"
    public_base_url: str = "https://mcp.justinnwajei.com"
    frontend_origin: str = "https://app.agenticforexdesk.com"
    chatgpt_return_url: str = "https://chatgpt.com"
    oauth_authorization_url: str | None = None
    oauth_token_url: str | None = None
    oauth_transaction_secret: str | None = None
    oauth_allowed_client_ids: str | None = None
    onboarding_assertion_secret: str | None = None
    onboarding_assertion_issuers: str | None = None
    sqlite_path: str = "storage/app.db"
    broker_secret_key: str | None = None
    allow_env_broker_fallback: bool = False

    database_url: str | None = None
    tradingview_webhook_secret: str | None = None
    mcp_shared_secret: str | None = None
    mcp_allow_public_no_auth: bool = False
    mcp_require_oauth: bool = True
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None

    live_trading_enabled: bool = False
    kill_switch_enabled: bool = True
    market_data_provider: str = "mock"

    default_max_risk_percent: float = 0.5
    default_max_daily_loss_percent: float = 2.0
    default_max_weekly_loss_percent: float = 5.0
    default_min_reward_risk: float = 1.5

    tradelocker_environment: str = "demo"
    tradelocker_base_url: str = "https://demo.tradelocker.com/backend-api"
    tradelocker_username: str | None = None
    tradelocker_password: str | None = None
    tradelocker_server: str | None = None
    tradelocker_account_id: str | None = None
    tradelocker_account_number: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
