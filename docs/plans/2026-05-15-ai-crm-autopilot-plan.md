# AI CRM Autopilot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an end-to-end agentic pipeline that ingests a user's Gmail, reasons about CRM-relevant signals using OpenAI function-calling, proposes Salesforce updates that a human approves with one click, and writes them via the Salesforce REST API.

**Architecture:** A FastAPI backend polls Gmail every 5 minutes, runs each new email through a GPT-4o agent with 4 SF-grounded function-calling tools, and stores resulting proposals in Postgres. A Next.js dashboard reads pending proposals, displays diff + reasoning + confidence, and on approve invokes a writer that revalidates and writes to Salesforce — recording every write in an audit log.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · Postgres 16 · APScheduler · OpenAI Python SDK (GPT-4o function calling) · `simple-salesforce` · `google-api-python-client` · Next.js 14 · Tailwind · pytest · Docker Compose · Railway (API) + Vercel (web).

**Source of truth for design:** `docs/plans/2026-05-15-ai-crm-autopilot-design.md`. Read it before starting.

---

## Repo layout (will exist after Phase 0)

```
Openforce/
├── apps/
│   ├── api/                          # FastAPI backend (Python)
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   ├── src/openforce/
│   │   │   ├── main.py               # FastAPI app
│   │   │   ├── config.py             # Pydantic settings
│   │   │   ├── db/{session,models}.py
│   │   │   ├── salesforce/{oauth,client,writer}.py
│   │   │   ├── gmail/{oauth,client,ingest}.py
│   │   │   ├── agent/{prompts,schemas,tools,runner}.py
│   │   │   ├── proposals/service.py
│   │   │   ├── workers/scheduler.py
│   │   │   └── api/{health,proposals,integrations}.py
│   │   ├── tests/{unit,fixtures,e2e}/
│   │   └── scripts/seed_sf.py
│   └── web/                          # Next.js 14 dashboard
│       ├── package.json
│       ├── src/app/                  # App Router
│       ├── src/components/
│       └── src/lib/api.ts
├── docker-compose.yml                # Postgres locally
├── .env.example
├── .github/workflows/ci.yml
└── README.md
```

## Conventions

- **TDD always:** failing test → minimal code → green → commit.
- **Commit per task:** every task ends with a commit. Use Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`, `refactor:`).
- **Never `git push` directly.** Use `/gitpush` (HARD RULE in CLAUDE.md).
- **Env vars only, no hardcoded secrets.** All keys come from `.env` (gitignored). `.env.example` is the canonical template.
- **Type hints required** on all Python functions touched by this plan.
- **Async where the framework supports it** (FastAPI handlers, SQLAlchemy 2 async). Sync is fine for one-off scripts.
- **Single source of structured output schema** lives in `agent/schemas.py` and is reused for OpenAI tool definitions, DB validation, and API serializers.

---

# Phase 0 — Repo scaffolding

## Task 1: Initialize monorepo layout + Python project scaffolding

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/openforce/__init__.py`
- Create: `apps/api/tests/__init__.py`
- Create: `apps/api/.python-version`
- Create: `.gitignore`
- Create: `apps/api/README.md` (1-paragraph)

**Step 1: Add `.gitignore`**

```
# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.egg-info/

# Node
node_modules/
.next/
out/
.turbo/

# Env / secrets
.env
.env.local
.env.*.local
*.pem
*.key

# OS / editors
.DS_Store
.idea/
.vscode/
```

**Step 2: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "openforce-api"
version = "0.1.0"
description = "AI CRM Autopilot - backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi[standard]>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0.36",
    "alembic>=1.14",
    "asyncpg>=0.30",
    "psycopg2-binary>=2.9",        # alembic
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "python-dotenv>=1.0",
    "httpx>=0.27",
    "openai>=1.55",
    "simple-salesforce>=1.12",
    "google-api-python-client>=2.149",
    "google-auth-oauthlib>=1.2",
    "apscheduler>=3.10",
    "structlog>=24.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
    "respx>=0.21",
    "ruff>=0.7",
    "mypy>=1.13",
    "freezegun>=1.5",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "TCH"]
```

**Step 3: Create `apps/api/.python-version`**

```
3.12
```

**Step 4: Create empty `__init__.py` files and 1-paragraph README**

`apps/api/README.md`:
```markdown
# Openforce API

FastAPI backend for AI CRM Autopilot. See repo-root `docs/plans/2026-05-15-ai-crm-autopilot-design.md` for design.

Run: `uv sync && uv run uvicorn openforce.main:app --reload`.
```

**Step 5: Verify install works**

Run:
```bash
cd apps/api && uv sync
```
Expected: a `.venv/` directory is created and dependencies resolve without error.

**Step 6: Commit**

```bash
git add .gitignore apps/api/
git commit -m "chore: scaffold apps/api Python project"
```

---

## Task 2: Next.js dashboard scaffolding

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/next.config.mjs`
- Create: `apps/web/tailwind.config.ts`
- Create: `apps/web/postcss.config.mjs`
- Create: `apps/web/src/app/layout.tsx`
- Create: `apps/web/src/app/page.tsx`
- Create: `apps/web/src/app/globals.css`
- Create: `apps/web/README.md`

**Step 1: `apps/web/package.json`**

```json
{
  "name": "openforce-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "14.2.18",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "swr": "2.2.5"
  },
  "devDependencies": {
    "@types/node": "22.9.0",
    "@types/react": "18.3.12",
    "@types/react-dom": "18.3.1",
    "autoprefixer": "10.4.20",
    "eslint": "9.15.0",
    "eslint-config-next": "14.2.18",
    "postcss": "8.4.49",
    "tailwindcss": "3.4.14",
    "typescript": "5.6.3"
  }
}
```

**Step 2: Add `next.config.mjs`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.mjs`** (standard Next 14 + App Router setup — copy the defaults `create-next-app` would emit; verify Tailwind `content` includes `./src/**/*.{ts,tsx}`).

**Step 3: Add `src/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Openforce — AI CRM Autopilot",
  description: "AI-proposed Salesforce updates from your inbox.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900">{children}</body>
    </html>
  );
}
```

**Step 4: Add `src/app/page.tsx` placeholder**

```tsx
export default function Home() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-3xl font-semibold">Openforce</h1>
      <p className="mt-2 text-slate-600">Dashboard placeholder — proposals will appear here.</p>
    </main>
  );
}
```

**Step 5: Verify it boots**

```bash
cd apps/web && npm install && npm run build
```
Expected: build completes; no TS errors.

**Step 6: Commit**

```bash
git add apps/web/
git commit -m "chore: scaffold apps/web Next.js dashboard"
```

---

## Task 3: Local Postgres via docker-compose + `.env.example`

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

**Step 1: `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: openforce
      POSTGRES_USER: openforce
      POSTGRES_PASSWORD: openforce_dev
    ports:
      - "5433:5432"
    volumes:
      - openforce_pg:/var/lib/postgresql/data

volumes:
  openforce_pg:
```

**Step 2: `.env.example` (canonical key list)**

```
# Database
DATABASE_URL=postgresql+asyncpg://openforce:openforce_dev@localhost:5433/openforce
DATABASE_URL_SYNC=postgresql+psycopg2://openforce:openforce_dev@localhost:5433/openforce

# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

# Salesforce (Connected App)
SF_CLIENT_ID=
SF_CLIENT_SECRET=
SF_REDIRECT_URI=http://localhost:8000/auth/salesforce/callback
SF_LOGIN_URL=https://login.salesforce.com    # use https://test.salesforce.com for sandboxes

# Gmail (OAuth)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/gmail/callback

# App
APP_SECRET=change-me-32-bytes-base64
LOG_LEVEL=INFO
POLL_INTERVAL_SECONDS=300
```

**Step 3: Boot Postgres + verify**

Run:
```bash
docker compose up -d db
docker compose exec db pg_isready -U openforce -d openforce
```
Expected: `localhost:5433 - accepting connections`.

**Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore: add docker-compose Postgres and env template"
```

---

## Task 4: Pydantic settings module

**Files:**
- Create: `apps/api/src/openforce/config.py`
- Test: `apps/api/tests/unit/test_config.py`

**Step 1: Write failing test**

```python
# tests/unit/test_config.py
import os
from openforce.config import Settings

def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "60")

    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.openai_model == "gpt-4o"
    assert s.poll_interval_seconds == 60
```

Run: `pytest tests/unit/test_config.py -v` → FAIL (no module).

**Step 2: Implement `config.py`**

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    database_url_sync: str = ""
    openai_api_key: str
    openai_model: str = "gpt-4o"

    sf_client_id: str = ""
    sf_client_secret: str = ""
    sf_redirect_uri: str = "http://localhost:8000/auth/salesforce/callback"
    sf_login_url: str = "https://login.salesforce.com"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"

    app_secret: str = Field(min_length=16)
    log_level: str = "INFO"
    poll_interval_seconds: int = 300


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

**Step 3: Run test** → PASS.

**Step 4: Commit**

```bash
git add apps/api/src/openforce/config.py apps/api/tests/unit/test_config.py
git commit -m "feat(config): pydantic settings module backed by env"
```

---

## Task 5: GitHub Actions CI skeleton

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: CI workflow**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  api:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: openforce
          POSTGRES_USER: openforce
          POSTGRES_PASSWORD: openforce_dev
        ports: ["5433:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 5s
          --health-timeout 5s --health-retries 10

    env:
      DATABASE_URL: postgresql+asyncpg://openforce:openforce_dev@localhost:5433/openforce
      DATABASE_URL_SYNC: postgresql+psycopg2://openforce:openforce_dev@localhost:5433/openforce
      OPENAI_API_KEY: sk-ci-fake
      APP_SECRET: ci-secret-min-16-chars-xxxxxxx

    defaults:
      run:
        working-directory: apps/api

    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          python-version: "3.12"
      - run: uv sync --frozen --extra dev
      - run: uv run ruff check .
      - run: uv run pytest -v

  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm run typecheck
      - run: npm run build
```

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions for api + web"
```

---

# Phase 1 — Database & FastAPI skeleton

## Task 6: Alembic init + database session

**Files:**
- Create: `apps/api/alembic.ini`
- Create: `apps/api/alembic/env.py`
- Create: `apps/api/alembic/script.py.mako` (standard alembic template)
- Create: `apps/api/src/openforce/db/__init__.py`
- Create: `apps/api/src/openforce/db/session.py`
- Test: `apps/api/tests/unit/test_db_session.py`

**Step 1: `alembic init` style files** — run `uv run alembic init alembic` inside `apps/api/`, then edit `alembic.ini`:
- set `sqlalchemy.url = ` (empty — overridden in env.py)

Edit `alembic/env.py` (the relevant section):

```python
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from openforce.db.session import Base
import openforce.db.models  # noqa: F401  ensure models are imported

config = context.config
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL_SYNC"])

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Step 2: `db/session.py`**

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from openforce.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(_settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

**Step 3: Failing test**

```python
# tests/unit/test_db_session.py
import pytest
from sqlalchemy import text
from openforce.db.session import SessionLocal


@pytest.mark.asyncio
async def test_can_connect_and_select_one():
    async with SessionLocal() as s:
        result = await s.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
```

Run with Postgres up: `pytest tests/unit/test_db_session.py -v` → should pass once DB is up.

**Step 4: Commit**

```bash
git add apps/api/alembic* apps/api/src/openforce/db apps/api/tests/unit/test_db_session.py
git commit -m "feat(db): alembic setup and async session factory"
```

---

## Task 7: Core SQLAlchemy models

**Files:**
- Create: `apps/api/src/openforce/db/models.py`
- Test: `apps/api/tests/unit/test_models.py`
- Migration: `apps/api/alembic/versions/0001_init.py` (autogenerated)

**Step 1: Define models**

```python
# db/models.py
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openforce.db.session import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class EmailStatus(str, enum.Enum):
    unprocessed = "unprocessed"
    proposed = "proposed"
    irrelevant = "irrelevant"
    extraction_failed = "extraction_failed"


class ProposalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"
    failed_validation = "failed_validation"


class IntegrationProvider(str, enum.Enum):
    gmail = "gmail"
    salesforce = "salesforce"


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[IntegrationProvider] = mapped_column(Enum(IntegrationProvider), unique=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    instance_url: Mapped[str | None] = mapped_column(String(512), nullable=True)  # SF
    history_id: Mapped[str | None] = mapped_column(String(128), nullable=True)    # gmail
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    needs_reauth: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (UniqueConstraint("gmail_msg_id", name="uq_emails_gmail_msg_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    gmail_msg_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    sender: Mapped[str] = mapped_column(String(256))
    subject: Mapped[str] = mapped_column(String(512))
    body_text: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[EmailStatus] = mapped_column(Enum(EmailStatus), default=EmailStatus.unprocessed, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    proposals: Mapped[list[Proposal]] = relationship(back_populates="email")


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"), index=True)
    sf_object_type: Mapped[str] = mapped_column(String(64))             # Account|Contact|Opportunity|Task
    sf_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # null = create new
    diff_payload: Mapped[dict[str, Any]] = mapped_column(JSON)          # {before, after}
    reasoning: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column()                         # 0..1
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus), default=ProposalStatus.pending, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    email: Mapped[Email] = relationship(back_populates="proposals")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id"), index=True)
    sf_record_id: Mapped[str] = mapped_column(String(64))
    before_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    after_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

**Step 2: Autogenerate migration**

```bash
cd apps/api
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head
```
Expected: migration file in `alembic/versions/*_init.py`; tables created in DB.

**Step 3: Test model round-trip**

```python
# tests/unit/test_models.py
import uuid
import pytest
from datetime import datetime, timezone
from openforce.db.models import Email, EmailStatus
from openforce.db.session import SessionLocal


@pytest.mark.asyncio
async def test_email_insert_and_select():
    async with SessionLocal() as s:
        e = Email(
            gmail_msg_id=f"msg-{uuid.uuid4()}",
            thread_id="t-1",
            sender="sam@acme.test",
            subject="Re: contract",
            body_text="ping",
            received_at=datetime.now(timezone.utc),
        )
        s.add(e)
        await s.commit()
        await s.refresh(e)
        assert e.status == EmailStatus.unprocessed
        assert e.id is not None
```

Run: `pytest tests/unit/test_models.py -v` → PASS.

**Step 4: Commit**

```bash
git add apps/api/alembic/versions apps/api/src/openforce/db/models.py apps/api/tests/unit/test_models.py
git commit -m "feat(db): core models for emails, proposals, audit_log, integrations"
```

---

## Task 8: FastAPI app + health endpoint

**Files:**
- Create: `apps/api/src/openforce/main.py`
- Create: `apps/api/src/openforce/api/__init__.py`
- Create: `apps/api/src/openforce/api/health.py`
- Test: `apps/api/tests/unit/test_health.py`

**Step 1: Failing test**

```python
# tests/unit/test_health.py
from fastapi.testclient import TestClient
from openforce.main import app


def test_health_ok():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
```

**Step 2: Implement**

```python
# api/health.py
from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

```python
# main.py
from fastapi import FastAPI
from openforce.api.health import router as health_router

app = FastAPI(title="Openforce", version="0.1.0")
app.include_router(health_router)
```

**Step 3: Run test** → PASS.

**Step 4: Commit**

```bash
git add apps/api/src/openforce/main.py apps/api/src/openforce/api
git commit -m "feat(api): FastAPI skeleton with health check"
```

---

# Phase 2 — Salesforce integration

## Task 9: Salesforce OAuth flow

**Files:**
- Create: `apps/api/src/openforce/salesforce/__init__.py`
- Create: `apps/api/src/openforce/salesforce/oauth.py`
- Create: `apps/api/src/openforce/api/integrations.py`
- Test: `apps/api/tests/unit/test_sf_oauth.py`

**Pre-requisite (manual, document in README):**
1. In SF Developer Org → Setup → App Manager → New Connected App
2. Enable OAuth, set callback to `http://localhost:8000/auth/salesforce/callback`
3. Scopes: `api`, `refresh_token`, `offline_access`
4. Copy consumer key/secret → `.env` as `SF_CLIENT_ID`, `SF_CLIENT_SECRET`

**Step 1: Failing test (mock the token exchange)**

```python
# tests/unit/test_sf_oauth.py
from fastapi.testclient import TestClient
import respx, httpx
from openforce.main import app


def test_sf_oauth_callback_persists_tokens(monkeypatch, db_session_setup):
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post("https://login.salesforce.com/services/oauth2/token").mock(
            return_value=httpx.Response(200, json={
                "access_token": "a-token",
                "refresh_token": "r-token",
                "instance_url": "https://example.my.salesforce.com",
                "id": "...",
                "token_type": "Bearer",
                "issued_at": "1700000000000",
                "signature": "x",
            })
        )
        with TestClient(app) as client:
            r = client.get("/auth/salesforce/callback?code=abc&state=ok")
            assert r.status_code == 200
            assert r.json()["status"] == "connected"
```

**Step 2: Implement OAuth**

```python
# salesforce/oauth.py
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from openforce.config import get_settings
from openforce.db.models import Integration, IntegrationProvider


def authorize_url() -> str:
    s = get_settings()
    return (
        f"{s.sf_login_url}/services/oauth2/authorize"
        f"?response_type=code&client_id={s.sf_client_id}"
        f"&redirect_uri={s.sf_redirect_uri}&scope=api%20refresh_token%20offline_access"
    )


async def exchange_code(code: str) -> dict:
    s = get_settings()
    async with httpx.AsyncClient() as http:
        r = await http.post(
            f"{s.sf_login_url}/services/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": s.sf_client_id,
                "client_secret": s.sf_client_secret,
                "redirect_uri": s.sf_redirect_uri,
            },
        )
        r.raise_for_status()
        return r.json()


async def save_sf_integration(session: AsyncSession, payload: dict) -> Integration:
    existing = (await session.execute(
        select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
    )).scalar_one_or_none()
    if existing is None:
        existing = Integration(provider=IntegrationProvider.salesforce)
        session.add(existing)
    existing.access_token = payload["access_token"]
    existing.refresh_token = payload.get("refresh_token")
    existing.instance_url = payload.get("instance_url")
    existing.needs_reauth = False
    await session.commit()
    await session.refresh(existing)
    return existing
```

```python
# api/integrations.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from openforce.db.session import get_session
from openforce.salesforce.oauth import authorize_url, exchange_code, save_sf_integration

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/salesforce/start")
async def sf_start() -> dict:
    return {"url": authorize_url()}

@router.get("/salesforce/callback")
async def sf_callback(code: str, session: AsyncSession = Depends(get_session)) -> dict:
    payload = await exchange_code(code)
    await save_sf_integration(session, payload)
    return {"status": "connected"}
```

Register router in `main.py`.

**Step 3: Add token-refresh helper** (used by writer and tools):

```python
# salesforce/oauth.py (append)
async def refresh_sf_tokens(session: AsyncSession, integration: Integration) -> Integration:
    s = get_settings()
    async with httpx.AsyncClient() as http:
        r = await http.post(
            f"{s.sf_login_url}/services/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": integration.refresh_token,
                "client_id": s.sf_client_id,
                "client_secret": s.sf_client_secret,
            },
        )
    if r.status_code != 200:
        integration.needs_reauth = True
        await session.commit()
        raise RuntimeError("SF refresh failed; needs_reauth set")
    payload = r.json()
    integration.access_token = payload["access_token"]
    await session.commit()
    return integration
```

**Step 4: Commit**

```bash
git add apps/api/src/openforce/salesforce apps/api/src/openforce/api/integrations.py apps/api/tests/unit/test_sf_oauth.py apps/api/src/openforce/main.py
git commit -m "feat(salesforce): OAuth Connected App callback + refresh"
```

---

## Task 10: Salesforce read client (used by agent tools)

**Files:**
- Create: `apps/api/src/openforce/salesforce/client.py`
- Test: `apps/api/tests/unit/test_sf_client.py`

**Step 1: Failing test (mock simple_salesforce)**

```python
# tests/unit/test_sf_client.py
import pytest
from unittest.mock import MagicMock, patch
from openforce.salesforce.client import SalesforceClient


@patch("openforce.salesforce.client.Salesforce")
def test_search_contacts_by_email(SfMock):
    instance = SfMock.return_value
    instance.query.return_value = {"records": [
        {"Id": "003xx", "FirstName": "Sam", "LastName": "Patel", "Email": "sam@acme.test", "AccountId": "001xx"}
    ]}
    c = SalesforceClient(access_token="t", instance_url="https://x.my.salesforce.com")
    results = c.search_contacts("sam@acme.test")
    assert len(results) == 1
    assert results[0]["Id"] == "003xx"
    instance.query.assert_called_once()
```

**Step 2: Implement**

```python
# salesforce/client.py
from simple_salesforce import Salesforce


class SalesforceClient:
    def __init__(self, access_token: str, instance_url: str) -> None:
        self._sf = Salesforce(instance_url=instance_url, session_id=access_token)

    def search_contacts(self, query: str) -> list[dict]:
        # SOSL would be ideal; SOQL LIKE is simpler and demo-sufficient
        q = query.replace("'", "\\'")
        soql = (
            "SELECT Id, FirstName, LastName, Email, AccountId "
            f"FROM Contact WHERE Email LIKE '%{q}%' OR Name LIKE '%{q}%' LIMIT 10"
        )
        res = self._sf.query(soql)
        return res["records"]

    def search_open_opportunities(self, account_id: str) -> list[dict]:
        soql = (
            "SELECT Id, Name, StageName, Amount, CloseDate "
            f"FROM Opportunity WHERE AccountId='{account_id}' AND IsClosed=false LIMIT 25"
        )
        return self._sf.query(soql)["records"]

    def get_record(self, object_type: str, record_id: str) -> dict:
        return getattr(self._sf, object_type).get(record_id)

    def update_record(self, object_type: str, record_id: str, fields: dict) -> None:
        getattr(self._sf, object_type).update(record_id, fields)

    def create_record(self, object_type: str, fields: dict) -> str:
        res = getattr(self._sf, object_type).create(fields)
        return res["id"]
```

**Step 3: Test passes**, then commit.

```bash
git add apps/api/src/openforce/salesforce/client.py apps/api/tests/unit/test_sf_client.py
git commit -m "feat(salesforce): read/write client wrapping simple-salesforce"
```

---

## Task 11: SF seed script (demo data)

**Files:**
- Create: `apps/api/scripts/seed_sf.py`

Creates 1 Account ("Acme Corp"), 2 Contacts ("Sam Patel", "Jordan Lee"), 1 open Opportunity ("Acme — Q3 Renewal", Stage: Discovery, $30000). Used by E2E test and demo.

```python
# scripts/seed_sf.py
"""One-shot seed for SF Developer Org. Idempotent by name."""
import asyncio, os
from sqlalchemy import select
from openforce.db.session import SessionLocal
from openforce.db.models import Integration, IntegrationProvider
from openforce.salesforce.client import SalesforceClient


async def main() -> None:
    async with SessionLocal() as s:
        integration = (await s.execute(
            select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
        )).scalar_one()
    c = SalesforceClient(integration.access_token, integration.instance_url)

    accounts = c._sf.query("SELECT Id FROM Account WHERE Name='Acme Corp'")["records"]
    if accounts:
        account_id = accounts[0]["Id"]
    else:
        account_id = c.create_record("Account", {"Name": "Acme Corp", "Industry": "Technology"})

    for first, last, email in [("Sam", "Patel", "sam@acme.test"), ("Jordan", "Lee", "jordan@acme.test")]:
        existing = c._sf.query(f"SELECT Id FROM Contact WHERE Email='{email}'")["records"]
        if not existing:
            c.create_record("Contact", {"FirstName": first, "LastName": last, "Email": email, "AccountId": account_id})

    opp_q = c._sf.query("SELECT Id FROM Opportunity WHERE Name='Acme - Q3 Renewal'")["records"]
    if not opp_q:
        c.create_record("Opportunity", {
            "Name": "Acme - Q3 Renewal",
            "AccountId": account_id,
            "StageName": "Discovery",
            "Amount": 30000,
            "CloseDate": "2026-09-30",
        })
    print("seed complete")


if __name__ == "__main__":
    asyncio.run(main())
```

Commit:
```bash
git add apps/api/scripts/seed_sf.py
git commit -m "chore: SF seed script with Acme Corp demo data"
```

---

# Phase 3 — Gmail integration & ingest

## Task 12: Gmail OAuth + token storage

**Files:**
- Create: `apps/api/src/openforce/gmail/__init__.py`
- Create: `apps/api/src/openforce/gmail/oauth.py`
- Add: routes in `api/integrations.py`
- Test: `apps/api/tests/unit/test_gmail_oauth.py`

**Pre-requisite (document in README):**
1. Google Cloud Console → enable Gmail API
2. OAuth consent screen → External, scope `https://www.googleapis.com/auth/gmail.readonly`
3. Create OAuth client → web → redirect `http://localhost:8000/auth/gmail/callback`
4. Put client_id/secret in `.env`

**Step 1: Failing test (mock httpx token exchange)** — same pattern as SF OAuth test.

**Step 2: Implement** with `google-auth-oauthlib.Flow` or hand-rolled httpx like SF. Persist tokens to `integrations` table with `provider=gmail`. Add `/auth/gmail/start` and `/auth/gmail/callback` endpoints mirroring SF.

**Step 3: Commit**

```bash
git add apps/api/src/openforce/gmail apps/api/tests/unit/test_gmail_oauth.py
git commit -m "feat(gmail): OAuth flow + token storage"
```

---

## Task 13: Gmail read client

**Files:**
- Create: `apps/api/src/openforce/gmail/client.py`
- Test: `apps/api/tests/unit/test_gmail_client.py`

**Step 1: Failing test** (mock `googleapiclient.discovery.build` and the chain `.users().history().list().execute()` + `.users().messages().get().execute()`).

**Step 2: Implement**

```python
# gmail/client.py
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


@dataclass
class GmailMessage:
    msg_id: str
    thread_id: str
    sender: str
    subject: str
    body_text: str
    received_at: datetime


class GmailClient:
    def __init__(self, access_token: str, refresh_token: str | None) -> None:
        creds = Credentials(token=access_token, refresh_token=refresh_token)
        self._svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def list_history_since(self, history_id: str) -> tuple[list[str], str]:
        """Return (new_msg_ids, latest_history_id)."""
        resp = self._svc.users().history().list(
            userId="me", startHistoryId=history_id, historyTypes=["messageAdded"]
        ).execute()
        msg_ids: list[str] = []
        for h in resp.get("history", []):
            for m in h.get("messagesAdded", []):
                msg_ids.append(m["message"]["id"])
        return msg_ids, resp.get("historyId", history_id)

    def initial_history_id(self) -> str:
        profile = self._svc.users().getProfile(userId="me").execute()
        return profile["historyId"]

    def get_message(self, msg_id: str) -> GmailMessage:
        m = self._svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in m["payload"]["headers"]}
        sender = headers.get("from", "")
        subject = headers.get("subject", "")
        date_hdr = headers.get("date")
        received_at = parsedate_to_datetime(date_hdr) if date_hdr else datetime.now(timezone.utc)
        body = _extract_text(m["payload"])
        return GmailMessage(
            msg_id=m["id"],
            thread_id=m["threadId"],
            sender=sender,
            subject=subject,
            body_text=body,
            received_at=received_at,
        )


def _extract_text(payload: dict) -> str:
    if payload.get("mimeType", "").startswith("text/plain") and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _extract_text(part)
        if text:
            return text
    return ""
```

**Step 3: Commit**

```bash
git add apps/api/src/openforce/gmail/client.py apps/api/tests/unit/test_gmail_client.py
git commit -m "feat(gmail): read client (history list + message fetch + text extract)"
```

---

## Task 14: Ingest service — store new emails

**Files:**
- Create: `apps/api/src/openforce/gmail/ingest.py`
- Test: `apps/api/tests/unit/test_ingest.py`

**Step 1: Failing test** — provide a fake `GmailClient` that returns 2 `GmailMessage` objects; assert 2 rows inserted into `emails` table and second invocation with same msg_ids is a no-op.

**Step 2: Implement**

```python
# gmail/ingest.py
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.db.models import Email, EmailStatus, Integration, IntegrationProvider
from openforce.gmail.client import GmailClient


async def ingest_new_emails(session: AsyncSession) -> int:
    integration = (await session.execute(
        select(Integration).where(Integration.provider == IntegrationProvider.gmail)
    )).scalar_one()
    if integration.needs_reauth:
        return 0

    client = GmailClient(integration.access_token, integration.refresh_token)
    history_id = integration.history_id or client.initial_history_id()
    msg_ids, latest = client.list_history_since(history_id)

    inserted = 0
    for mid in msg_ids:
        msg = client.get_message(mid)
        email = Email(
            gmail_msg_id=msg.msg_id,
            thread_id=msg.thread_id,
            sender=msg.sender,
            subject=msg.subject,
            body_text=msg.body_text,
            received_at=msg.received_at,
            status=EmailStatus.unprocessed,
        )
        session.add(email)
        try:
            await session.commit()
            inserted += 1
        except IntegrityError:
            await session.rollback()  # duplicate gmail_msg_id

    integration.history_id = latest
    await session.commit()
    return inserted
```

**Step 3: Commit**

```bash
git add apps/api/src/openforce/gmail/ingest.py apps/api/tests/unit/test_ingest.py
git commit -m "feat(ingest): poll Gmail history and dedupe-store new emails"
```

---

# Phase 4 — Agent

## Task 15: Agent schemas + system prompt

**Files:**
- Create: `apps/api/src/openforce/agent/__init__.py`
- Create: `apps/api/src/openforce/agent/schemas.py`
- Create: `apps/api/src/openforce/agent/prompts.py`
- Test: `apps/api/tests/unit/test_agent_schemas.py`

**Step 1: Define Pydantic schemas + OpenAI tool definitions**

```python
# agent/schemas.py
from typing import Any, Literal
from pydantic import BaseModel, Field


SfObjectType = Literal["Account", "Contact", "Opportunity", "Task"]


class ProposeCrmUpdateArgs(BaseModel):
    sf_object_type: SfObjectType
    sf_record_id: str = Field(min_length=15, max_length=18)
    before: dict[str, Any]
    after: dict[str, Any]
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class ProposeNewRecordArgs(BaseModel):
    sf_object_type: SfObjectType
    fields: dict[str, Any]
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


OPENAI_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_salesforce_contacts",
            "description": "Search SF Contacts by name or email. Returns up to 10 candidates.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_open_opportunities",
            "description": "Return open Opportunities for a given AccountId.",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_crm_update",
            "description": "Propose an update to an existing SF record. Provide before/after diff.",
            "parameters": ProposeCrmUpdateArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_new_record",
            "description": "Propose creating a new SF record.",
            "parameters": ProposeNewRecordArgs.model_json_schema(),
        },
    },
]
```

**Step 2: System prompt**

```python
# agent/prompts.py
SYSTEM_PROMPT = """You are a Salesforce CRM operations assistant.

Given a single inbound email, your job is to figure out which (if any) CRM updates are warranted.

Rules:
1. ALWAYS use the search_* tools FIRST to ground your proposals in real records before proposing changes.
2. NEVER invent Salesforce record IDs. Only use IDs returned by a search_* tool.
3. If no CRM-relevant signal is present (newsletter, spam, internal note), end your turn with no proposal — return the assistant text "no_action".
4. For ambiguous references (e.g., two matching contacts), set confidence below 0.5 and explain the ambiguity in `reasoning`.
5. You may produce MULTIPLE proposals from a single email if multiple deals/contacts are referenced.
6. Stick to these object types: Account, Contact, Opportunity, Task.
7. confidence in (0,1] — calibrate honestly. < 0.5 means the human reviewer should treat as a hint, not a sure thing.
"""
```

**Step 3: Test schema validation rejects bad inputs**

```python
# tests/unit/test_agent_schemas.py
import pytest
from openforce.agent.schemas import ProposeCrmUpdateArgs


def test_rejects_short_record_id():
    with pytest.raises(ValueError):
        ProposeCrmUpdateArgs(
            sf_object_type="Opportunity",
            sf_record_id="too-short",
            before={"StageName": "Discovery"},
            after={"StageName": "Negotiation"},
            reasoning="...",
            confidence=0.8,
        )


def test_rejects_bad_confidence():
    with pytest.raises(ValueError):
        ProposeCrmUpdateArgs(
            sf_object_type="Opportunity",
            sf_record_id="006xx000000000000",
            before={}, after={},
            reasoning="...",
            confidence=1.5,
        )
```

**Step 4: Commit**

```bash
git add apps/api/src/openforce/agent apps/api/tests/unit/test_agent_schemas.py
git commit -m "feat(agent): schemas, system prompt, openai tool definitions"
```

---

## Task 16: Agent tool handlers

**Files:**
- Create: `apps/api/src/openforce/agent/tools.py`
- Test: `apps/api/tests/unit/test_agent_tools.py`

**Step 1: Failing test** — fake `SalesforceClient` returns known records; assert each tool handler returns the expected JSON-serializable payload, and that `propose_crm_update` writes a `Proposal` row.

**Step 2: Implement**

```python
# agent/tools.py
import json
import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.agent.schemas import ProposeCrmUpdateArgs, ProposeNewRecordArgs
from openforce.db.models import Proposal, ProposalStatus
from openforce.salesforce.client import SalesforceClient


class ToolContext:
    """Stable handle for tool handlers: SF read client + DB session + current email id."""
    def __init__(self, sf: SalesforceClient, session: AsyncSession, email_id: uuid.UUID) -> None:
        self.sf = sf
        self.session = session
        self.email_id = email_id


async def handle_tool_call(ctx: ToolContext, name: str, raw_args: str) -> str:
    args = json.loads(raw_args)
    if name == "search_salesforce_contacts":
        return json.dumps(ctx.sf.search_contacts(args["query"]))
    if name == "search_open_opportunities":
        return json.dumps(ctx.sf.search_open_opportunities(args["account_id"]))
    if name == "propose_crm_update":
        parsed = ProposeCrmUpdateArgs(**args)
        proposal = Proposal(
            email_id=ctx.email_id,
            sf_object_type=parsed.sf_object_type,
            sf_record_id=parsed.sf_record_id,
            diff_payload={"before": parsed.before, "after": parsed.after},
            reasoning=parsed.reasoning,
            confidence=parsed.confidence,
            status=ProposalStatus.pending,
        )
        ctx.session.add(proposal)
        await ctx.session.commit()
        return json.dumps({"ok": True, "proposal_id": str(proposal.id)})
    if name == "propose_new_record":
        parsed = ProposeNewRecordArgs(**args)
        proposal = Proposal(
            email_id=ctx.email_id,
            sf_object_type=parsed.sf_object_type,
            sf_record_id=None,
            diff_payload={"before": {}, "after": parsed.fields},
            reasoning=parsed.reasoning,
            confidence=parsed.confidence,
            status=ProposalStatus.pending,
        )
        ctx.session.add(proposal)
        await ctx.session.commit()
        return json.dumps({"ok": True, "proposal_id": str(proposal.id)})
    raise ValueError(f"unknown tool: {name}")
```

**Step 3: Commit**

```bash
git add apps/api/src/openforce/agent/tools.py apps/api/tests/unit/test_agent_tools.py
git commit -m "feat(agent): tool handlers backed by SF client and proposals table"
```

---

## Task 17: Agent runner (OpenAI function-calling loop)

**Files:**
- Create: `apps/api/src/openforce/agent/runner.py`
- Test: `apps/api/tests/unit/test_agent_runner.py`

**Step 1: Failing test** — patch `openai.OpenAI.chat.completions.create` with a sequence of responses that simulate (a) tool call → (b) tool call → (c) final assistant message. Assert tool handlers were invoked in order and final email status set to `proposed`.

**Step 2: Implement**

```python
# agent/runner.py
import json
import uuid
from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.agent.prompts import SYSTEM_PROMPT
from openforce.agent.schemas import OPENAI_TOOLS
from openforce.agent.tools import ToolContext, handle_tool_call
from openforce.config import get_settings
from openforce.db.models import Email, EmailStatus
from openforce.salesforce.client import SalesforceClient


MAX_TOOL_ITERS = 6


async def run_agent_for_email(session: AsyncSession, sf: SalesforceClient, email: Email) -> EmailStatus:
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    ctx = ToolContext(sf=sf, session=session, email_id=email.id)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _format_user_msg(email)},
    ]

    proposed_anything = False
    for _ in range(MAX_TOOL_ITERS):
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})

        if not msg.tool_calls:
            content = (msg.content or "").strip().lower()
            return EmailStatus.proposed if proposed_anything else (
                EmailStatus.irrelevant if "no_action" in content else EmailStatus.proposed
            )

        for tc in msg.tool_calls:
            try:
                result = await handle_tool_call(ctx, tc.function.name, tc.function.arguments)
                if tc.function.name in ("propose_crm_update", "propose_new_record"):
                    proposed_anything = True
            except Exception as e:  # tool error feedback
                result = json.dumps({"ok": False, "error": str(e)})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
    # Iter budget exhausted
    return EmailStatus.extraction_failed


def _format_user_msg(email: Email) -> str:
    return (
        f"From: {email.sender}\n"
        f"Subject: {email.subject}\n"
        f"Received: {email.received_at.isoformat()}\n\n"
        f"{email.body_text}"
    )
```

**Step 3: Commit**

```bash
git add apps/api/src/openforce/agent/runner.py apps/api/tests/unit/test_agent_runner.py
git commit -m "feat(agent): OpenAI function-calling loop with tool dispatch"
```

---

## Task 18: Process-one-email pipeline (ingest → agent → store proposals)

**Files:**
- Create: `apps/api/src/openforce/proposals/__init__.py`
- Create: `apps/api/src/openforce/proposals/service.py`
- Test: `apps/api/tests/unit/test_pipeline.py`

**Step 1: Failing test** — given an unprocessed `Email` row, stub the agent runner, assert it's invoked and email status flips.

**Step 2: Implement**

```python
# proposals/service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.agent.runner import run_agent_for_email
from openforce.db.models import Email, EmailStatus, Integration, IntegrationProvider
from openforce.salesforce.client import SalesforceClient


async def process_one_email(session: AsyncSession, email_id) -> EmailStatus:
    email = (await session.execute(select(Email).where(Email.id == email_id))).scalar_one()
    integration = (await session.execute(
        select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
    )).scalar_one()
    sf = SalesforceClient(integration.access_token, integration.instance_url)
    try:
        new_status = await run_agent_for_email(session, sf, email)
    except Exception as e:
        email.status = EmailStatus.extraction_failed
        email.error = str(e)
        await session.commit()
        return email.status
    email.status = new_status
    await session.commit()
    return new_status


async def process_unprocessed_batch(session: AsyncSession, limit: int = 20) -> int:
    rows = (await session.execute(
        select(Email.id).where(Email.status == EmailStatus.unprocessed).limit(limit)
    )).scalars().all()
    for eid in rows:
        await process_one_email(session, eid)
    return len(rows)
```

**Step 3: Commit**

```bash
git add apps/api/src/openforce/proposals apps/api/tests/unit/test_pipeline.py
git commit -m "feat(proposals): single-email and batch processing pipeline"
```

---

## Task 19: Background scheduler

**Files:**
- Create: `apps/api/src/openforce/workers/__init__.py`
- Create: `apps/api/src/openforce/workers/scheduler.py`
- Modify: `apps/api/src/openforce/main.py` (lifespan to start scheduler)
- Test: `apps/api/tests/unit/test_scheduler.py`

**Step 1: Implement APScheduler-backed lifespan**

```python
# workers/scheduler.py
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from openforce.config import get_settings
from openforce.db.session import SessionLocal
from openforce.gmail.ingest import ingest_new_emails
from openforce.proposals.service import process_unprocessed_batch


async def _tick() -> None:
    async with SessionLocal() as s:
        await ingest_new_emails(s)
        await process_unprocessed_batch(s)


@asynccontextmanager
async def scheduler_lifespan(app):
    sched = AsyncIOScheduler()
    interval = get_settings().poll_interval_seconds
    sched.add_job(_tick, "interval", seconds=interval, id="poll", coalesce=True, max_instances=1)
    sched.start()
    try:
        yield
    finally:
        sched.shutdown(wait=False)
```

Modify `main.py`:

```python
from openforce.workers.scheduler import scheduler_lifespan
app = FastAPI(title="Openforce", version="0.1.0", lifespan=scheduler_lifespan)
```

**Step 2: Commit**

```bash
git add apps/api/src/openforce/workers apps/api/src/openforce/main.py apps/api/tests/unit/test_scheduler.py
git commit -m "feat(workers): APScheduler-driven poll + process tick"
```

---

# Phase 5 — Salesforce writer

## Task 20: Writer with pre-write revalidation + audit log

**Files:**
- Create: `apps/api/src/openforce/salesforce/writer.py`
- Test: `apps/api/tests/unit/test_sf_writer.py`

**Step 1: Failing test** — given a `Proposal` with `before`/`after`, mock SF `get_record` to return current state. If current matches `before`, expect `update_record` call + `audit_log` row + `Proposal.status = approved`. If current diverges, expect `failed_validation` and no write.

**Step 2: Implement**

```python
# salesforce/writer.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.db.models import AuditLog, Integration, IntegrationProvider, Proposal, ProposalStatus
from openforce.salesforce.client import SalesforceClient


async def execute_proposal(session: AsyncSession, proposal_id) -> ProposalStatus:
    proposal = (await session.execute(select(Proposal).where(Proposal.id == proposal_id))).scalar_one()
    integration = (await session.execute(
        select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
    )).scalar_one()
    sf = SalesforceClient(integration.access_token, integration.instance_url)

    audit_before: dict = {}
    audit_after: dict = {}
    try:
        if proposal.sf_record_id:
            # Update path: revalidate `before` state
            claimed_before = proposal.diff_payload.get("before", {})
            current = sf.get_record(proposal.sf_object_type, proposal.sf_record_id)
            for field, claimed in claimed_before.items():
                if current.get(field) != claimed:
                    proposal.status = ProposalStatus.failed_validation
                    proposal.error = f"Field {field}: expected {claimed!r}, found {current.get(field)!r}"
                    await session.commit()
                    return proposal.status
            sf.update_record(proposal.sf_object_type, proposal.sf_record_id, proposal.diff_payload["after"])
            audit_before = {k: current.get(k) for k in proposal.diff_payload["after"].keys()}
            audit_after = proposal.diff_payload["after"]
            sf_record_id = proposal.sf_record_id
        else:
            # Create path
            sf_record_id = sf.create_record(proposal.sf_object_type, proposal.diff_payload["after"])
            audit_after = proposal.diff_payload["after"]
        proposal.status = ProposalStatus.approved
    except Exception as e:
        proposal.status = ProposalStatus.failed
        proposal.error = str(e)
        await session.commit()
        return proposal.status

    session.add(AuditLog(
        proposal_id=proposal.id,
        sf_record_id=sf_record_id,
        before_state=audit_before,
        after_state=audit_after,
        success=True,
    ))
    await session.commit()
    return proposal.status
```

**Step 3: Commit**

```bash
git add apps/api/src/openforce/salesforce/writer.py apps/api/tests/unit/test_sf_writer.py
git commit -m "feat(salesforce): writer with pre-write revalidation and audit log"
```

---

# Phase 6 — Dashboard API endpoints

## Task 21: Proposals REST API

**Files:**
- Create: `apps/api/src/openforce/api/proposals.py`
- Test: `apps/api/tests/unit/test_api_proposals.py`

**Step 1: Failing test** — `GET /proposals?status=pending` returns seeded proposals; `POST /proposals/{id}/approve` invokes `execute_proposal`; `POST /proposals/{id}/reject` flips status; `PATCH /proposals/{id}` accepts an edited `after` payload before approval.

**Step 2: Implement**

```python
# api/proposals.py
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.db.models import Proposal, ProposalStatus
from openforce.db.session import get_session
from openforce.salesforce.writer import execute_proposal

router = APIRouter(prefix="/proposals", tags=["proposals"])


class ProposalOut(BaseModel):
    id: UUID
    email_id: UUID
    sf_object_type: str
    sf_record_id: str | None
    diff_payload: dict[str, Any]
    reasoning: str
    confidence: float
    status: ProposalStatus
    error: str | None

    class Config:
        from_attributes = True


@router.get("", response_model=list[ProposalOut])
async def list_proposals(status: ProposalStatus | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(Proposal).order_by(Proposal.confidence.asc(), Proposal.created_at.desc())
    if status:
        stmt = stmt.where(Proposal.status == status)
    return (await session.execute(stmt)).scalars().all()


@router.get("/{proposal_id}", response_model=ProposalOut)
async def get_proposal(proposal_id: UUID, session: AsyncSession = Depends(get_session)):
    p = (await session.execute(select(Proposal).where(Proposal.id == proposal_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(404)
    return p


class EditIn(BaseModel):
    after: dict[str, Any]


@router.patch("/{proposal_id}", response_model=ProposalOut)
async def edit_proposal(proposal_id: UUID, body: EditIn, session: AsyncSession = Depends(get_session)):
    p = (await session.execute(select(Proposal).where(Proposal.id == proposal_id))).scalar_one()
    if p.status != ProposalStatus.pending:
        raise HTTPException(400, "only pending proposals can be edited")
    p.diff_payload = {**p.diff_payload, "after": body.after}
    await session.commit()
    await session.refresh(p)
    return p


@router.post("/{proposal_id}/approve", response_model=ProposalOut)
async def approve(proposal_id: UUID, session: AsyncSession = Depends(get_session)):
    await execute_proposal(session, proposal_id)
    p = (await session.execute(select(Proposal).where(Proposal.id == proposal_id))).scalar_one()
    return p


@router.post("/{proposal_id}/reject", response_model=ProposalOut)
async def reject(proposal_id: UUID, session: AsyncSession = Depends(get_session)):
    p = (await session.execute(select(Proposal).where(Proposal.id == proposal_id))).scalar_one()
    p.status = ProposalStatus.rejected
    await session.commit()
    await session.refresh(p)
    return p
```

Register router in `main.py`.

**Step 3: Commit**

```bash
git add apps/api/src/openforce/api/proposals.py apps/api/src/openforce/main.py apps/api/tests/unit/test_api_proposals.py
git commit -m "feat(api): proposals endpoints (list, get, edit, approve, reject)"
```

---

# Phase 7 — Dashboard UI

## Task 22: SWR API client + types

**Files:**
- Create: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/types.ts`

```typescript
// lib/types.ts
export type ProposalStatus = "pending" | "approved" | "rejected" | "failed" | "failed_validation";

export interface Proposal {
  id: string;
  email_id: string;
  sf_object_type: "Account" | "Contact" | "Opportunity" | "Task";
  sf_record_id: string | null;
  diff_payload: { before: Record<string, unknown>; after: Record<string, unknown> };
  reasoning: string;
  confidence: number;
  status: ProposalStatus;
  error: string | null;
}
```

```typescript
// lib/api.ts
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  listProposals: (status = "pending") => req<import("./types").Proposal[]>(`/proposals?status=${status}`),
  approve: (id: string) => req(`/proposals/${id}/approve`, { method: "POST" }),
  reject: (id: string) => req(`/proposals/${id}/reject`, { method: "POST" }),
  edit: (id: string, after: Record<string, unknown>) =>
    req(`/proposals/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ after }),
    }),
};
```

Commit: `feat(web): API client + types for proposals`.

---

## Task 23: Proposal card + dashboard list

**Files:**
- Create: `apps/web/src/components/ProposalCard.tsx`
- Create: `apps/web/src/components/DiffView.tsx`
- Create: `apps/web/src/components/ConfidenceBadge.tsx`
- Modify: `apps/web/src/app/page.tsx`

**Step 1: `ConfidenceBadge.tsx`**

```tsx
export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "bg-emerald-100 text-emerald-800"
    : value >= 0.5 ? "bg-amber-100 text-amber-800"
    : "bg-rose-100 text-rose-800";
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${color}`}>{pct}% confidence</span>;
}
```

**Step 2: `DiffView.tsx`**

```tsx
export function DiffView({ before, after }: { before: Record<string, unknown>; after: Record<string, unknown> }) {
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]));
  return (
    <table className="w-full text-sm">
      <thead className="text-slate-500">
        <tr><th className="text-left">Field</th><th className="text-left">Before</th><th className="text-left">After</th></tr>
      </thead>
      <tbody>
        {keys.map(k => {
          const b = before[k], a = after[k];
          const changed = JSON.stringify(b) !== JSON.stringify(a);
          return (
            <tr key={k} className={changed ? "bg-amber-50" : ""}>
              <td className="font-mono">{k}</td>
              <td className="text-rose-700 line-through">{b == null ? "—" : String(b)}</td>
              <td className="text-emerald-700">{a == null ? "—" : String(a)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

**Step 3: `ProposalCard.tsx`**

```tsx
"use client";
import { useState } from "react";
import { Proposal } from "@/lib/types";
import { api } from "@/lib/api";
import { DiffView } from "./DiffView";
import { ConfidenceBadge } from "./ConfidenceBadge";

export function ProposalCard({ proposal, onChange }: { proposal: Proposal; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const action = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    try { await fn(); onChange(); } finally { setBusy(false); }
  };
  return (
    <article className="rounded-lg border bg-white p-4 shadow-sm">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium">
            {proposal.sf_record_id ? `Update ${proposal.sf_object_type}` : `Create ${proposal.sf_object_type}`}
          </h2>
          <p className="text-xs text-slate-500">{proposal.sf_record_id ?? "(new record)"}</p>
        </div>
        <ConfidenceBadge value={proposal.confidence} />
      </header>
      <div className="mt-3">
        <DiffView before={proposal.diff_payload.before} after={proposal.diff_payload.after} />
      </div>
      <p className="mt-3 text-sm text-slate-700"><strong>Reasoning:</strong> {proposal.reasoning}</p>
      <footer className="mt-4 flex gap-2">
        <button disabled={busy} onClick={action(() => api.approve(proposal.id))}
          className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
          Approve
        </button>
        <button disabled={busy} onClick={action(() => api.reject(proposal.id))}
          className="rounded bg-white px-3 py-1.5 text-sm font-medium text-rose-700 ring-1 ring-rose-200 hover:bg-rose-50 disabled:opacity-50">
          Reject
        </button>
      </footer>
    </article>
  );
}
```

**Step 4: `app/page.tsx`**

```tsx
"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import { ProposalCard } from "@/components/ProposalCard";

export default function Home() {
  const { data, error, isLoading, mutate } = useSWR("proposals/pending", () => api.listProposals("pending"));
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-3xl font-semibold">Pending proposals</h1>
      {error && <p className="mt-4 text-rose-700">Error: {String(error)}</p>}
      {isLoading && <p className="mt-4 text-slate-500">Loading…</p>}
      <div className="mt-6 space-y-4">
        {data?.length === 0 && <p className="text-slate-500">Inbox is clean.</p>}
        {data?.map(p => <ProposalCard key={p.id} proposal={p} onChange={() => mutate()} />)}
      </div>
    </main>
  );
}
```

**Step 5: Commit**

```bash
git add apps/web/src
git commit -m "feat(web): dashboard list + proposal card with diff/reasoning/approve"
```

---

## Task 24: Edit modal (in-place edit of `after` payload)

**Files:**
- Create: `apps/web/src/components/EditModal.tsx`
- Modify: `apps/web/src/components/ProposalCard.tsx` (add Edit button)

Edit modal displays each `after` key as a text input prefilled with current value; Save calls `api.edit(id, newAfter)` then triggers refresh.

Commit: `feat(web): edit proposal before approve`.

---

# Phase 8 — Tests, fixtures, demo, deployment

## Task 25: Agent regression fixture suite (the demo dataset)

**Files:**
- Create: `apps/api/tests/fixtures/emails/01-stage-advance.json` ... `15-very-long.json`
- Create: `apps/api/tests/fixtures/expected/*.json` (expected proposals per fixture)
- Create: `apps/api/tests/agent/test_fixture_suite.py`

**Fixture JSON shape:**

```json
{
  "name": "stage-advance",
  "email": {
    "sender": "sam@acme.test",
    "subject": "Re: Q3 Renewal",
    "received_at": "2026-05-10T10:00:00Z",
    "body_text": "Hi! We've reviewed the proposal and are ready to move forward — sending to procurement for signature this week."
  },
  "sf_state": {
    "contacts": [{"Id": "003xx000000000001", "Email": "sam@acme.test", "AccountId": "001xx000000000001"}],
    "opportunities": [{"Id": "006xx000000000001", "AccountId": "001xx000000000001", "Name": "Acme - Q3 Renewal", "StageName": "Discovery", "Amount": 30000}]
  },
  "expect": {
    "proposals_count": 1,
    "proposal": {
      "sf_object_type": "Opportunity",
      "sf_record_id": "006xx000000000001",
      "before": {"StageName": "Discovery"},
      "after_contains_keys": ["StageName"],
      "min_confidence": 0.6
    }
  }
}
```

**The 15 fixtures:**

| # | Name | Expected |
|---|---|---|
| 01 | `stage-advance` | 1 update on existing Opp |
| 02 | `new-contact` | 1 create Contact |
| 03 | `new-opp` | 1 create Opportunity |
| 04 | `ambiguous-sam` | 1 proposal with confidence < 0.5 + reasoning notes ambiguity |
| 05 | `irrelevant-newsletter` | 0 proposals, email marked `irrelevant` |
| 06 | `conflicting-state` | 1 proposal with reasoning flagging conflict |
| 07 | `multi-deal-thread` | 2 proposals |
| 08 | `empty-body` | 0 proposals, `irrelevant` |
| 09 | `forwarded-chain` | 1 proposal (must read past forward header) |
| 10 | `signature-noise` | 1 proposal, ignores disclaimer text |
| 11 | `non-english` | 1 proposal (Spanish body) |
| 12 | `stage-regression` | 1 proposal, flagged in reasoning |
| 13 | `task-from-email` | 1 Task create proposal with due date |
| 14 | `new-account` | 1 Account create + 1 Contact create |
| 15 | `very-long` | 1 proposal (body > 12k chars, exercises truncation/summarization) |

**Test harness:**

```python
# tests/agent/test_fixture_suite.py
import json, pathlib, pytest
from unittest.mock import patch
from openforce.agent.runner import run_agent_for_email
# ... build an in-memory Email object and stub SalesforceClient.search_* with sf_state from fixture

FIXTURES = sorted(pathlib.Path(__file__).parent.parent.joinpath("fixtures/emails").glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
@pytest.mark.asyncio
async def test_fixture(path):
    fixture = json.loads(path.read_text())
    # ... run agent, collect produced Proposal rows, compare against fixture["expect"]
```

**These fixtures are also the canned demo dataset.**

Commit: `test(agent): 15-fixture regression suite + canned demo emails`.

---

## Task 26: E2E smoke against SF Developer Org

**File:**
- Create: `apps/api/tests/e2e/test_e2e_smoke.py`

Marked `@pytest.mark.e2e`; gated by an env var (skip in default CI). Runs:
1. Insert `Integration` row with real SF tokens (read from env)
2. Insert a fixture `Email` (the `stage-advance` one)
3. Run `process_one_email`
4. Approve the resulting proposal via the writer
5. Verify SF Opportunity `StageName` actually changed
6. Reset SF state (set back to Discovery) for next run

Commit: `test(e2e): smoke test against SF Developer Org (manual gate)`.

---

## Task 27: README + demo script

**Files:**
- Create: `README.md` at repo root

Sections:
1. **What is this** — 1-paragraph elevator pitch + GIF placeholder
2. **Architecture diagram** — ASCII / mermaid from the design doc
3. **Demo (2 min walkthrough)** — exactly the demo script from §7 of the design doc
4. **How it works** — agent loop, function-calling tools, propose-and-approve flow
5. **Run locally** — `docker compose up -d db; cd apps/api && uv sync && uv run alembic upgrade head && uv run uvicorn openforce.main:app --reload`; SF + Gmail OAuth setup steps; `cd apps/web && npm install && npm run dev`
6. **Tests** — `pytest`, fixture suite, E2E gate
7. **Tech & decisions** — links to design doc and learnings

Commit: `docs: README with architecture, demo script, run instructions`.

---

## Task 28: Deploy — Railway (API) + Vercel (web)

**Files:**
- Create: `apps/api/Dockerfile`
- Create: `apps/api/railway.json` (optional)
- Modify: `apps/web/next.config.mjs` (set `NEXT_PUBLIC_API_BASE` env)

**Step 1: Dockerfile**

```dockerfile
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install uv
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --frozen --no-dev || uv sync --no-dev
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "alembic upgrade head && uvicorn openforce.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

**Step 2: Railway**
- New project from GitHub
- Add Postgres plugin → wire `DATABASE_URL` / `DATABASE_URL_SYNC`
- Add env vars from `.env.example`
- Update SF and Google OAuth redirect URIs to the Railway public URL

**Step 3: Vercel**
- New project, root `apps/web`
- Env var: `NEXT_PUBLIC_API_BASE=<Railway URL>`
- Deploy

**Step 4: Run `/gitpush` skill, not raw `git push`.**

Commit: `feat(deploy): Dockerfile + Railway + Vercel config`.

---

## Task 29 (Stretch — optional): Trace/observability view

**Files:**
- Modify: `agent/runner.py` — record per-step trace events to DB
- Create: `apps/api/src/openforce/db/models.py` — add `AgentTrace` table
- Create: `apps/web/src/app/proposals/[id]/page.tsx` — trace detail view

Drop if v1 is shipped on time; otherwise this is the cherry on top of the portfolio.

---

# Verification gates (must pass before claiming v1 done)

- [ ] `cd apps/api && uv run pytest` — all unit + fixture tests pass
- [ ] `cd apps/web && npm run build` — clean build, no TS errors
- [ ] Local end-to-end: load a fixture email into DB, see proposal in dashboard, approve, see SF record update
- [ ] Hosted demo URL works (Vercel)
- [ ] README renders cleanly on GitHub with diagram + demo GIF
- [ ] All commits use Conventional Commits prefixes
- [ ] Pushed via `/gitpush` (no raw `git push` in history)

---

# After execution

When all 28 tasks (29 if stretch) are done:
1. Run `/capture-learnings` to harvest anything non-obvious into `learnings.md`
2. Update `CLAUDE.md`'s `## Completed Work` with v1 ship summary
3. Update `short_term_memory.md` with the v1 ship task

---

# Execution choice

This plan is ready to execute. Two options per the writing-plans skill:

1. **Subagent-Driven (this session)** — dispatch fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — open a new session with `superpowers:executing-plans`, batch execution with checkpoints.

Pick before starting.
