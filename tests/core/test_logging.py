from src.core.logging import redact_sensitive

REDACTED = "***REDACTED***"


def test_redacts_sensitive_keys():
    event = {
        "event": "search",
        "password": "hunter2",
        "hashed_password": "deadbeef",
        "query": "email:a@b.com",
        "email": "a@b.com",
        "phone": "555",
        "name": "Jane",
        "address": "1 St",
        "status": "ok",
    }
    out = redact_sensitive(None, "info", dict(event))
    for key in (
        "password",
        "hashed_password",
        "query",
        "email",
        "phone",
        "name",
        "address",
    ):
        assert out[key] == REDACTED
    assert out["status"] == "ok"  # non-sensitive untouched
