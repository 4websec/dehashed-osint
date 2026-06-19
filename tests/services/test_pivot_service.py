import pytest

from src.services.pivot_service import suggest_pivot


def test_pivot_on_email_builds_query():
    s = suggest_pivot("email", "a@b.com")
    assert s.field_type == "email"
    assert s.query == 'email:"a@b.com"'


def test_pivot_on_unknown_field_raises():
    with pytest.raises(ValueError):
        suggest_pivot("ssn", "123")
