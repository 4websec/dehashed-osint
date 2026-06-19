"""SearchService: orchestrates DeHashed queries with caching, credit-guard,
persistence, and audit logging.

Flow for run_search:
  1. Compute a stable cache_key from (query, {page, size}).
  2. If a matching Search row already exists, return it immediately — no API
     call, no credit spend.
  3. Call the DeHashed client.
  4. Credit-guard: check the balance the API *returns*.  The search has already
     happened at this point, so this guards FUTURE spend rather than blocking
     the current call.  A true pre-spend block would require a separate
     get_balance() round-trip; add that when/if DeHashed exposes a cheap probe
     endpoint.  Tracked as a follow-up.
  5. Persist the Search row, ResultRecord rows, and an AuditLog entry.
  6. Return the persisted Search.
"""

import json
from typing import Protocol

from src.core.exceptions import InsufficientCreditsError
from src.models import Search
from src.repositories.searches import SearchRepository
from src.schemas.dehashed import SearchResponse
from src.services.query_builder import cache_key


class _Client(Protocol):
    """Structural type for any object that can call the DeHashed search API.

    Using a Protocol here (rather than importing the concrete DehashedClient)
    keeps this module decoupled from the HTTP layer and makes FakeClient-based
    unit tests trivial.
    """

    async def search(
        self,
        query: str,
        page: int = 1,
        size: int = 100,
        wildcard: bool = False,
        regex: bool = False,
    ) -> SearchResponse: ...


class SearchService:
    """Runs DeHashed searches with caching, credit-guard, persistence, audit."""

    def __init__(
        self, repo: SearchRepository, client: _Client, threshold: int
    ) -> None:
        self._repo = repo
        self._client = client
        # Minimum acceptable post-call balance before refusing further spend.
        self._threshold = threshold

    async def run_search(
        self, target_id: int, query: str, page: int = 1, size: int = 100
    ) -> Search:
        """Execute a DeHashed search, using the cache when possible.

        Args:
            target_id: FK to the Target this search belongs to.
            query: Raw DeHashed query string, e.g. ``email:"foo@bar.com"``.
            page: Result page (1-indexed).
            size: Max results per page (default 100, DeHashed max).

        Returns:
            The persisted Search ORM object (new or cached).

        Raises:
            InsufficientCreditsError: Post-call balance is at or below
                ``threshold``; the result is NOT persisted in this case.
        """
        params: dict[str, object] = {"page": page, "size": size}
        key = cache_key(query, params)

        cached = await self._repo.find_by_cache_key(key)
        if cached is not None:
            # Identical query already persisted; return it without spending.
            return cached

        response = await self._client.search(query, page=page, size=size)

        # Credit-guard: the API has already deducted credits for the call above.
        # We raise here to stop *future* calls when balance is critically low.
        # See module docstring for a note on true pre-spend blocking.
        if response.balance <= self._threshold:
            raise InsufficientCreditsError(response.balance, self._threshold)

        search = await self._repo.create(
            target_id=target_id,
            query=query,
            params=json.dumps(params, sort_keys=True),
            cache_key=key,
            # Cost is the number of records returned; floor at 1 so a 0-result
            # search still registers as 1 credit spent.
            cost=max(response.total, 1),
            balance_after=response.balance,
            took=response.took,
        )
        await self._repo.add_records(search.id, target_id, response.entries)
        await self._repo.write_audit("search", query, search.cost)
        return search
