from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Investigation, Selector, Target


class InvestigationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str, notes: str | None = None) -> Investigation:
        inv = Investigation(name=name, notes=notes)
        self._session.add(inv)
        await self._session.flush()
        return inv

    async def get(self, investigation_id: int) -> Investigation | None:
        return await self._session.get(Investigation, investigation_id)

    async def list_all(self) -> list[Investigation]:
        result = await self._session.execute(
            select(Investigation).order_by(Investigation.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_target(
        self, investigation_id: int, label: str, entity_type: str = "person"
    ) -> Target:
        target = Target(
            investigation_id=investigation_id, label=label, entity_type=entity_type
        )
        self._session.add(target)
        await self._session.flush()
        return target

    async def get_target(self, target_id: int) -> Target | None:
        return await self._session.get(Target, target_id)

    async def list_targets(self, investigation_id: int) -> list[Target]:
        result = await self._session.execute(
            select(Target)
            .where(Target.investigation_id == investigation_id)
            .order_by(Target.id)
        )
        return list(result.scalars().all())

    async def add_selector(
        self, target_id: int, field_type: str, value: str
    ) -> Selector:
        selector = Selector(target_id=target_id, field_type=field_type, value=value)
        self._session.add(selector)
        await self._session.flush()
        return selector
