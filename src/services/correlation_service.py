import re
from collections import Counter

from src.repositories.searches import SearchRepository
from src.schemas.domain import TargetProfile

_MD5 = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
_SHA1 = re.compile(r"^[a-f0-9]{40}$", re.IGNORECASE)
_SHA256 = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)
_BCRYPT = re.compile(r"^\$2[aby]\$\d{2}\$.{53}$")


def identify_hash_type(value: str) -> str:
    """Return the hash algorithm name for *value*, or 'unknown'.

    bcrypt is checked first because its prefix is unambiguous; the hex-length
    checks below would otherwise mis-classify a bcrypt string that happens to
    be 32/40/64 chars long in edge cases.
    """
    if _BCRYPT.match(value):
        return "bcrypt"
    if _MD5.match(value):
        return "MD5"
    if _SHA1.match(value):
        return "SHA-1"
    if _SHA256.match(value):
        return "SHA-256"
    return "unknown"


def _dedup_preserve(values: list[str | None]) -> list[str]:
    """Return deduplicated list preserving first-seen order; drops None/empty."""
    seen: dict[str, None] = {}
    for v in values:
        if v:
            seen.setdefault(v, None)
    return list(seen)


class CorrelationService:
    """Merges result records for a target into a deduplicated TargetProfile."""

    def __init__(self, repo: SearchRepository) -> None:
        self._repo = repo

    async def build_profile(self, target_id: int) -> TargetProfile:
        """Build a TargetProfile by aggregating all ResultRecords for *target_id*."""
        records = await self._repo.records_for_target(target_id)

        emails = _dedup_preserve([r.email for r in records])
        usernames = _dedup_preserve([r.username for r in records])
        passwords = _dedup_preserve([r.password for r in records])
        ips = _dedup_preserve([r.ip_address for r in records])

        # Reuse = same plaintext password appearing under >1 distinct breach source.
        pw_breaches: dict[str, set[str]] = {}
        for r in records:
            if r.password and r.database_name:
                pw_breaches.setdefault(r.password, set()).add(r.database_name)
        reused = [pw for pw, srcs in pw_breaches.items() if len(srcs) > 1]

        breach_sources = dict(
            Counter(r.database_name for r in records if r.database_name)
        )

        hash_types = {
            r.hashed_password: identify_hash_type(r.hashed_password)
            for r in records
            if r.hashed_password
        }

        return TargetProfile(
            emails=emails,
            usernames=usernames,
            passwords=passwords,
            ip_addresses=ips,
            reused_passwords=reused,
            breach_sources=breach_sources,
            hash_types=hash_types,
        )
