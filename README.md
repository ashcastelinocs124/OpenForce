# Openforce — AI CRM Autopilot

An AI assistant that reads your Gmail inbox, reasons about what's happening with each lead and deal, and proposes Salesforce CRM updates that a human approves with one click.

> Portfolio project. Showcases agentic AI (OpenAI function calling), production-style infra (FastAPI + Postgres + Next.js), and real third-party SaaS integrations (Gmail + Salesforce).

## What it does

1. **Polls Gmail** every 5 minutes for new messages.
2. **An OpenAI GPT-4o agent** reads each email with four function-calling tools:
   - `search_salesforce_contacts(query)` — look up existing contacts
   - `search_open_opportunities(account_id)` — find live deals
   - `propose_crm_update(payload)` — propose updating an existing record
   - `propose_new_record(payload)` — propose creating a new record
3. **Proposals queue** — every AI proposal lands in a dashboard with diff view, model reasoning, and a confidence score.
4. **Human approves** — one click applies the change to Salesforce. The writer revalidates the `before` state against live SF data before writing, so no surprise overwrites.
5. **Everything audited** — every executed change is logged in `audit_log` with before/after state.

## Architecture

```
┌─────────────┐    poll       ┌──────────────────┐    function calls  ┌──────────────┐
│   Gmail     │ ◄──────────── │  Ingest Worker   │ ─────────────────► │   OpenAI     │
│   (OAuth)   │  every 5 min  │   (FastAPI bg)   │ ◄─────────────────  │   GPT-4o     │
└─────────────┘                └────────┬─────────┘     proposals     └──────┬───────┘
                                        │                                    │
                                        ▼                                    │ search SF /
                                ┌──────────────┐                             │ propose update
                                │  Postgres    │ ◄───────────────────────────┘
                                │  (state +    │
                                │  proposals)  │
                                └──────┬───────┘
                                       │ read pending
                                       ▼
                              ┌────────────────┐    approve     ┌──────────────┐
                              │ Next.js        │ ─────────────► │  Salesforce  │
                              │ Dashboard      │  via writer    │  (REST API)  │
                              └────────────────┘                └──────────────┘
```

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic |
| Database | Postgres 16 |
| Model | OpenAI GPT-4o via `openai` Python SDK with function calling |
| Salesforce | `simple-salesforce` |
| Gmail | `google-api-python-client` |
| Scheduler | APScheduler (in-process tick) |
| Frontend | Next.js 14 (App Router) · TypeScript · Tailwind · SWR |
| CI | GitHub Actions |

## Demo (2-minute walkthrough)

1. SF dev org starts with seed data: Acme Corp account, Sam Patel & Jordan Lee contacts, one Q3 Renewal opportunity in Discovery.
2. New email arrives in Gmail: *"We're ready to move forward — sending to procurement this week."*
3. The agent loop:
   - Calls `search_salesforce_contacts("sam@acme.test")` → finds Sam Patel
   - Calls `search_open_opportunities("001…Acme")` → finds the Q3 Renewal
   - Calls `propose_crm_update({Opportunity, StageName: Discovery → Negotiation, confidence 0.9})`
4. Dashboard refreshes — proposal appears with the diff, reasoning, and a green Approve button.
5. Click **Approve** — writer revalidates current SF state, writes Stage to Negotiation, records the change in `audit_log`.
6. SF shows the new stage. The whole loop ran in ~5 seconds end-to-end.

## Run locally

```bash
# 1. Boot Postgres
docker compose up -d db

# 2. Backend
cd apps/api
cp ../../.env.example .env       # fill in OPENAI_API_KEY, SF + Gmail OAuth credentials
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn openforce.main:app --reload  # http://localhost:8000

# 3. Frontend (separate terminal)
cd apps/web
npm install --legacy-peer-deps
npm run dev                       # http://localhost:3000
```

Then visit `http://localhost:8000/auth/salesforce/start` and `/auth/gmail/start` to connect both OAuth providers. After that, the Gmail poll worker is active.

### Seed demo data into Salesforce

After connecting SF OAuth:

```bash
cd apps/api
uv run python scripts/seed_sf.py
```

## Tests

```bash
cd apps/api

# Unit + integration tests (require Postgres running)
uv run pytest -v

# Agent fixture suite (live OpenAI calls — costs cents)
OPENFORCE_RUN_AGENT_FIXTURES=1 OPENAI_API_KEY=sk-... uv run pytest tests/agent/ -v

# End-to-end smoke (live Salesforce Developer Org)
OPENFORCE_RUN_E2E=1 uv run pytest tests/e2e/ -v
```

49 unit/integration tests at last count. The agent fixture suite runs 5 curated email scenarios (stage advance, new contact, irrelevant newsletter, ambiguous reference, multi-deal thread) against a real OpenAI call. These fixtures double as the canned demo dataset.

## Design & plan

- `docs/plans/2026-05-15-ai-crm-autopilot-design.md` — full design, debate history, risk register
- `docs/plans/2026-05-15-ai-crm-autopilot-plan.md` — task-by-task TDD implementation plan

## Deployment

- **API** → Railway (Postgres plugin + Dockerfile in `apps/api/Dockerfile`)
- **Web** → Vercel (root `apps/web`, env var `NEXT_PUBLIC_API_BASE` = Railway URL)

After deploying, update the OAuth redirect URIs in Salesforce Connected App + Google Cloud Console to point at the Railway public URL.

## Conventions

- **No SF write without human approval.** All AI updates flow through the proposal queue.
- **Tool-grounded proposals.** The agent can only reference SF records returned by `search_*` tools — it never invents IDs. The writer re-fetches and revalidates before every write.
- **Idempotent ingest.** Unique constraint on `emails.gmail_msg_id` makes duplicate polls free.
- **Every write audited.** `audit_log` rows record `(proposal_id, sf_record_id, before, after, success)`.
- **All git pushes go through the `/gitpush` skill** (pre-push secret scan).

## What's intentionally out of scope (v1)

- The other three CRM-autopilot wedges: follow-up nudges, leak-proof pipeline, draft messages
- Multi-CRM (HubSpot, Pipedrive)
- Multi-tenancy / billing
- Sending emails on the user's behalf
- Realtime push (we poll on a 5-min cadence)

## Status

v1 complete. 17 sequential waves, TDD throughout, 49 tests passing.
