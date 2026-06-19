import json

import pytest
from sqlalchemy import text

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


@pytest.mark.asyncio
async def test_records_for_target_deduplicates(db_session):
    """Identical exposures from repeated searches collapse to one row."""
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Dedup Op")
    target = await inv_repo.add_target(inv.id, "jane")
    s_repo = SearchRepository(db_session)
    s1 = await s_repo.create(target.id, "email:x", "{}", "ckA", 1, 99, "1ms")
    s2 = await s_repo.create(target.id, "email:x", "{}", "ckB", 1, 98, "1ms")
    dup = RawEntry(email="a@b.com", username="jane", database_name="Canva")
    other = RawEntry(email="a@b.com", username="jane2", database_name="Canva")
    # Same exposure inserted under two searches + a distinct one.
    await s_repo.add_records(s1.id, target.id, [dup])
    await s_repo.add_records(s2.id, target.id, [dup, other])
    records = await s_repo.records_for_target(target.id)
    assert len(records) == 2  # dup collapsed, other kept
    usernames = {r.username for r in records}
    assert usernames == {"jane", "jane2"}


@pytest.mark.asyncio
async def test_list_audit_returns_newest_first(db_session):
    s_repo = SearchRepository(db_session)
    await s_repo.write_audit("search", "email:a", 1)
    await s_repo.write_audit("search", "email:b", 2)
    entries = await s_repo.list_audit()
    assert len(entries) == 2
    # Newest first (tie broken by id desc).
    assert entries[0].query == "email:b"
    assert entries[0].cost == 2


@pytest.mark.asyncio
async def test_raw_json_is_encrypted_at_rest(db_session):
    """raw_json must be stored encrypted; ORM must decrypt on read.

    Verifies that the EncryptedString column type on ResultRecord.raw_json
    prevents plaintext credentials from appearing in the DB storage layer
    while still allowing the ORM to transparently decrypt them.
    """
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Enc Test")
    target = await inv_repo.add_target(inv.id, "victim")
    s_repo = SearchRepository(db_session)
    search = await s_repo.create(
        target.id,
        "email:victim@test.com",
        "{}",
        "ck_enc",
        cost=1,
        balance_after=0,
        took="1ms",
    )
    plaintext_password = "super_secret_pw_1234"
    entry = RawEntry(
        email="victim@test.com",
        password=plaintext_password,
        database_name="TestBreach",
    )
    recs = await s_repo.add_records(search.id, target.id, [entry])
    record_id = recs[0].id

    # Query the raw stored bytes directly — bypassing the ORM type decorator.
    raw_result = await db_session.execute(
        text("SELECT raw_json FROM result_records WHERE id = :id"),
        {"id": record_id},
    )
    raw_value: str = raw_result.scalar_one()

    # The plaintext password must NOT appear in the encrypted storage value.
    assert (
        plaintext_password not in raw_value
    ), "raw_json stored plaintext password — encryption not applied!"
    # The raw value should not be valid JSON (it's a base64-encoded ciphertext).
    try:
        json.loads(raw_value)
        is_json = True
    except (json.JSONDecodeError, ValueError):
        is_json = False
    assert (
        not is_json
    ), "raw_json stored as plaintext JSON — expected encrypted ciphertext"

    # ORM read must still decrypt and return parseable JSON containing the password.
    orm_record = (await s_repo.records_for_target(target.id))[0]
    decrypted_data = json.loads(orm_record.raw_json)
    assert decrypted_data.get("password") == plaintext_password
