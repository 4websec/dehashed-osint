from typing import Any

import structlog

REDACTED = "***REDACTED***"
_SENSITIVE_KEYS = frozenset(
    {"password", "hashed_password", "query", "email", "phone", "name", "address"}
)


def redact_sensitive(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor: redact PII/credential keys before output."""
    for key in _SENSITIVE_KEYS:
        if key in event_dict and event_dict[key] is not None:
            event_dict[key] = REDACTED
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            redact_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
