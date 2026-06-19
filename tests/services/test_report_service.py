import json

from src.schemas.domain import TargetProfile
from src.services.report_service import (
    profile_to_pdf,
    records_to_csv,
    records_to_json,
)


class FakeRecord:
    email = "a@b.com"
    username = "jane"
    password = "pw"
    hashed_password = None
    ip_address = "1.2.3.4"
    database_name = "LeakA"


def test_csv_has_header_and_row() -> None:
    csv = records_to_csv([FakeRecord()])
    assert "email" in csv.splitlines()[0]
    assert "a@b.com" in csv


def test_json_is_list() -> None:
    data = json.loads(records_to_json([FakeRecord()]))
    assert data[0]["email"] == "a@b.com"


def test_pdf_starts_with_magic_bytes() -> None:
    profile = TargetProfile(emails=["a@b.com"], breach_sources={"LeakA": 1})
    pdf = profile_to_pdf("Op", "jane", profile)
    assert pdf[:4] == b"%PDF"
