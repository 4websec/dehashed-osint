"""Report export service: CSV, JSON, and PDF (via ReportLab).

PDF generation uses ReportLab (pure-Python, no native deps) instead of
WeasyPrint, which cannot load its native libraries on Windows hosts.
"""

import csv
import io
import json
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from src.schemas.domain import TargetProfile

# Fields exported in all tabular formats — order matches DeHashed response shape.
_CSV_FIELDS: list[str] = [
    "email",
    "username",
    "password",
    "hashed_password",
    "ip_address",
    "database_name",
]


def records_to_csv(records: list[Any]) -> str:
    """Serialise *records* to a CSV string with a header row.

    Args:
        records: Any objects exposing the ``_CSV_FIELDS`` attributes
            (missing attributes silently become ``None``).

    Returns:
        UTF-8 CSV text with CRLF line endings (csv module default).
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for r in records:
        writer.writerow({f: getattr(r, f, None) for f in _CSV_FIELDS})
    return buf.getvalue()


def records_to_json(records: list[Any]) -> str:
    """Serialise *records* to a JSON array string.

    Args:
        records: Any objects exposing the ``_CSV_FIELDS`` attributes.

    Returns:
        Pretty-printed JSON (indent=2).
    """
    return json.dumps(
        [{f: getattr(r, f, None) for f in _CSV_FIELDS} for r in records],
        indent=2,
    )


def profile_to_pdf(
    investigation_name: str,
    target_label: str,
    profile: TargetProfile,
) -> bytes:
    """Render a ``TargetProfile`` to a PDF document and return its bytes.

    Uses ReportLab's ``SimpleDocTemplate`` / Platypus flowable pipeline so
    that no native libraries are required.  The returned bytes always start
    with ``b"%PDF"`` as guaranteed by the ReportLab engine.

    Args:
        investigation_name: Human-readable name of the investigation.
        target_label: Identifier for the target (e.g. email or username).
        profile: Aggregated target intelligence from the correlation service.

    Returns:
        Raw PDF bytes beginning with the ``%PDF`` magic.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    styles = getSampleStyleSheet()
    flowables: list[Any] = []

    # ── Title ──────────────────────────────────────────────────────────────
    # xml_escape prevents ReportLab from misinterpreting markup characters in
    # untrusted investigation names and target labels (e.g. "<script>" in a
    # breach-derived username would corrupt the PDF paragraph XML parser).
    title_text = (
        f"<b>Investigation: {xml_escape(investigation_name)}"
        f" — Target: {xml_escape(target_label)}</b>"
    )
    flowables.append(Paragraph(title_text, styles["Title"]))
    flowables.append(Spacer(1, 0.25 * inch))

    # ── Emails ─────────────────────────────────────────────────────────────
    email_list = (
        ", ".join(xml_escape(e) for e in profile.emails) if profile.emails else "—"
    )
    flowables.append(Paragraph(f"<b>Emails:</b> {email_list}", styles["Normal"]))
    flowables.append(Spacer(1, 0.1 * inch))

    # ── Usernames ──────────────────────────────────────────────────────────
    username_list = (
        ", ".join(xml_escape(u) for u in profile.usernames)
        if profile.usernames
        else "—"
    )
    flowables.append(Paragraph(f"<b>Usernames:</b> {username_list}", styles["Normal"]))
    flowables.append(Spacer(1, 0.1 * inch))

    # ── Reused passwords ───────────────────────────────────────────────────
    reused_count = len(profile.reused_passwords)
    flowables.append(
        Paragraph(
            f"<b>Reused passwords:</b> {reused_count}",
            styles["Normal"],
        )
    )
    flowables.append(Spacer(1, 0.1 * inch))

    # ── Breach sources ─────────────────────────────────────────────────────
    flowables.append(Paragraph("<b>Breach sources:</b>", styles["Normal"]))
    flowables.append(Spacer(1, 0.05 * inch))

    if profile.breach_sources:
        # Render as a two-column table: [Source name | Hit count]
        table_data: list[list[str]] = [["Source", "Count"]]
        for source, count in profile.breach_sources.items():
            table_data.append([source, str(count)])
        flowables.append(Table(table_data))
    else:
        flowables.append(Paragraph("No breach sources recorded.", styles["Normal"]))

    doc.build(flowables)
    return buf.getvalue()
