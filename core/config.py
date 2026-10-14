from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    openrouter_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    app_name: str = "Ritm Productivity PWA"
    app_url: str = "http://localhost:5173"
    debug: bool = False
    log_file: str = "logs/productivity.log"

    @field_validator("openrouter_base_url", "app_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("A valid HTTP(S) URL is required")
        return value.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
