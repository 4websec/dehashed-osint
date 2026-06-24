from pydantic import BaseModel, Field


class TargetProfile(BaseModel):
    emails: list[str] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    passwords: list[str] = Field(default_factory=list)
    ip_addresses: list[str] = Field(default_factory=list)
    reused_passwords: list[str] = Field(default_factory=list)
    reuse_counts: dict[str, int] = Field(default_factory=dict)
    breach_sources: dict[str, int] = Field(default_factory=dict)
    hash_types: dict[str, str] = Field(default_factory=dict)


class PivotSuggestion(BaseModel):
    field_type: str
    value: str
    query: str
