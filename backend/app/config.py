from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./jana.db"
    jwt_secret: str = Field(min_length=32)
    token_minutes: int = Field(default=60, ge=1, le=1440)
    demo_password: str | None = Field(default=None, min_length=12)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
