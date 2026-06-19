"""Searches, profile, and pivot-graph API routes.

Each request builds a DehashedClient around a fresh httpx.AsyncClient context
manager so connections are always closed after the request completes.  The
route owns the transaction: it calls session.commit() after a successful write.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db import get_session
from src.core.exceptions import DehashedAuthError, InsufficientCreditsError
from src.repositories.external.dehashed import DehashedClient
from src.repositories.searches import SearchRepository
from src.services.correlation_service import CorrelationService
from src.services.query_builder import build_query
from src.services.search_service import SearchService

router = APIRouter(prefix="/v1", tags=["searches"])


class SearchIn(BaseModel):
    field: str
    value: str


@router.post("/targets/{target_id}/searches")
async def run_search(
    target_id: int,
    body: SearchIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Run a DeHashed search for *target_id* and persist the results.

    Maps domain exceptions to HTTP status codes:
    - ValueError (disallowed field) → 422
    - InsufficientCreditsError → 402
    - DehashedAuthError → 502
    """
    settings = get_settings()

    # Validate and build the query string before touching the network.
    try:
        query = build_query(body.field, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with httpx.AsyncClient(timeout=30) as hc:
        client = DehashedClient(
            settings.dehashed_api_key.get_secret_value(),
            settings.dehashed_base_url,
            hc,
        )
        svc = SearchService(
            SearchRepository(session),
            client,
            settings.credit_guard_threshold,
        )
        try:
            search = await svc.run_search(target_id, query)
        except InsufficientCreditsError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        except DehashedAuthError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Commit only after the async client has closed cleanly.
    await session.commit()
    return {
        "search_id": search.id,
        "cost": search.cost,
        "balance_after": search.balance_after,
    }


@router.get("/targets/{target_id}/profile")
async def get_profile(
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Return the deduplicated TargetProfile for *target_id*."""
    profile = await CorrelationService(SearchRepository(session)).build_profile(
        target_id
    )
    return profile.model_dump()


@router.get("/targets/{target_id}/graph")
async def get_graph(
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[dict[str, object]]]:
    """Return a Cytoscape-compatible graph for *target_id*.

    Node id format: ``"{field}:{value}"`` (e.g. ``"email:a@b.com"``).
    A ``target:{target_id}`` root node is always included, with directed
    edges from it to each email/username/ip_address selector node.
    """
    profile = await CorrelationService(SearchRepository(session)).build_profile(
        target_id
    )
    nodes: list[dict[str, object]] = [
        {"data": {"id": f"target:{target_id}", "label": "TARGET", "kind": "target"}}
    ]
    edges: list[dict[str, object]] = []

    field_map: list[tuple[str, list[str]]] = [
        ("email", profile.emails),
        ("username", profile.usernames),
        ("ip_address", profile.ip_addresses),
    ]
    for field, values in field_map:
        for value in values:
            node_id = f"{field}:{value}"
            nodes.append({"data": {"id": node_id, "label": value, "kind": field}})
            edges.append(
                {"data": {"source": f"target:{target_id}", "target": node_id}}
            )

    return {"nodes": nodes, "edges": edges}
