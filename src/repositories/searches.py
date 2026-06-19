from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AuditLog, ResultRecord, Search
from src.schemas.dehashed import RawEntry


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_cache_key(self, cache_key: str) -> Search | None:
        result = await self._session.execute(
            select(Search).where(Search.cache_key == cache_key).limit(1)
        )
        return result.scalars().first()

    async def create(
        self,
        target_id: int,
        query: str,
        params: str,
        cache_key: str,
        cost: int,
        balance_after: int,
        took: str | None,
    ) -> Search:
        search = Search(
            target_id=target_id,
            query=query,
            params=params,
            cache_key=cache_key,
            cost=cost,
            balance_after=balance_after,
            took=took,
        )
        self._session.add(search)
        await self._session.flush()
        return search

    async def add_records(
        self, search_id: int, target_id: int, entries: Sequence[RawEntry]
    ) -> list[ResultRecord]:
        records = [
            ResultRecord(
                search_id=search_id,
                target_id=target_id,
                raw_json=entry.model_dump_json(),
                email=entry.email,
                username=entry.username,
                password=entry.password,
                hashed_password=entry.hashed_password,
                name=entry.name,
                ip_address=entry.ip_address,
                phone=entry.phone,
                address=entry.address,
                database_name=entry.database_name,
            )
            for entry in entries
        ]
        self._session.add_all(records)
        await self._session.flush()
        return records

    async def records_for_target(self, target_id: int) -> list[ResultRecord]:
        result = await self._session.execute(
            select(ResultRecord).where(ResultRecord.target_id == target_id)
        )
        return list(result.scalars().all())

    async def copy_records_for_target(
        self, search_id: int, target_id: int
    ) -> None:
        """Ensure ResultRecord rows for *search_id* exist under *target_id*.

        On a cache hit the original records may belong to a different target;
        this copies them so that profile queries for *target_id* see the data.
        Rows that already exist (same search_id + target_id) are skipped to
        avoid duplicates.
        """
        existing = await self._session.execute(
            select(ResultRecord).where(
                ResultRecord.search_id == search_id,
                ResultRecord.target_id == target_id,
            )
        )
        if existing.scalars().first() is not None:
            # Records already exist for this target; nothing to do.
            return

        originals_result = await self._session.execute(
            select(ResultRecord).where(ResultRecord.search_id == search_id)
        )
        originals = list(originals_result.scalars().all())
        copies = [
            ResultRecord(
                search_id=r.search_id,
                target_id=target_id,
                raw_json=r.raw_json,
                email=r.email,
                username=r.username,
                password=r.password,
                hashed_password=r.hashed_password,
                name=r.name,
                ip_address=r.ip_address,
                phone=r.phone,
                address=r.address,
                database_name=r.database_name,
            )
            for r in originals
        ]
        if copies:
            self._session.add_all(copies)
            await self._session.flush()

    async def write_audit(self, action: str, query: str | None, cost: int) -> None:
        self._session.add(AuditLog(action=action, query=query, cost=cost))
        await self._session.flush()
