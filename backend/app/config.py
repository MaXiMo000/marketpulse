from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Hosts hand out `postgres://` or `postgresql://`; SQLAlchemy needs the driver named explicitly."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 'development' allows an empty API_TOKEN and serves API docs; any other value is treated as production
    app_env: str = "development"
    api_token: str = ""
    database_url: str = "sqlite:///./marketpulse.db"
    twelvedata_api_key: str = ""
    twelvedata_min_interval_s: float = 8.0
    cors_origins: str = "http://localhost:5173"
    # Number of trusted reverse proxies in front of the API. 0 ignores X-Forwarded-For entirely (it can be forged);
    # behind one proxy (for example Render) set 1 so rate limiting sees the real client address.
    proxy_hops: int = 0
    # Optional email alerts for band flips; off unless smtp_host and alert_email_to are both set
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_from: str = ""
    alert_email_to: str = ""

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        return normalize_database_url(v)


settings = Settings()
