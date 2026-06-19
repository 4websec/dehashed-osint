"""HTMX-driven server-rendered web UI routes.

Renders Jinja2 templates for investigations, target detail, search results
(partial), pivot graph, and the authorization gate.
"""

from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import escape
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db import get_session
from src.core.exceptions import DehashedError, InsufficientCreditsError
from src.repositories.external.dehashed import DehashedClient
from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.services.correlation_service import CorrelationService
from src.services.query_builder import ALLOWED_FIELDS
from src.services.search_service import SearchService

router = APIRouter()

# Resolve templates directory relative to this file's location so the path is
# stable regardless of the working directory at runtime.
_TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent.parent / "templates")
_templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/authorize", response_class=HTMLResponse)
async def authorize_form(request: Request) -> HTMLResponse:
    """Render the authorization acknowledgement form."""
    return _templates.TemplateResponse(request, "authorize.html")


@router.post("/authorize")
async def authorize_submit(ack: str = Form(...)) -> RedirectResponse:
    """Accept acknowledgement, set the auth cookie, redirect to home."""
    # ack value is intentionally unused beyond being required — its presence
    # in the POST body confirms the user clicked the consent button.
    _ = ack
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("osint_authorized", "1", httponly=True, samesite="strict")
    return resp


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Render the investigations list page."""
    investigations = await InvestigationRepository(session).list_all()
    return _templates.TemplateResponse(
        request,
        "investigations.html",
        {"investigations": investigations},
    )


@router.post("/ui/investigations", response_class=HTMLResponse)
async def create_investigation_ui(
    request: Request,
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """HTMX partial: create investigation and return a single <li> fragment."""
    inv = await InvestigationRepository(session).create(name)
    await session.commit()
    # Return a minimal HTML fragment; HTMX swaps it into the list.
    # inv.id is an int PK (safe); inv.name is user input — escape to prevent stored XSS.
    return HTMLResponse(
        f'<li><a href="/ui/investigations/{inv.id}">{escape(inv.name)}</a></li>'
    )


@router.get("/ui/investigations/{investigation_id}", response_class=HTMLResponse)
async def investigation_page(
    request: Request,
    investigation_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Render an investigation's detail page: its targets + an add-target form."""
    repo = InvestigationRepository(session)
    investigation = await repo.get(investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    targets = await repo.list_targets(investigation_id)
    return _templates.TemplateResponse(
        request,
        "investigation.html",
        {"investigation": investigation, "targets": targets},
    )


@router.post(
    "/ui/investigations/{investigation_id}/targets", response_class=HTMLResponse
)
async def create_target_ui(
    request: Request,
    investigation_id: int,
    label: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """HTMX partial: create a target under an investigation, return an <li>."""
    repo = InvestigationRepository(session)
    if await repo.get(investigation_id) is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    target = await repo.add_target(investigation_id, label)
    await session.commit()
    # target.id is an int PK (safe); label is user input — escape to prevent XSS.
    return HTMLResponse(
        f'<li><a href="/ui/targets/{target.id}">{escape(target.label)}</a></li>'
    )


@router.get("/ui/targets/{target_id}", response_class=HTMLResponse)
async def target_page(
    request: Request,
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Render the target detail page with existing result records."""
    repo = InvestigationRepository(session)
    target = await repo.get_target(target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    records = await SearchRepository(session).records_for_target(target_id)
    return _templates.TemplateResponse(
        request,
        "target.html",
        {
            "target": target,
            "records": records,
            "fields": sorted(ALLOWED_FIELDS),
            "target_id": target_id,
            "profile": None,
        },
    )


@router.post("/ui/targets/{target_id}/search", response_class=HTMLResponse)
async def search_ui(
    request: Request,
    target_id: int,
    field: str = Form(...),
    value: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """HTMX partial: run a DeHashed search, persist, return results table."""
    from src.services.query_builder import build_query  # local import avoids circular

    settings = get_settings()
    query = build_query(field, value)

    try:
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
            await svc.run_search(target_id, query)
    except (InsufficientCreditsError, DehashedError) as exc:
        # Return a friendly HTML fragment instead of a 500; HTMX swaps it in.
        return HTMLResponse(
            f'<p class="error">Search failed: {escape(str(exc))}</p>',
            status_code=200,
        )

    await session.commit()

    s_repo = SearchRepository(session)
    records = await s_repo.records_for_target(target_id)
    profile = await CorrelationService(s_repo).build_profile(target_id)

    return _templates.TemplateResponse(
        request,
        "_results.html",
        {"records": records, "target_id": target_id, "profile": profile},
    )


@router.get("/ui/targets/{target_id}/graph", response_class=HTMLResponse)
async def graph_page(
    request: Request,
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Render the Cytoscape.js pivot-graph page for *target_id*."""
    target = await InvestigationRepository(session).get_target(target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return _templates.TemplateResponse(request, "graph.html", {"target": target})
