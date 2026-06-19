"""Export endpoints: CSV, JSON, and PDF downloads for a target.

All three formats reuse the ReportService functions and CorrelationService
so that the business-logic layer is never bypassed by a serialisation path.
PDF generation uses ReportLab (pure-Python); WeasyPrint is NOT used here.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_session
from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.services.correlation_service import CorrelationService
from src.services.report_service import (
    profile_to_pdf,
    records_to_csv,
    records_to_json,
)

router = APIRouter(prefix="/v1", tags=["exports"])


@router.get("/targets/{target_id}/export.csv")
async def export_csv(
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return all result records for *target_id* as a CSV attachment.

    Content-Type is ``text/csv``; the response carries a
    ``Content-Disposition: attachment`` header so browsers download rather
    than render the file.
    """
    records = await SearchRepository(session).records_for_target(target_id)
    return Response(
        records_to_csv(records),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="target_{target_id}.csv"'
        },
    )


@router.get("/targets/{target_id}/export.json")
async def export_json(
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return all result records for *target_id* as a JSON array.

    Content-Type is ``application/json``.  The response body is a
    pretty-printed JSON array produced by :func:`records_to_json`.
    """
    records = await SearchRepository(session).records_for_target(target_id)
    return Response(
        records_to_json(records),
        media_type="application/json",
    )


@router.get("/targets/{target_id}/report.pdf")
async def report_pdf(
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Render a full TargetProfile report as a PDF attachment.

    Builds the correlated profile via :class:`CorrelationService`, then
    passes it to :func:`profile_to_pdf` (ReportLab-backed).  Returns 404
    when the target or its parent investigation cannot be found.
    """
    inv_repo = InvestigationRepository(session)
    s_repo = SearchRepository(session)

    target = await inv_repo.get_target(target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")

    investigation = await inv_repo.get(target.investigation_id)
    # investigation should always exist if target exists; guard defensively.
    inv_name = investigation.name if investigation is not None else ""

    profile = await CorrelationService(s_repo).build_profile(target_id)
    pdf_bytes = profile_to_pdf(inv_name, target.label, profile)

    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="target_{target_id}.pdf"'
        },
    )
