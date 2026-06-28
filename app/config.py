from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Brain V2"
    app_env: str = "local"
    database_url: str = "sqlite:///./ai_brain.db"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_timeout_seconds: float = 20.0
    telegram_bot_token: Optional[str] = None
    telegram_max_response_chars: int = 2500
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def empty_api_key_as_none(cls, value: Optional[str]) -> Optional[str]:
        if value == "":
            return None
        return value

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def empty_telegram_token_as_none(cls, value: Optional[str]) -> Optional[str]:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
