from openforce.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "60")

    s = Settings()  # type: ignore[call-arg]
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.openai_model == "gpt-4o"
    assert s.poll_interval_seconds == 60


def test_settings_rejects_short_app_secret(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("APP_SECRET", "tooshort")

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
