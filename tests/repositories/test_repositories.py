import pytest

from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.schemas.dehashed import RawEntry


@pytest.mark.asyncio
async def test_investigation_target_selector_flow(db_session):
    repo = InvestigationRepository(db_session)
    inv = await repo.create("Op One", notes="n")
    target = await repo.add_target(inv.id, "jane")
    sel = await repo.add_selector(target.id, "email", "jane@x.com")
    assert sel.id is not None
    assert (await repo.get(inv.id)).name == "Op One"


@pytest.mark.asyncio
async def test_search_cache_lookup_and_records(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op Two")
    target = await inv_repo.add_target(inv.id, "jane")
    s_repo = SearchRepository(db_session)
    assert await s_repo.find_by_cache_key("missing") is None
    search = await s_repo.create(
        target.id, "email:x", "{}", "ck1", cost=1, balance_after=99, took="5ms"
    )
    assert (await s_repo.find_by_cache_key("ck1")).id == search.id
    entry = RawEntry(email="a@b.com", password="pw", database_name="X")
    recs = await s_repo.add_records(search.id, target.id, [entry])
    assert recs[0].password == "pw"
    assert len(await s_repo.records_for_target(target.id)) == 1
