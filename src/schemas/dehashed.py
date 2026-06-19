from pydantic import BaseModel, Field


class RawEntry(BaseModel):
    """One record as returned by DeHashed. Unknown fields ignored."""

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


class SearchResponse(BaseModel):
    balance: int = 0
    total: int = 0
    took: str | None = None
    entries: list[RawEntry] = Field(default_factory=list)
