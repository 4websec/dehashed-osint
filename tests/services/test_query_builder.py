import pytest

from src.services.query_builder import (
    ALLOWED_FIELDS,
    build_query,
    cache_key,
    normalize_query,
)


def test_build_query_known_field():
    assert build_query("email", "a@b.com") == 'email:"a@b.com"'


def test_build_query_rejects_unknown_field():
    with pytest.raises(ValueError):
        build_query("ssn", "123")


def test_email_is_allowed():
    assert "email" in ALLOWED_FIELDS


def test_normalize_is_case_and_space_stable():
    assert normalize_query("  Email:A@B.com ") == normalize_query("email:a@b.com")


def test_cache_key_stable_and_param_sensitive():
    k1 = cache_key("email:a@b.com", {"page": 1})
    k2 = cache_key("email:a@b.com", {"page": 1})
    k3 = cache_key("email:a@b.com", {"page": 2})
    assert k1 == k2 and k1 != k3
    assert len(k1) == 64
