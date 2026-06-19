from typing import Any

from pydantic import BaseModel, Field, field_validator


class RawEntry(BaseModel):
    """One record as returned by DeHashed v2. Unknown fields are ignored.

    DeHashed v2 returns most per-record fields as JSON ARRAYS (e.g.
    ``"email": ["a@b.com"]``, and occasionally multiple values per field),
    while a few legacy/edge responses use bare scalars. We normalize every
    field to a single ``str | None`` so the rest of the system (scalar DB
    columns, correlation) can treat a record uniformly: a list is flattened to
    a comma-joined string, scalars are coerced to ``str``, and empty/None
    becomes ``None``.
    """

    id: str | None = None
    email: str | None = None
    username: str | None = None
    password: str | None = None
    hashed_password: str | None = None
    name: str | None = None
    ip_address: str | None = None
    phone: str | None = None
    address: str | None = None
    database_name: str | None = None

    model_config = {"extra": "allow"}

    @field_validator(
        "id",
        "email",
        "username",
        "password",
        "hashed_password",
        "name",
        "ip_address",
        "phone",
        "address",
        "database_name",
        mode="before",
    )
    @classmethod
    def _flatten_to_str(cls, value: Any) -> str | None:
        """Normalize DeHashed's list-or-scalar field shapes to ``str | None``."""
        if value is None:
            return None
        if isinstance(value, list):
            parts = [str(v) for v in value if v is not None and str(v) != ""]
            return ", ".join(parts) if parts else None
        text = str(value)
        return text if text != "" else None


class SearchResponse(BaseModel):
    balance: int = 0
    total: int = 0
    took: str | None = None
    entries: list[RawEntry] = Field(default_factory=list)
