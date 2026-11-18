from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./marketpulse.db"
    redis_url: str = "redis://localhost:6379"
    twelvedata_api_key: str = ""
    twelvedata_min_interval_s: float = 8.0
    cors_origins: str = "http://localhost:5173"
    # Optional email alerts for band flips; off unless smtp_host and alert_email_to are both set
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_from: str = ""
    alert_email_to: str = ""


settings = Settings()
