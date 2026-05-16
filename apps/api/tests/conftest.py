"""Test configuration: load env vars so config.Settings() works under pytest."""
import os

# Defaults sufficient for unit + integration tests if not provided by the env / shell.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://openforce:openforce_dev@localhost:5433/openforce",
)
os.environ.setdefault(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://openforce:openforce_dev@localhost:5433/openforce",
)
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("APP_SECRET", "test-app-secret-32-bytes-xxxxxxxx")
