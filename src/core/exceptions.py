class DehashedError(Exception):
    """Base class for all DeHashed integration errors."""


class DehashedAuthError(DehashedError):
    """Authentication with the DeHashed API failed (401/403)."""


class DehashedRateLimitError(DehashedError):
    """DeHashed API returned 429 after retries."""


class DehashedAPIError(DehashedError):
    """Unexpected/non-2xx response from the DeHashed API."""


class InsufficientCreditsError(DehashedError):
    """Remaining balance is at or below the configured credit-guard threshold."""

    def __init__(self, balance: int, threshold: int) -> None:
        self.balance = balance
        self.threshold = threshold
        super().__init__(
            f"DeHashed balance {balance} at/below guard threshold {threshold}; "
            "refusing to spend credits."
        )
