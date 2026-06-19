from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AuditLog, ResultRecord, Search
from src.schemas.dehashed import RawEntry

# Fields that define a record's identity for deduplication. Two rows equal on
# all of these are the same exposure (DeHashed often returns a credential under
# many breach compilations, and repeated searches re-insert overlapping rows).
_DEDUP_FIELDS = (
    "email",
    "username",
    "password",
    "hashed_password",
    "ip_address",
    "phone",
    "address",
    "name",
    "database_name",
)


def _record_key(record: ResultRecord) -> tuple[str | None, ...]:
    """Content key used to deduplicate result records (post-decryption)."""
    return tuple(getattr(record, f) for f in _DEDUP_FIELDS)


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
        """Return a target's records, deduplicated by content (order-preserving).

        Repeated/overlapping searches accumulate identical rows; dedup here so
        the ledger, exports, and correlation all see each exposure once. Done in
        Python because raw_json is non-deterministically encrypted (the stored
        ciphertext differs for identical entries, so SQL DISTINCT can't be used).
        """
        result = await self._session.execute(
            select(ResultRecord)
            .where(ResultRecord.target_id == target_id)
            .order_by(ResultRecord.id)
        )
        seen: set[tuple[str | None, ...]] = set()
        unique: list[ResultRecord] = []
        for record in result.scalars().all():
            key = _record_key(record)
            if key not in seen:
                seen.add(key)
                unique.append(record)
        return unique

    async def copy_records_for_target(self, search_id: int, target_id: int) -> None:
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

    async def list_audit(self, limit: int = 200) -> list[AuditLog]:
        """Return the most recent audit-log entries, newest first."""
        result = await self._session.execute(
            select(AuditLog)
            .order_by(AuditLog.ts.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
