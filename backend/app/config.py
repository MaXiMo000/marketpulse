from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./marketpulse.db"
    redis_url: str = "redis://localhost:6379"
    twelvedata_api_key: str = ""
    twelvedata_min_interval_s: float = 8.0
    cors_origins: str = "http://localhost:5173"


settings = Settings()
