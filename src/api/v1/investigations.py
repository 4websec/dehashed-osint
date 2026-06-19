"""Investigations and targets API routes.

Provides CRUD for investigations and targets; routes own the transaction
boundary and commit after each successful write.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_session
from src.repositories.investigations import InvestigationRepository

router = APIRouter(prefix="/v1", tags=["investigations"])


class InvestigationIn(BaseModel):
    name: str
    notes: str | None = None


class TargetIn(BaseModel):
    label: str
    entity_type: str = "person"


@router.post("/investigations")
async def create_investigation(
    body: InvestigationIn, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    """Create a new investigation and return its id and name."""
    repo = InvestigationRepository(session)
    inv = await repo.create(body.name, body.notes)
    await session.commit()
    return {"id": inv.id, "name": inv.name}


@router.get("/investigations")
async def list_investigations(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Return all investigations ordered by creation time descending."""
    repo = InvestigationRepository(session)
    all_inv = await repo.list_all()
    return [{"id": i.id, "name": i.name, "status": i.status} for i in all_inv]


@router.post("/investigations/{investigation_id}/targets")
async def add_target(
    investigation_id: int,
    body: TargetIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Add a target to an existing investigation and return its id and label."""
    repo = InvestigationRepository(session)
    target = await repo.add_target(investigation_id, body.label, body.entity_type)
    await session.commit()
    return {"id": target.id, "label": target.label}
