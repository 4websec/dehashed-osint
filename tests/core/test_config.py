from src.core.config import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("DEHASHED_API_KEY", "abc")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("ENCRYPTION_KEY", "a" * 44)
    settings = Settings()
    assert settings.dehashed_api_key.get_secret_value() == "abc"
    assert settings.credit_guard_threshold == 100  # default
    assert settings.app_host == "127.0.0.1"  # default
