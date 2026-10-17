from functools import lru_cache
from datetime import date
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = "sqlite:///./jana.db"
    jwt_secret: str = Field(min_length=32)
    token_minutes: int = Field(default=60, ge=1, le=1440)
    demo_password: str | None = Field(default=None, min_length=12)
    academy_demo_as_of: date = date(2026, 10, 17)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    llm_provider: Literal["disabled", "openai_compatible"] = "disabled"
    llm_api_key: str | None = None
    llm_api_url: str = "https://api.openai.com/v1/chat/completions"
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = Field(default=5, ge=1, le=10)
    llm_max_output_tokens: int = Field(default=200, ge=64, le=400)
    zup_mode: Literal["mock", "real"] = "mock"
    zup_base_url: str = "http://127.0.0.1:8300/hs/jana/v1"
    zup_auth_type: Literal["bearer", "basic"] = "bearer"
    zup_api_token: str | None = Field(default=None, min_length=32)
    zup_username: str | None = None
    zup_password: str | None = None
    zup_timeout_seconds: float = Field(default=5, ge=1, le=30)
    zup_verify_tls: bool = True
    zup_ca_bundle: str | None = None
    zup_client_cert: str | None = None
    zup_client_key: str | None = None
    zup_allow_insecure_http: bool = False
    documentolog_mode: Literal["disabled", "mock", "real"] = "disabled"
    documentolog_base_url: str = "https://apibusiness.documentolog.com"
    documentolog_browser_url: str = "https://apibusiness.documentolog.com"
    documentolog_api_key: str | None = Field(default=None, min_length=32)
    documentolog_sender: str | None = None
    documentolog_public_url: str = "http://127.0.0.1:8000"
    documentolog_callback_url: str = "http://127.0.0.1:8000"
    documentolog_timeout_seconds: float = Field(default=10, ge=1, le=30)

    @model_validator(mode="after")
    def validate_zup_connection(self):
        if self.llm_provider != "disabled":
            url = urlparse(self.llm_api_url)
            if (url.scheme != "https" or not url.netloc or url.username or url.password
                    or url.query or url.fragment or not url.path.endswith("/chat/completions")):
                raise ValueError("LLM_API_URL должен быть HTTPS endpoint /chat/completions без учётных данных и query")
            if not self.llm_model.strip():
                raise ValueError("LLM_MODEL не может быть пустым")
        parsed = urlparse(self.zup_base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("ZUP_BASE_URL должен быть абсолютным HTTP(S) URL")
        if self.zup_mode == "real" and parsed.scheme != "https" and not self.zup_allow_insecure_http:
            raise ValueError("Реальная 1С:ЗУП требует HTTPS; для изолированного тестового контура явно задайте ZUP_ALLOW_INSECURE_HTTP=true")
        if self.zup_mode == "real" and not self.zup_verify_tls and not self.zup_allow_insecure_http:
            raise ValueError("Для реальной 1С:ЗУП проверка TLS обязательна; исключение допускается только явной настройкой тестового контура")
        if bool(self.zup_client_cert) != bool(self.zup_client_key):
            raise ValueError("ZUP_CLIENT_CERT и ZUP_CLIENT_KEY задаются вместе")
        if self.documentolog_mode != "disabled":
            for value in (self.documentolog_base_url, self.documentolog_browser_url,
                          self.documentolog_public_url, self.documentolog_callback_url):
                url = urlparse(value)
                if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment:
                    raise ValueError("Documentolog: задайте абсолютные HTTP(S) URL без учётных данных, query и fragment")
                if self.documentolog_mode == "real" and url.scheme != "https":
                    raise ValueError("Реальный Documentolog требует HTTPS для API, файлов и webhook")
            if not self.documentolog_api_key:
                raise ValueError("Задайте DOCUMENTOLOG_API_KEY")
            if self.documentolog_mode == "real" and (not self.documentolog_sender or not self.documentolog_sender.isascii() or not self.documentolog_sender.isdigit() or len(self.documentolog_sender) != 12):
                raise ValueError("DOCUMENTOLOG_SENDER: ИИН/БИН отправителя из 12 цифр")
        return self

    @property
    def zup_tls_verified(self) -> bool:
        return urlparse(self.zup_base_url).scheme == "https" and bool(self.zup_ca_bundle or self.zup_verify_tls)


@lru_cache
def get_settings() -> Settings:
    return Settings()
