import pytest

from src.core.exceptions import (
    DehashedAuthError,
    DehashedError,
    InsufficientCreditsError,
)


def test_subclasses_share_base():
    assert issubclass(DehashedAuthError, DehashedError)


def test_insufficient_credits_carries_context():
    exc = InsufficientCreditsError(balance=5, threshold=100)
    assert exc.balance == 5
    assert exc.threshold == 100
    assert "5" in str(exc) and "100" in str(exc)


def test_is_raisable():
    with pytest.raises(DehashedError):
        raise DehashedAuthError("bad key")
