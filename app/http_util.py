from __future__ import annotations

import random
import time
from typing import Any

import httpx

from app.config import settings

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,zh-CN;q=0.7",
}


def sleep_jitter(low: float = 1.5, high: float = 4.5) -> None:
    time.sleep(random.uniform(low, high))


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 4,
) -> httpx.Response:
    last_exc: Exception | None = None
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params, headers=merged)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise httpx.HTTPStatusError(
                    f"retryable {response.status_code}",
                    request=response.request,
                    response=response,
                )
            if response.status_code >= 400:
                raise RuntimeError(f"GET {response.status_code}: {url}")
            return response
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 — collectors must never crash the job
            last_exc = exc
            time.sleep((2 ** attempt) + random.random())
    raise RuntimeError(f"GET failed after {attempts} attempts: {url}") from last_exc


def json_client() -> httpx.Client:
    return httpx.Client(timeout=settings.request_timeout, follow_redirects=True, headers=DEFAULT_HEADERS)
