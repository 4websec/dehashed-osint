import httpx
import pytest
import respx

from src.core.exceptions import (
    DehashedAPIError,
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
async def test_search_flattens_dehashed_v2_array_fields():
    """DeHashed v2 returns fields as arrays; RawEntry must normalize to str."""
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance": 500,
                "total": 2,
                "entries": [
                    {
                        "email": ["adriennebalkum@gmail.com"],
                        "username": ["AdrienneBalkum"],
                        "name": ["Adrienne Balkum"],
                        "database_name": "LeakA",  # scalar still works
                    },
                    {
                        "email": ["a@b.com", "a2@b.com"],  # multi-valued -> joined
                        "hashed_password": ["$2a$08$abc"],
                    },
                ],
            },
        )
    )
    async with httpx.AsyncClient() as hc:
        client = DehashedClient("key", BASE, hc)
        resp = await client.search('email:"adriennebalkum@gmail.com"')
    assert resp.entries[0].email == "adriennebalkum@gmail.com"
    assert resp.entries[0].username == "AdrienneBalkum"
    assert resp.entries[0].database_name == "LeakA"
    assert resp.entries[1].email == "a@b.com, a2@b.com"
    assert resp.entries[1].hashed_password == "$2a$08$abc"


@pytest.mark.asyncio
@respx.mock
async def test_unparseable_body_raises_api_error():
    """A 200 with an unexpected shape becomes DehashedAPIError, not a raw
    pydantic ValidationError (which would escape to an HTTP 500)."""
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(200, json={"entries": "not-a-list"})
    )
    async with httpx.AsyncClient() as hc:
        client = DehashedClient("key", BASE, hc)
        with pytest.raises(DehashedAPIError):
            await client.search("email:x")


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
