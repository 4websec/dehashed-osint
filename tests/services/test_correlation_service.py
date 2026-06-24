import pytest

from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.schemas.dehashed import RawEntry
from src.services.correlation_service import CorrelationService, identify_hash_type


@pytest.mark.parametrize(
    "value,expected",
    [
        ("5f4dcc3b5aa765d61d8327deb882cf99", "MD5"),
        ("aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d", "SHA-1"),
        ("a" * 64, "SHA-256"),
        ("$2b$12$" + "a" * 53, "bcrypt"),
        # DeHashed-annotated forms: "<hash>[:salt]||<Algorithm>"
        ("$2a$08$" + "a" * 53 + ":None||Blowfish(OpenBSD)", "bcrypt"),
        ("5f4dcc3b5aa765d61d8327deb882cf99:salt||MD5", "MD5"),
        ("notahash", "unknown"),
    ],
)
def test_identify_hash_type(value, expected):
    assert identify_hash_type(value) == expected


@pytest.mark.asyncio
async def test_build_profile_dedups_and_maps(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op")
    target = await inv_repo.add_target(inv.id, "jane")
    s_repo = SearchRepository(db_session)
    s = await s_repo.create(target.id, "q", "{}", "ck", 1, 99, "1ms")
    await s_repo.add_records(
        s.id,
        target.id,
        [
            RawEntry(email="a@b.com", password="reuse", database_name="LeakA"),
            RawEntry(email="a@b.com", password="reuse", database_name="LeakB"),
            RawEntry(username="jane", password="other", database_name="LeakA"),
        ],
    )
    profile = await CorrelationService(s_repo).build_profile(target.id)
    assert profile.emails == ["a@b.com"]  # deduped
    assert "reuse" in profile.reused_passwords  # appears in 2 breaches
    # 2 distinct breaches; "other" (single source) is excluded
    assert profile.reuse_counts == {"reuse": 2}
    assert profile.breach_sources == {"LeakA": 2, "LeakB": 1}
