import httpx
import pytest
import respx

from src.core.exceptions import (
    DehashedAuthError,
    DehashedRateLimitError,
)
from src.repositories.external.dehashed import DehashedClient

BASE = "https://api.dehashed.com/v2"


@pytest.mark.asyncio
@respx.mock
async def test_search_parses_response():
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance": 500,
                "total": 1,
                "took": "5ms",
                "entries": [
                    {"email": "a@b.com", "password": "pw", "database_name": "X"}
                ],
            },
        )
    )
    async with httpx.AsyncClient() as hc:
        client = DehashedClient("key", BASE, hc)
        resp = await client.search('email:"a@b.com"')
    assert resp.balance == 500
    assert resp.entries[0].email == "a@b.com"


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_auth_error():
    respx.post(f"{BASE}/search").mock(return_value=httpx.Response(401))
    async with httpx.AsyncClient() as hc:
        client = DehashedClient("key", BASE, hc)
        with pytest.raises(DehashedAuthError):
            await client.search("email:x")


@pytest.mark.asyncio
@respx.mock
async def test_429_retries_then_raises():
    route = respx.post(f"{BASE}/search").mock(return_value=httpx.Response(429))
    async with httpx.AsyncClient() as hc:
        client = DehashedClient("key", BASE, hc, max_retries=2, backoff_base=0)
        with pytest.raises(DehashedRateLimitError):
            await client.search("email:x")
    assert route.call_count == 3  # initial + 2 retries
