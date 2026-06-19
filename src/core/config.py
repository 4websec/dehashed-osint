from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration. Secrets never hardcoded."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dehashed_api_key: SecretStr
    dehashed_base_url: str = "https://api.dehashed.com/v2"
    database_url: str
    encryption_key: SecretStr  # base64-encoded 32 bytes
    credit_guard_threshold: int = 100
    app_host: str = "127.0.0.1"
    app_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
