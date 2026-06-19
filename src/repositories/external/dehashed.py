import asyncio

import httpx
from pydantic import ValidationError

from src.core.exceptions import (
    DehashedAPIError,
    DehashedAuthError,
    DehashedRateLimitError,
)
from src.schemas.dehashed import SearchResponse

_AUTH_HEADER = "Dehashed-Api-Key"


class DehashedClient:
    """Async wrapper over the DeHashed v2 search API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        client: httpx.AsyncClient,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    async def search(
        self,
        query: str,
        page: int = 1,
        size: int = 100,
        wildcard: bool = False,
        regex: bool = False,
    ) -> SearchResponse:
        """POST /search and return a typed SearchResponse.

        Retries on 429 up to max_retries times with exponential backoff.
        Raises DehashedAuthError on 401/403, DehashedRateLimitError when
        retries are exhausted, and DehashedAPIError for any other non-2xx.
        """
        body = {
            "query": query,
            "page": page,
            "size": size,
            "wildcard": wildcard,
            "regex": regex,
        }
        headers = {_AUTH_HEADER: self._api_key, "Content-Type": "application/json"}
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            resp = await self._client.post(
                f"{self._base_url}/search", json=body, headers=headers
            )
            if resp.status_code == 200:
                try:
                    return SearchResponse.model_validate(resp.json())
                except ValidationError as exc:
                    # Unexpected/unparseable 200 body — surface as a domain error
                    # so callers degrade gracefully instead of raising a raw
                    # ValidationError that escapes exception mapping (→ HTTP 500).
                    raise DehashedAPIError(
                        "DeHashed returned an unparseable response body"
                    ) from exc
            if resp.status_code in (401, 403):
                raise DehashedAuthError("DeHashed authentication failed")
            if resp.status_code == 429:
                last_exc = DehashedRateLimitError("rate limited")
                if attempt < self._max_retries:
                    # Exponential backoff; backoff_base=0 in tests to avoid sleeping.
                    await asyncio.sleep(self._backoff_base * (2**attempt))
                    continue
                raise last_exc
            raise DehashedAPIError(f"DeHashed returned {resp.status_code}")
        # Unreachable — 429 path sets last_exc before every continue; loop always
        # returns or raises above this point.
        raise last_exc or DehashedRateLimitError("rate limited (unreachable)")
