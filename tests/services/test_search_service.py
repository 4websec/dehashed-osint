import pytest

from src.core.exceptions import InsufficientCreditsError
from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.schemas.dehashed import RawEntry, SearchResponse
from src.services.search_service import SearchService


class FakeClient:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls = 0

    async def search(self, query, page=1, size=100, wildcard=False, regex=False):
        self.calls += 1
        return self.response


@pytest.mark.asyncio
async def test_run_search_persists_and_audits(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op")
    target = await inv_repo.add_target(inv.id, "jane")
    client = FakeClient(
        SearchResponse(
            balance=400,
            total=1,
            took="3ms",
            entries=[RawEntry(email="a@b.com")],
        )
    )
    svc = SearchService(SearchRepository(db_session), client, threshold=100)
    search = await svc.run_search(target.id, 'email:"a@b.com"')
    assert search.balance_after == 400
    assert client.calls == 1


@pytest.mark.asyncio
async def test_duplicate_query_uses_cache_no_spend(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op")
    target = await inv_repo.add_target(inv.id, "jane")
    client = FakeClient(SearchResponse(balance=400, total=0, entries=[]))
    svc = SearchService(SearchRepository(db_session), client, threshold=100)
    await svc.run_search(target.id, 'email:"a@b.com"')
    await svc.run_search(target.id, 'email:"a@b.com"')
    assert client.calls == 1  # second call served from cache


@pytest.mark.asyncio
async def test_credit_guard_blocks_below_threshold(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op")
    target = await inv_repo.add_target(inv.id, "jane")
    client = FakeClient(SearchResponse(balance=50, total=0, entries=[]))
    svc = SearchService(SearchRepository(db_session), client, threshold=100)
    with pytest.raises(InsufficientCreditsError):
        await svc.run_search(target.id, 'email:"a@b.com"')
