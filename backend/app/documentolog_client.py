"""Documentolog Business public API. Platform requires its own agreed adapter.

The public create-session endpoint does not document idempotency or status lookup.
Never automatically replay it after an uncertain response.
"""
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException

from app.config import get_settings


class DocumentologClient:
    def __init__(self, base_url, browser_url, api_key, *, mode="real", timeout=10, transport=None):
        self.base_url = base_url.rstrip("/")
        self.browser_url = browser_url.rstrip("/")
        self.api_key, self.mode, self.timeout, self.transport = api_key, mode, timeout, transport

    def create_session(self, payload: dict, command_key: str) -> str:
        headers = {"api-key": self.api_key, "User-Agent": "JanaMen-Documentolog/1.0"}
        # This guarantee belongs to our mock only, not Documentolog Business.
        if self.mode == "mock":
            headers["Idempotency-Key"] = command_key
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                response = client.post(self.base_url + "/json/external/oauth/token", headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            token = result["data"]["access_token"]
            if result["status"] != 1 or not isinstance(token, str) or not token or len(token) > 16000:
                raise ValueError("Invalid response")
            return self.browser_url + "/external/sign/embedded?" + urlencode({"sParams": token})
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            # Never expose upstream bodies, URLs with credentials, or API keys.
            raise HTTPException(503, "Результат Documentolog не подтверждён. Нужна сверка в Documentolog; автоматический повтор отключён во избежание дубля.") from error

    def safe_view_url(self, value: str | None) -> str | None:
        if not value or len(value) > 2000:
            return None
        try:
            url, expected = urlparse(value), urlparse(self.browser_url)
        except ValueError:
            return None
        if url.scheme == expected.scheme and url.netloc == expected.netloc and not url.username and not url.password and not url.fragment:
            return value
        return None


def documentolog_client():
    settings = get_settings()
    if settings.documentolog_mode == "disabled":
        raise HTTPException(503, "Documentolog не настроен")
    return DocumentologClient(settings.documentolog_base_url, settings.documentolog_browser_url,
        settings.documentolog_api_key, mode=settings.documentolog_mode,
        timeout=settings.documentolog_timeout_seconds)
