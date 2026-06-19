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


def test_build_query_escapes_double_quote():
    # A value with an embedded double-quote must be backslash-escaped in the query.
    assert build_query("email", 'a"b') == 'email:"a\\"b"'


def test_build_query_escapes_backslash_before_quote():
    # A backslash immediately before a double-quote must produce \\" not just \"
    # (the backslash itself must be escaped first, then the quote).
    result = build_query("email", 'a\\"b')
    # Input: a\"b  →  escaped: a\\\\"b  →  query: email:"a\\"b"
    assert result == 'email:"a\\\\\\"b"'


def test_build_query_escapes_lone_backslash():
    # A lone backslash in the value must be doubled to avoid escaping the closing quote.
    result = build_query("email", "a\\b")
    assert result == 'email:"a\\\\b"'
