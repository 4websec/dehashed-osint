import hashlib
import json

ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "email",
        "username",
        "password",
        "hashed_password",
        "name",
        "ip_address",
        "phone",
        "address",
        "domain",
        "vin",
    }
)


def build_query(field: str, value: str) -> str:
    """Build a single field:value clause. Whitelists field, quotes value."""
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Disallowed search field: {field!r}")
    escaped = value.replace('"', '\\"')
    return f'{field}:"{escaped}"'


def normalize_query(query: str) -> str:
    """Stable canonical form for cache keys (lowercase, trimmed)."""
    return query.strip().lower()


def cache_key(query: str, params: dict[str, object]) -> str:
    """Return a 64-char sha256 hex digest stable for equal inputs."""
    payload = json.dumps(
        {"q": normalize_query(query), "p": params}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()
