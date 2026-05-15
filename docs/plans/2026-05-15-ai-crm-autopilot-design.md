# AI CRM Autopilot — Design Document

**Date:** 2026-05-15
**Status:** Design approved, ready for implementation planning
**Project type:** Portfolio / learning project
**Author:** ashleyn4@illinois.edu

---

## 1. Premise

An AI assistant that keeps a Salesforce CRM updated automatically by ingesting the user's Gmail inbox, reasoning about what changed (deal stages, new contacts, new opportunities, follow-up tasks), and proposing structured updates that a human approves with one click.

This is the **wedge** of a larger "CRM autopilot" vision (follow-ups, draft messages, leak-proof pipeline). The other three capabilities are intentionally deferred — the auto-update wedge alone is enough portfolio surface to demonstrate end-to-end agentic AI on a realistic domain.

### Decisions locked in via debate

| Decision | Choice | Rationale |
|---|---|---|
| Primary wedge | Auto-update CRM | Highest portfolio leverage; pure ingest → reason → write pipeline |
| Target CRM | Salesforce (Developer Edition) | User already has dev org; demonstrates enterprise SaaS integration |
| Ingest source | Gmail (OAuth) | Most realistic input; portfolio-impressive integration |
| Write semantics | Propose → 1-click approve | Shows AI reasoning + judgment; safer than blind writes |
| Model | OpenAI GPT-4o (function calling) | Mature tool-use SDK |
| Project intent | Portfolio | Optimizes for demo quality and resume narrative, not commercial fit |

### Risks accepted

- **Extraction hallucination** — mitigated by grounded tool-use (model can only reference records returned by `search_*` tools) and pre-write revalidation
- **Demo dataset** — solved by the 15-fixture agent regression suite (doubles as canned demo input)
- **SF setup overhead** — dev org exists; seed data scripted

---

## 2. Architecture

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

### Components

1. **Ingest Worker** — FastAPI background task. Polls Gmail every 5 minutes via the Gmail History API; for each new message, kicks off the agent.
2. **Agent (OpenAI GPT-4o + function calling)** — Receives email text, calls tools, returns proposals + reasoning + confidence.
3. **Postgres** — Tables: `emails`, `proposals`, `audit_log`.
4. **Salesforce Writer** — Thin wrapper around `simple-salesforce`. Validates record IDs pre-write. Only invoked on approve.
5. **Dashboard (Next.js 14 + Tailwind)** — Pending proposals card view: source email excerpt, diff, reasoning, confidence, [Approve] / [Reject] / [Edit].
6. **Auth** — Google OAuth (Gmail), Salesforce Connected App OAuth (SF).

### Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12 + FastAPI + SQLAlchemy |
| Database | Postgres |
| Model | OpenAI GPT-4o via `openai` Python SDK |
| Salesforce | `simple-salesforce` |
| Gmail | `google-api-python-client` |
| Frontend | Next.js 14 + Tailwind |
| Hosting | Railway or Fly.io (backend) + Vercel (frontend) |
| CI | GitHub Actions |

### Function-calling tools exposed to the agent

| Tool | Purpose |
|---|---|
| `search_salesforce_contacts(query)` | Returns 0..N candidate contacts matching name/email/account |
| `search_open_opportunities(account_id)` | Returns existing opportunities for an account |
| `propose_crm_update(payload)` | Stores a proposal to update an existing SF record |
| `propose_new_record(payload)` | Stores a proposal to create a new SF record |

---

## 3. Data Flow

### 3.1 Ingest

```
Gmail Worker (cron, 5 min)
├─ Gmail History API: list messages since last_polled_at
├─ For each new msg: fetch body, headers, thread
└─ Insert row in `emails` (status: 'unprocessed')
```

### 3.2 Agent reasoning

```
For each unprocessed email:
├─ Build prompt: system + email body + thread context
├─ Call OpenAI with function-calling enabled
├─ Agent loop:
│   ├─ Model may call `search_salesforce_contacts("Sam Patel, Acme")`
│   │     → returns 0/1/N candidate matches
│   ├─ Model may call `search_open_opportunities(account_id)`
│   │     → returns existing deals
│   └─ Model calls `propose_crm_update(...)` or `propose_new_record(...)`
│         → handler stores proposal row, returns ack
└─ Mark email status: 'proposed' or 'no_action' (irrelevant)
```

### 3.3 Proposal queue

`proposals` row schema:
- `source_email_id`, `sf_object_type`, `sf_record_id` (null for new records)
- `diff_payload`: `{before: {...}, after: {...}}`
- `reasoning`: natural-language explanation from the agent
- `confidence`: model-reported 0–1
- `status`: `pending` / `approved` / `rejected` / `failed` / `failed_validation`

### 3.4 Human review

Dashboard polls `/proposals?status=pending`. User sees a card per proposal and clicks Approve / Reject / Edit. Edit opens a pre-filled form for adjustments.

### 3.5 Write

```
On approve:
├─ Salesforce Writer reads proposal
├─ Re-fetches current SF record state (revalidate diff `before`)
├─ Calls SF REST API (update or create)
├─ On success: proposal.status = 'approved', audit_log row inserted
└─ On failure: proposal.status = 'failed', surface error in dashboard
```

### Invariants

- One email → 0..N proposals
- No SF write without a human-approved proposal
- All writes recorded in `audit_log` (`proposal_id`, `sf_record_id`, `before`, `after`, `timestamp`)
- Reprocessing same Gmail message-id is idempotent (uniqueness on `emails.gmail_msg_id`)

---

## 4. Error Handling & Edge Cases

| Failure | Where | Response |
|---|---|---|
| Gmail OAuth token expired | Ingest worker | Refresh via stored refresh-token; if refresh fails → mark integration `needs_reauth`, surface banner. |
| Gmail API rate limit (429) | Ingest worker | Exponential backoff (1s → 60s max). |
| OpenAI returns malformed JSON | Agent | Retry once with stricter schema reminder. If still bad → `extraction_failed`, no proposal. |
| Model hallucinates SF record ID | Agent → writer | Writer validates ID existence pre-write. Not found → `failed_validation`. |
| SF API validation error | SF writer | Store error in proposal, mark `failed`, show inline in dashboard with [Retry]. |
| SF rate limit | SF writer | Backoff + retry ≤ 3x. |
| Concurrent emails about same deal | Agent | `search_open_opportunities` sees in-flight proposal → agent writes follow-up proposal referencing prior. |
| Approve → SF write fails | SF writer | Proposal stays `failed`. [Retry] button. Audit log records attempt. |
| Irrelevant email (newsletter, internal) | Agent | `no_action`, marked `irrelevant`. Toggleable in dashboard. |
| Duplicate Gmail msg | Ingest | Unique constraint on `gmail_msg_id`. |
| Worker crash mid-processing | Ingest | Email stays `unprocessed`; next poll retries. Idempotent. |
| Low-confidence proposal (< 0.5) | Agent | Still created; dashboard sorts by confidence ASC + red badge. |

### Hallucination mitigation (critical)

- Tools return *real* SF data — model grounds proposals in `search_*` results, never invents IDs
- Writer revalidates every record ID before SF write
- Diff view shows model's claimed `before` vs SF's actual `before` at write time — divergence blocks the write

### Explicitly out of scope

- Multi-user collaboration / approval workflows
- SF object types beyond Account / Contact / Opportunity / Task
- Email send-on-behalf (that's the "draft messages" wedge)

---

## 5. Testing Strategy

### Layer 1 — Unit tests

- `agent/tools.py` — each tool handler with fake SF responses
- `salesforce/writer.py` — mocked SDK, verify payloads and SF error handling
- `gmail/ingest.py` — mocked Gmail API, dedup, history-token handling, OAuth refresh
- Diff calculator
- Confidence parser / proposal validator (rejects malformed model output)

### Layer 2 — Agent regression suite (the interesting one)

~15 hand-crafted fixture emails, each with an expected proposal (or `no_action`):

1. Update existing deal stage
2. Create new contact (unknown sender)
3. Create new opportunity (known contact, new project)
4. Ambiguous reference (two Sams) → expect low confidence + clarification
5. Irrelevant email (newsletter) → `no_action`
6. Conflicting info (email contradicts SF state) → flagged proposal
7. Multi-deal email → 2 proposals
8. Empty body
9. Forwarded chain
10. Signature noise / disclaimer-heavy
11. Non-English body
12. Stage regression ("they want to pause") → flagged
13. Task creation ("send me the contract by Tuesday")
14. Account creation (new logo)
15. Edge: very long email (16k+ tokens, exercise truncation/summarization)

Runs as pytest. **Doubles as canned demo dataset.**

### Layer 3 — End-to-end smoke

One test runs the full path against the SF Developer Org: fixture email → agent → propose → auto-approve → verify SF record. Cleans up after. Manual / `main` branch only.

### CI

GitHub Actions runs Layers 1 + 2 on every push. Layer 3 runs manually (no SF creds in CI by default).

### Explicitly skipped

- Load testing, chaos testing, property-based, mutation testing
- Frontend component tests beyond a smoke render

---

## 6. Scope & Timeline

### MVP (v1 ships in ~2 weeks focused)

- Gmail OAuth + polling worker
- Agent w/ 4 function-calling tools
- Postgres state (emails, proposals, audit_log)
- Next.js dashboard
- SF writer: Account / Contact / Opportunity / Task
- Hosted demo (Railway + Vercel)
- 15-fixture regression suite
- README with architecture diagram, demo GIF, walkthrough

### Rough effort breakdown

| Phase | Days |
|---|---|
| Infra + auth (FastAPI, Postgres, Gmail OAuth, SF Connected App) | 3 |
| Agent + tools + prompt engineering | 4 |
| Dashboard (Next.js + approve/reject/edit) | 3 |
| Tests + fixture suite | 2 |
| Polish + hosted demo + README + screen recording | 2 |

### Out of scope (named to prevent drift)

- Other three wedge features (follow-ups, leak-proof pipeline, draft messages)
- Multi-CRM (HubSpot/Pipedrive)
- Multi-tenancy / billing
- Email send-on-behalf
- Mobile UI
- Realtime push (polling only in v1)
- Voice / call ingestion

### Stretch goals (post-v1, if time)

1. **Gmail Pub/Sub push** — replace polling, enable "real-time" demo claim
2. **Contact disambiguation with embeddings** — pgvector, resolves "Sam at Acme" → "Samuel Patel"
3. **Layer in one more wedge** — e.g., follow-up suggestions from same Gmail data
4. **Trace/observability dashboard** — token usage, tool-call traces, decision paths

---

## 7. Demo Script (~2 minutes)

1. Show empty Salesforce org + clean inbox
2. Trigger fixture inbox load (8 emails about Acme deal progressing through stages)
3. Refresh dashboard → 6 proposals appear with reasoning
4. Walk through: 1 high-confidence approve, 1 low-confidence with edit, 1 reject
5. Cut to Salesforce showing new opportunity created + stage advanced + contact linked
6. Close on trace view (if stretch goal hit) showing the agent's reasoning chain

---

## 8. Next step

Hand off to the `writing-plans` skill to produce a step-by-step implementation plan in `docs/plans/2026-05-15-ai-crm-autopilot-plan.md`.
