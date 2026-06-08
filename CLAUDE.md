# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

An AI-powered children's book publishing pipeline. A user submits a story brief; the system runs competing writer agents, judges their output, loops until quality passes, then generates illustrations and KDP-ready export files. The human approves at defined gates; the rest is automated.

**v1 is single-user.** No auth, no multi-tenancy, no billing, no KDP API automation. These are designed-for but deliberately deferred.

---

## Commands (once Unit 0 is built)

```bash
make up          # docker-compose up — starts API, worker, Postgres, Redis
make down        # docker-compose down
make migrate     # alembic upgrade head
make test        # pytest
make test-one    # pytest tests/path/to/test.py::test_name
```

The full stack runs locally via docker-compose. Local disk stands in for S3 in dev. All config flows through env vars; copy `.env.example` to `.env` before first run.

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

Every book has a `status`. The orchestrator is the **only** thing that transitions it, and every transition writes an `audit_log` row.

```
DRAFT_BRIEF → OUTLINING → WRITING → JUDGING → REVISION (loops, capped)
  → AWAITING_APPROVAL → APPROVED → GENERATING_IMAGES → GENERATING_COVER
  → DRAFTING_METADATA → EXPORTING → EXPORT_READY → (manual KDP upload → DONE)

RETIRED  ← exceeded max revision rounds, or human kills it
```

Keep the stage enum and legal-transition table in **one place**. Never hardcode stage strings in multiple files.

**Kanban colors:** green = auto-advanced, yellow = running in worker, blue = awaiting human, red = failed/retired.

---

## Writer/judge loop

The core quality mechanism:

1. Orchestrator fans out **N parallel writer tasks** (one per method: three-act, sensory-first, problem-solution, hero's-journey — whichever the template enables).
2. Each calls `WriterAgent.write(brief, method, prior_critique)` → saves a `story_versions` row.
3. One `JudgeAgent.judge(story_versions, criteria)` task scores all new versions → `judgements` rows.
4. Orchestrator picks the top `weighted_total`. If it clears the threshold → `AWAITING_APPROVAL`. Else if rounds remain → attach critique, back to `WRITING`. Else → `RETIRED`.

**Critical rules:**
- The judge must return **structured JSON** (schema: per-dimension scores 0–10 for `emotional_authenticity`, `representation_quality`, `pacing`, `age_fit`, `uniqueness`; per-dimension critique string; `weighted_total`; `passed`). Validate on the way out; on invalid JSON, retry up to 3 times, then raise — never crash the pipeline silently.
- Writers rewrite **from critique**, not from scratch. Pass `prior_version + judge critique` into the next round.
- The judge system prompt is a **versioned artifact** — store it with a version identifier and record which version produced each judgement. This is the highest-value thing to iterate on against real Amazon review data.

---

## Provider interfaces (the anti-vendor-lock seam)

No agent or orchestrator code ever imports a vendor SDK directly. Everything goes through:

```python
LLMProvider.generate(system: str, messages: list, *, json_schema=None) -> Response
ImageProvider.generate_scene(scene_prompt: str, character_ref: CharacterRef, params: dict) -> ImageResult
```

`CharacterRef` abstracts over "a set of reference images" OR "a trained model handle." The pipeline never checks which kind. Swapping the LLM vendor or image provider is a config change + one new class.

**Fake implementations** (`FakeLLMProvider`, `FakeImageProvider`) exist from Unit 2 onward — they let the full pipeline run offline for free and remain the test backbone forever. Always verify real-model calls can be switched back to fakes via env.

**Before wiring in any real model or image provider:** verify the current model name, endpoint, pricing, and commercial-use terms yourself. These change; don't trust any name or URL written in the architecture doc.

---

## Key data model notes

- `story_versions` and `audit_log` are **append-only** — no update or delete in the repo layer.
- `judgements` is separate from `story_versions` so a version can be re-judged.
- `images` records `seed` and all provider params for reproducibility.
- `character_assets` of `kind = "reference_images"` is v1. `kind = "trained_model"` is a future swap, same interface.
- `similarity_scores` is deferred past MVP.

---

## API design rule

Commands (`POST /books/{id}/approve`, etc.) return immediately and enqueue work. **Never block an HTTP request on an LLM or image call.** Progress flows over `WS /books/{id}/stream` via Redis pub/sub → FastAPI WebSocket.

Worker tasks are idempotent, keyed on `(book_id, round, method)`. Re-running a task overwrites cleanly.

---

## Build sequence

The project is built in units. **Do not start a unit until the previous unit's verification passes and is committed.** The fakes in Units 2–5 are the key — they let the entire pipeline logic be proven before any API spend.

| Unit | Status | Goal |
|------|--------|------|
| 0 | DONE | Repo + docker-compose: FastAPI, Celery, Redis, Postgres, `/health`, trivial worker task, LocalStorage |
| 1 | DONE | All DB tables + migrations + status enum + transition table + repository layer |
| 2 | DONE | `LLMProvider` + `ImageProvider` interfaces with `Fake*` implementations |
| 3 | DONE | `WriterAgent` + `JudgeAgent` with structured I/O and retry on bad JSON |
| 4 | DONE | Orchestrator + full writer/judge loop, end-to-end on fakes |
| 5 | **NEXT** | FastAPI endpoints + WebSocket progress |
| 6 | | Real LLM provider (verify model/endpoint/pricing first) |
| 7 | | Real image provider + `character_assets` (verify Leonardo terms first) |
| 8 | | Cover, metadata, export (KDP PDF + Word + Markdown + image folder) |
| 9 | | Next.js frontend: Kanban board, approval gate, inline paragraph editor |

### What was built in each completed unit

**Unit 0** — `docker-compose.yml` (Postgres 16 on 5433, Redis 7, API on 8001, Celery worker), `app/main.py` (`GET /health`, `POST /health/worker`), `app/tasks.py` (`ping` task).

**Unit 1** — `app/db/enums.py` (`BookStatus` + `LEGAL_TRANSITIONS` + `assert_legal_transition`), `app/db/models.py` (all 6 tables), `app/db/repos/` (one class per table), `migrations/versions/0002_schema.py`.

**Unit 2** — `app/providers/base.py` (`LLMProvider`, `ImageProvider` ABCs; `LLMResponse`, `CharacterRef`, `ImageResult` dataclasses), `app/providers/fake_llm.py` (`FakeLLMProvider` — injectable response queue, records calls), `app/providers/fake_image.py` (`FakeImageProvider`), `app/providers/factory.py` (`get_llm_provider` / `get_image_provider` driven by `Settings.llm_provider` / `Settings.image_provider`, both default to `"fake"`).

**Unit 3** — `app/agents/writer.py` (`WriterAgent.write(brief, method, prior_critique)` — 4 named methods, revision vs. fresh system prompts), `app/agents/judge.py` (`JudgeAgent.judge(story_versions, criteria)` — one LLM call per version, 3-retry loop with error fed back to LLM, `PROMPT_VERSION = "v1"`), `app/agents/base.py` (`JudgementResult`, `validate_judgement_json` — computes `passed` from threshold, not LLM opinion).

**Unit 4** — `app/orchestrator.py` (`Orchestrator` — sole owner of `BookRepo.transition()`; `start`, `run_judging`, `handle_revision` as the three pipeline phase methods; idempotent `_run_writing_round`; `_build_prior_critique` from best judgement of prior round), pipeline Celery tasks in `app/tasks.py` (`pipeline_start` → `pipeline_run_judging` → `pipeline_handle_revision` chain), `app/db/session.py` gains `get_task_session()` context manager.

---

## What is explicitly out of scope for v1

Multi-tenancy, user auth/login, billing, per-user API keys, KDP API automation, similarity matrix, Story DNA library, collaborative roles, Enterprise judge/writer builder UI. Do not build toward these; do not let the model gold-plate them in.
