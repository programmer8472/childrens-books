# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

An AI-powered children's book publishing pipeline. A user submits a story brief; the system runs competing writer agents, judges their output, loops until quality passes, then generates illustrations and KDP-ready export files. The human approves at defined gates; the rest is automated.

**v1 is single-user.** No auth, no multi-tenancy, no billing, no KDP API automation. These are designed-for but deliberately deferred.

---

## Commands

```bash
make up          # docker-compose up — starts API, worker, Postgres, Redis
make down        # docker-compose down
make migrate     # alembic upgrade head
make test        # pytest
make test-one    # pytest tests/path/to/test.py::test_name
```

All config flows through env vars; copy `.env.example` to `.env` before first run. Local disk stands in for S3 in dev.

---

## Tech stack

- **Backend:** Python, FastAPI, Celery (workers), Redis (broker + pub/sub), PostgreSQL, SQLAlchemy + Alembic
- **Frontend:** Next.js, React, Tailwind (built in Unit 9; talks only to the API)
- **Storage:** S3 in prod; `LocalStorage` implementation for dev

---

## Core architectural principle

> **The orchestrator owns sequencing. Agents own thinking. Providers own vendors. The DB owns truth.**

These four responsibilities must not leak into each other. Violating this makes the later multi-tenant refactor a teardown instead of an additive change.

---

## Pipeline state machine

Every book has a `status`. `BookRepo.transition()` is the **only** way to change it, and every call writes an `audit_log` row. Automated steps use `actor="orchestrator"`; human gate actions (approve/reject) use `actor="human"` via the API.

```
DRAFT_BRIEF → OUTLINING → WRITING → JUDGING → REVISION (loops, capped)
  → AWAITING_APPROVAL → APPROVED → GENERATING_IMAGES → GENERATING_COVER
  → DRAFTING_METADATA → EXPORTING → EXPORT_READY → (manual KDP upload → DONE)

RETIRED  ← exceeded max revision rounds, or human kills it
```

Keep the stage enum and legal-transition table in **one place**. Never hardcode stage strings in multiple files.

**Kanban colors:** green = auto-advanced, yellow = running in worker, blue = awaiting human, red = failed/retired.

---

## Build sequence

Do not start a unit until the previous unit's verification passes and is committed. See [docs/build-log.md](docs/build-log.md) for per-unit implementation details.

| Unit | Status | Goal |
|------|--------|------|
| 0 | DONE | Repo + docker-compose: FastAPI, Celery, Redis, Postgres, `/health`, trivial worker task, LocalStorage |
| 1 | DONE | All DB tables + migrations + status enum + transition table + repository layer |
| 2 | DONE | `LLMProvider` + `ImageProvider` interfaces with `Fake*` implementations |
| 3 | DONE | `WriterAgent` + `JudgeAgent` with structured I/O and retry on bad JSON |
| 4 | DONE | Orchestrator + full writer/judge loop, end-to-end on fakes |
| 5 | DONE | FastAPI endpoints + WebSocket progress |
| 6 | DONE | Real LLM provider (DeepSeek via OpenAI-compatible SDK) |
| 7 | IN PROGRESS | `PlaceholderImageProvider` done (correct spread dims, prompt text overlay). `LeonardoImageProvider` + `character_assets` pending API key — swap `IMAGE_PROVIDER=leonardo`, no other code changes needed |
| 8 | DONE | Compositor (`app/compositor/` — 8 modules), `MetadataAgent`, `BookComposer.compose_all` (interior PDF, cover PDF, Word, Markdown, text, images); full post-approval pipeline wired; `GET/PUT /metadata`, `GET /export/{artifact}` API; 225 tests passing |
| 9 | **NEXT** | Next.js frontend: Kanban board, approval gate, inline paragraph editor |

---

## Reference docs

- [docs/architecture-and-build-guide.md](docs/architecture-and-build-guide.md) — full architecture spec, data model, API surface, and unit prompt scaffolds
- [docs/book-design-spec.md](docs/book-design-spec.md) — complete binding design spec for the compositor (typography, spread types, KDP print specs, color, cover)
- [docs/build-log.md](docs/build-log.md) — what was built in each completed unit

---

## What is explicitly out of scope for v1

Multi-tenancy, user auth/login, billing, per-user API keys, KDP API automation, similarity matrix, Story DNA library, collaborative roles, Enterprise judge/writer builder UI. Do not build toward these; do not let the model gold-plate them in.
