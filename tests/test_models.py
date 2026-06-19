"""Model persistence tests: encrypted round-trip and basic FK relationships."""

import pytest

from src.models import Investigation, ResultRecord, Search, Target


@pytest.mark.asyncio
async def test_encrypted_password_round_trips(db_session):
    inv = Investigation(name="Op Test")
    db_session.add(inv)
    await db_session.flush()
    target = Target(investigation_id=inv.id, label="jane")
    db_session.add(target)
    await db_session.flush()
    search = Search(target_id=target.id, query="email:a@b.com", cache_key="k1")
    db_session.add(search)
    await db_session.flush()
    rec = ResultRecord(
        search_id=search.id, target_id=target.id, raw_json="{}", password="hunter2"
    )
    db_session.add(rec)
    await db_session.flush()
    # Capture PK before expire: accessing rec.id after expire() would trigger a
    # synchronous lazy-load in Python argument-evaluation position, which raises
    # MissingGreenlet in an async session.  Saving the PK first preserves the
    # test's intent (force a DB round-trip via expire → get) without the bug.
    rec_id = rec.id
    db_session.expire(rec)
    loaded = await db_session.get(ResultRecord, rec_id)
    assert loaded is not None
    assert loaded.password == "hunter2"  # decrypted transparently
