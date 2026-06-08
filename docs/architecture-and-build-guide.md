# AI Book Publishing Platform — Architecture Spec & Build Guide

**Version:** v1 (single-user)
**Scope of this document:** A reference architecture you keep open while building, plus a sequenced set of build units you feed to a coding model one at a time.
**Confirmed constraints driving this design:**

- Single-user tool first; multi-tenant SaaS is a *later refactor*, not a v1 concern.
- Your API keys, your cost. No per-user key vaulting, billing, or quota system in v1.
- Quality over volume. Few high-quality books first.
- Export to KDP-ready files. Publishing to Amazon is a **manual human step** (no KDP API exists).
- Image consistency uses a **pluggable provider** (Leonardo character-reference for v1, with a clean seam to swap in a trained character model later). Nothing in the pipeline hardcodes Leonardo.

---

## How to use this document

This is split into two halves, and they serve different purposes:

**Part A — Architecture Spec.** Your map. Read it to understand the system. Do **not** paste it wholesale into a coding model — it's too big and they'll lose coherence and invent decisions. Pull from it as needed.

**Part B — Build Sequence.** Your execution plan. The project is broken into ordered build units. Each unit has: a goal, what to hand the model, a prompt scaffold you can adapt, and a "definition of done" you verify before moving to the next unit. You build one unit, confirm it works, commit, then start the next. This keeps the coding model's job small and verifiable at every step.

**The core working loop with a coding model:**

1. Open this doc. Find the next build unit.
2. Give the model: (a) the relevant Architecture Spec sections only, (b) the build unit's prompt scaffold, (c) the current state of the repo (or let it read the files).
3. Let it build *only that unit*. Resist scope creep — if it starts building ahead, stop it.
4. Run the unit's verification steps. If they pass, commit. If not, iterate on that unit only.
5. Repeat.

A note on the open model question (DeepSeek vs. a cheaper writer model): the design treats the LLM behind an interface too, so this is a config swap, not a rewrite. Pick one to start; switch later with data. Model names, pricing, and API shapes change often — verify the current model and endpoint before you wire it in rather than trusting any name written here.

---

# PART A — ARCHITECTURE SPEC

## 1. System overview

The system is a **pipeline** that takes a story brief and walks it through stages until it produces KDP-ready export files. A human approves at defined gates. The whole thing is a state machine: each book moves through ordered stages, and each stage is a unit of work that either completes, needs a human, or fails.

```
Story Brief
   │
   ▼
[Outline]  →  [Writer agents ×3 compete]  →  [Judge scores all 3]
                          ▲                          │
                          │   (feedback, ≤N rounds)   │
                          └──────────────────────────┘
                                                      │ best passes threshold
                                                      ▼
                                              [Human Approval Gate]
                                                      │ approved
                                                      ▼
                                        [Image Generation (provider)]
                                                      │
                                                      ▼
                                              [Cover Generation]
                                                      │
                                                      ▼
                                          [Metadata / SEO draft]
                                                      │
                                                      ▼
                                        [Export: KDP PDF + others]
                                                      │
                                                      ▼
                                   Human uploads to KDP manually (out of system)
```

### Component map

- **API layer (FastAPI).** The single front door. Serves the dashboard's data, accepts commands ("approve variant 2", "start a book", "rewrite this paragraph"), and emits progress over WebSockets.
- **Orchestrator.** Owns the state machine. Decides what stage a book is in and what task to enqueue next. This is the brain; keep its logic out of the agents themselves.
- **Task workers (Celery).** Run the slow work — LLM calls, image generation, export rendering — off the request path. Redis is the broker.
- **Agent services.** `WriterAgent`, `JudgeAgent`. Pure functions over (prompt, context) → structured output. They do not know about the database or the queue; the orchestrator calls them and persists results.
- **Provider interfaces.** `LLMProvider` and `ImageProvider`. Thin abstractions so the model vendor and image vendor are config, not structure.
- **Persistence (PostgreSQL).** Source of truth for books, stages, story versions, scores, images, audit log.
- **Object storage (S3, or local disk in dev).** Image files, export artifacts, the character reference asset(s).
- **Frontend (Next.js + React + Tailwind).** Kanban board, story editor, approval gates, performance views. Talks only to the API.

### A guiding principle

**The orchestrator owns sequencing; agents own thinking; providers own vendors; the DB owns truth.** If you keep those four responsibilities from leaking into each other, the multi-tenant refactor later is additive (add a tenant_id and an auth layer) rather than a teardown.

---

## 2. Data model (PostgreSQL)

This is the heart of the system. Get this right and everything else has a place to live. Tables below are conceptual; let the coding model write the actual migrations.

### `books`
The top-level project. One row per book.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| title | text | working title, may change |
| template_id | uuid FK | which template (ADHD picture book, etc.) |
| status | text | current pipeline stage (see state machine) |
| brief | jsonb | the full story brief that kicked it off |
| created_at / updated_at | timestamptz | |

### `templates`
A template is a *parameter set*, per your doc — not a separate system.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text | "ADHD Picture Book (4-8)" |
| writer_config | jsonb | which methods, prompt fragments, word-count targets |
| judge_config | jsonb | criteria, weights, threshold, max rounds |
| image_config | jsonb | art style, character age, provider params |
| export_config | jsonb | page size, bleed, format targets |

### `story_versions`
Every iteration of story text, ever. Append-only. This gives you the git-like history and rollback your doc asks for.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| book_id | uuid FK | |
| round | int | iteration number |
| method | text | "three_act", "sensory_first", etc. |
| writer_agent | text | which agent/config produced it |
| outline | jsonb | structured outline |
| text | text | full story text |
| parent_version_id | uuid FK null | what this was a rewrite of |
| created_at | timestamptz | |

### `judgements`
The judge's scoring of a story version. Separate from the version so a version can be re-judged.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| story_version_id | uuid FK | |
| scores | jsonb | per-dimension scores (emotional authenticity, representation, pacing, age-fit, uniqueness) |
| weighted_total | numeric | |
| passed | bool | cleared threshold? |
| critique | jsonb | structured feedback for rewrite |
| created_at | timestamptz | |

### `images`
Generated illustrations and covers.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| book_id | uuid FK | |
| scene_index | int | which page/scene |
| kind | text | "interior" or "cover" |
| provider | text | which ImageProvider produced it |
| character_ref_id | uuid FK null | which character asset was referenced |
| storage_key | text | S3 key / local path |
| params | jsonb | seed, prompt, provider settings (reproducibility) |
| status | text | pending / done / failed |
| created_at | timestamptz | |

### `character_assets`
The "golden character" — abstracted so it can be a reference image set *or* a trained model handle later.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text | |
| kind | text | "reference_images" \| "trained_model" |
| storage_keys | jsonb | image keys, or model identifier |
| created_at | timestamptz | locked after book 1 per your plan |

### `audit_log`
Who/what changed what, when, why. Critical for later resale/team use; cheap to add now.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| book_id | uuid FK null | |
| actor | text | "human" or agent/system name |
| action | text | "approved_variant", "rewrote_paragraph", "stage_transition" |
| detail | jsonb | before/after, ids, reason |
| created_at | timestamptz | |

### `similarity_scores` (can defer past MVP)
Pairwise similarity between books for diversity enforcement.

| Column | Type | Notes |
|---|---|---|
| book_id_a / book_id_b | uuid FK | |
| score | numeric | 0–1 |
| computed_at | timestamptz | |

---

## 3. The pipeline state machine

Each book has a `status` that is exactly one of these stages. The orchestrator is the only thing allowed to transition it, and every transition writes an `audit_log` row.

```
DRAFT_BRIEF
  → OUTLINING
  → WRITING            (writer agents producing variants)
  → JUDGING            (judge scoring variants)
  → REVISION           (failed threshold; feedback → back to WRITING)   [loop, capped]
  → AWAITING_APPROVAL  (passed threshold; human gate)  ── human rejects ──┐
  → APPROVED                                                              │
  → GENERATING_IMAGES                                                     │
  → GENERATING_COVER                                                      │
  → DRAFTING_METADATA                                                     │
  → EXPORTING                                                             │
  → EXPORT_READY                                                          │
  → (manual KDP upload, marked DONE by human)                            │
                                                                          │
  RETIRED  ←── exceeded max revision rounds, or human kills it ──────────┘
```

**Status colors map to the doc's Kanban:**
- Green = a stage that completed and auto-advanced.
- Yellow = a stage actively running in a worker.
- Blue = `AWAITING_APPROVAL` (or any human-input stage).
- Red = a failed stage or `RETIRED`.

Keep the stage list in **one place** (an enum + a transition table). The frontend reads it; the orchestrator enforces it. Never let stage strings get hardcoded in three different files.

---

## 4. The writer/judge loop (the core IP)

This is where quality is won or lost. Structure it carefully.

**One round:**

1. Orchestrator reads the book's brief + template `writer_config` + (if this is a revision) the last judge critique.
2. It dispatches **N writer tasks in parallel** (Celery), one per method (three-act, sensory-first, problem-solution, hero's-journey — whichever the template enables). Each calls `WriterAgent.write(brief, method, prior_critique)` → outline + text. Each result is saved as a `story_versions` row.
3. When all writers finish, orchestrator dispatches **one judge task** that scores every new version → `judgements` rows.
4. Orchestrator picks the top `weighted_total`.
   - If it cleared the threshold → transition to `AWAITING_APPROVAL`.
   - Else, if rounds remaining → attach critique, transition back to `WRITING` (a new round).
   - Else → `RETIRED`.

**Design rules that matter:**

- **The judge must produce *structured* output**, not prose. Define a strict JSON schema (each dimension 0–10 + a short critique string per dimension + an overall verdict). Validate it on the way out; if the model returns malformed JSON, retry the call, don't crash the pipeline. This is the #1 source of flakiness in judge/writer systems.
- **Writers rewrite from critique, not from scratch** (your doc is right about this). Pass the prior version + the judge's specific critique into the next round's writer call.
- **Correlated-blindspot risk:** writer and judge being the same base model can mean the judge is blind to the same things the writer is. Mitigate by (a) giving the judge a *very* different, rubric-heavy system prompt grounded in real review data, and (b) leaving the door open to use a different model for the judge. The provider interface makes that a config change.
- **The judge prompt is the "super prompt" your doc flags as mission-critical.** Treat it as a versioned artifact (store prompt versions; record which version produced which judgement). You'll iterate on it constantly against real Amazon performance.

---

## 5. Provider interfaces (the anti-vendor-lock seam)

Two thin interfaces. Everything else depends on these, never on a vendor SDK directly.

**`LLMProvider`**
```
generate(system: str, messages: list, *, json_schema=None) -> Response
```
- One implementation for your chosen model (e.g. DeepSeek). Add others later.
- Handles retries, timeout, and (when `json_schema` given) validates/coerces structured output.
- No agent ever imports a vendor SDK. They take an `LLMProvider`.

**`ImageProvider`**
```
generate_scene(scene_prompt: str, character_ref: CharacterRef, params: dict) -> ImageResult
```
- v1 implementation: Leonardo, using its character-reference / image-guidance feature.
- `CharacterRef` is an abstraction over "a set of reference images" OR "a trained model handle." The pipeline passes a `CharacterRef`; it does not know or care which kind it is.
- Later: a `TrainedCharacterImageProvider` (LoRA or equivalent) implements the same method. Swapping is a config change + one new class.

**Why this matters for you specifically:** you flagged uncertainty on both the writer model choice and on Leonardo. Both uncertainties are absorbed by these two interfaces. You are never betting the architecture on a vendor.

> Reality check to keep in mind, not to build around: text-to-image character consistency is imperfect across pose/angle/expression changes. Expect to start with Leonardo character-reference, and plan to graduate your flagship character to a trained model when you commit to it. Verify the current Leonardo feature set and commercial-use terms before relying on them — these change, and the books are for children and possibly resale.

---

## 6. API surface (FastAPI)

Keep it small and resource-oriented. Illustrative, not exhaustive:

- `POST /books` — create a book from a brief.
- `GET /books` / `GET /books/{id}` — board data, book detail.
- `GET /books/{id}/versions` — story version history.
- `POST /books/{id}/approve` — approve current best variant (advances the gate).
- `POST /books/{id}/reject` — reject; send back with optional note.
- `POST /books/{id}/retry` — re-run a failed stage.
- `POST /books/{id}/paragraphs/rewrite` — inline editor: rewrite a paragraph with an instruction.
- `GET /templates` / `POST /templates` — template CRUD.
- `WS /books/{id}/stream` — live stage/progress events for that book.

Commands return immediately and enqueue work; the WebSocket carries progress. Don't block HTTP requests on LLM/image calls.

---

## 7. Orchestration & real-time

- **Celery + Redis** for the work queue. Writer tasks fan out in parallel; a judge task depends on their completion (use a chord/group, or have the orchestrator poll completion — simpler is fine for v1).
- **Progress to the UI:** workers publish events (stage started, variant N done, image 4 of 12) to a Redis pub/sub channel; the FastAPI WebSocket endpoint subscribes and forwards to the browser. This keeps workers decoupled from the web layer.
- **Idempotency:** every task should be safe to retry. Tie results to `(book_id, round, method)` so a re-run overwrites cleanly rather than duplicating versions.

---

## 8. Export subsystem

- **KDP-ready PDF** is the real deliverable boundary. Correct trim size, bleed, and resolution for KDP's picture-book specs. Verify current KDP specs at build time.
- Also emit: Word doc (manual editing), Markdown, raw text (Canva import), and an organized image-asset folder.
- Export is a worker task that reads the approved version + images and renders artifacts to S3/disk, then flips the book to `EXPORT_READY`.
- **Publishing is manual.** The system's job ends at "files ready"; you upload to KDP yourself. Don't let the coding model try to automate Amazon — it's against their terms and it's brittle.

---

## 9. Infrastructure

- **Dev:** docker-compose with Postgres, Redis, the API, a worker, and local-disk storage standing in for S3. You want the whole thing to come up with one command.
- **Prod (later):** the AWS mapping in your doc is fine (RDS, S3, workers on ECS/Lambda). Don't build for prod until v1 runs locally end to end.
- **Secrets:** your API keys go in environment variables / a `.env` that is gitignored. Never commit keys. (This is the seed of the later multi-tenant key-vault, but for now it's just your env.)
- **Config over hardcoding:** model names, provider choices, thresholds, round caps — all config, not literals in code.

---

## 10. What is deliberately NOT in v1

So the coding model doesn't gold-plate: no multi-tenancy, no auth/login, no billing, no per-user quotas, no Enterprise custom-judge-builder UI, no collaborative/role-based mode, no KDP automation, no similarity matrix (defer), no Story DNA library (defer). These are real features from your strategy doc — they're just later. Each was designed *around* (clean seams) but not *built*.

---

# PART B — BUILD SEQUENCE

Build in this order. Each unit ends in a working, committable state. Don't start a unit until the previous one's "Done when" checks pass. For each unit, give the coding model only the Spec sections listed under "Hand it."

### Unit 0 — Repo & dev environment
**Goal:** One command brings up Postgres, Redis, an empty FastAPI app, and a Celery worker.
**Hand it:** Spec §1, §9.
**Prompt scaffold:**
> Set up a Python project (FastAPI + Celery + Redis + PostgreSQL) with docker-compose for local dev. Use SQLAlchemy + Alembic for migrations. Provide a `make up` / `docker-compose up` that starts API, worker, db, redis. Add a `/health` endpoint and a trivial Celery task I can trigger to confirm the worker runs. Local disk stands in for S3 via a storage interface with a `LocalStorage` implementation. Keep all config in env vars with a `.env.example`. No business logic yet.
**Done when:** stack comes up clean; `/health` returns OK; the trivial task runs on the worker; migrations apply.

### Unit 1 — Data model & migrations
**Goal:** All core tables exist with relationships and an append-only `story_versions` + `audit_log`.
**Hand it:** Spec §2, §3 (for the status enum).
**Prompt scaffold:**
> Implement these tables as SQLAlchemy models + Alembic migrations: books, templates, story_versions, judgements, images, character_assets, audit_log. [paste the §2 tables]. Make story_versions and audit_log append-only by convention (no update/delete in the repo layer). Add a Python enum for book status matching the state machine in [paste §3], and a single transition table that defines legal transitions. Seed one template row for "ADHD Picture Book (4-8)" with placeholder config. Write repository functions for create/read; no orchestration yet.
**Done when:** migrations apply; you can create a book + template via a script/REPL; illegal status transitions are rejected by the transition table; an audit row is written on transition.

### Unit 2 — Provider interfaces (with fakes)
**Goal:** `LLMProvider` and `ImageProvider` interfaces, plus **fake** implementations so the whole pipeline can run offline before you spend a cent on APIs.
**Hand it:** Spec §5.
**Prompt scaffold:**
> Define `LLMProvider.generate(system, messages, json_schema=None)` and `ImageProvider.generate_scene(scene_prompt, character_ref, params)` as abstract interfaces. Implement `FakeLLMProvider` (returns canned but schema-valid JSON, deterministic by seed) and `FakeImageProvider` (writes a placeholder PNG to storage). Wire provider selection through config so I can switch real/fake via env. Include a `CharacterRef` abstraction that can represent either reference images or a trained-model handle.
**Done when:** you can call both fakes from a test; fake LLM returns schema-valid structured output; fake image writes a file via the storage interface.

### Unit 3 — Writer & Judge agents
**Goal:** The two agents as pure functions over a provider, with strict structured I/O.
**Hand it:** Spec §4, §5.
**Prompt scaffold:**
> Implement `WriterAgent.write(brief, method, prior_critique=None)` and `JudgeAgent.judge(story_versions, criteria)`. They take an `LLMProvider` (inject it). Define a strict JSON schema for the judge output: per-dimension score 0–10 (emotional_authenticity, representation_quality, pacing, age_fit, uniqueness), a per-dimension critique string, weighted_total, and pass/fail vs a threshold. Validate the model output against the schema; on invalid JSON, retry up to 3 times then raise. Writers must accept and incorporate prior_critique. Store the judge system prompt as a versioned string constant. Use the FakeLLMProvider in tests.
**Done when:** with fakes, a writer produces a saved `story_versions` row; the judge produces a schema-valid `judgements` row; malformed output triggers retry, not a crash.

### Unit 4 — Orchestrator & the writer/judge loop
**Goal:** The state machine drives a full brief→approval-gate cycle, offline, on fakes.
**Hand it:** Spec §3, §4, §7.
**Prompt scaffold:**
> Implement the orchestrator that owns book status transitions per the transition table. Implement the loop: from WRITING, fan out N parallel Celery writer tasks (one per enabled method), then run one judge task over the new versions, pick the top weighted_total, and either advance to AWAITING_APPROVAL (passed) or loop back to WRITING with critique (failed), capped at max_rounds from template config, else RETIRED. Every transition writes audit_log. Make all tasks idempotent keyed on (book_id, round, method). Use fakes so this runs with no external APIs.
**Done when:** kicking off a book runs writers→judge→loop and lands in AWAITING_APPROVAL or RETIRED, entirely on fakes; re-running a task doesn't duplicate versions; audit log shows the full trail.

### Unit 5 — API + WebSocket progress
**Goal:** Drive the pipeline over HTTP and watch it live.
**Hand it:** Spec §6, §7.
**Prompt scaffold:**
> Add FastAPI endpoints: POST /books (create from brief, starts pipeline), GET /books, GET /books/{id}, GET /books/{id}/versions, POST /books/{id}/approve, POST /books/{id}/reject, POST /books/{id}/retry. Add WS /books/{id}/stream. Workers publish progress events to a Redis pub/sub channel; the WebSocket subscribes and forwards them. Commands enqueue work and return immediately. Approve/reject advance or revert the human gate via the orchestrator.
**Done when:** you can POST a brief via curl, watch stage events over the WebSocket, and approve the gate via an endpoint — all on fakes.

### Unit 6 — Real LLM provider
**Goal:** Swap the fake LLM for your real model and tune the judge prompt.
**Hand it:** Spec §4, §5; plus go verify the current model name/endpoint/pricing yourself first.
**Prompt scaffold:**
> Implement a real `LLMProvider` for [model you verified], honoring the same interface and JSON-schema validation/retry as the fake. Make it selectable by env. Do not change agent or orchestrator code. Add a small script to run one real book end-to-end to AWAITING_APPROVAL and print all variants + judge scores so I can evaluate quality.
**Done when:** a real brief produces real variants and real structured judge scores; switching back to fakes still works; no agent/orchestrator code changed.

### Unit 7 — Real image provider + character ref
**Goal:** Real illustrations with character-reference consistency.
**Hand it:** Spec §5, §8 (image parts); verify current Leonardo features/terms yourself first.
**Prompt scaffold:**
> Implement a real `ImageProvider` for Leonardo using its character-reference/image-guidance feature, same interface as the fake. Implement `character_assets` of kind "reference_images": store the locked reference set in storage and pass it as a `CharacterRef`. Add the GENERATING_IMAGES stage: from the approved version, derive scene prompts, batch-generate interior images, persist `images` rows with seed/params for reproducibility, and emit progress events. Keep a clean path for a future "trained_model" CharacterRef without changing the pipeline.
**Done when:** an approved book generates a consistent-character image set into storage; image rows record reproducible params; progress shows "X of Y".

### Unit 8 — Cover, metadata, export
**Goal:** Produce the KDP-ready file bundle.
**Hand it:** Spec §8.
**Prompt scaffold:**
> Add GENERATING_COVER, DRAFTING_METADATA, and EXPORTING stages. Cover uses the ImageProvider. Metadata uses the LLMProvider to draft title/description/keywords (human-editable). Export renders: KDP-ready PDF (verify current KDP picture-book trim/bleed/resolution specs), Word, Markdown, raw text, and an organized image-asset folder, all to storage. Flip to EXPORT_READY when done. Publishing to KDP is manual and out of scope.
**Done when:** an approved book produces a downloadable file bundle; the PDF meets the KDP specs you verified; book reaches EXPORT_READY.

### Unit 9 — Frontend: Kanban + approval + editor
**Goal:** The dashboard you actually operate from.
**Hand it:** Spec §1, §3 (colors), §6.
**Prompt scaffold:**
> Build a Next.js + React + Tailwind dashboard talking only to the API. Views: (1) Kanban board of books colored by stage [green/yellow/blue/red per §3], with a priority queue at top showing the single highest-priority human action; (2) book detail showing the 3 variants with judge score breakdowns and an Approve/Reject control on the gate; (3) inline story editor — click a paragraph, type an instruction, call POST /paragraphs/rewrite, show before/after. Subscribe to the WebSocket for live progress. Keep it clean and power-user friendly.
**Done when:** you can run a book start-to-export entirely from the browser, approve at the gate, and reword a paragraph inline.

### Later units (designed-for, not built now)
Similarity matrix & diversity scoring · Story DNA library · multi-tenancy + auth · billing & per-user keys · Enterprise custom judge/writer builders · collaborative roles. Each slots onto the existing seams without a rewrite.

---

## Two things to hold onto

**First:** the single most valuable, hardest-to-copy asset here is the judge prompt grounded in real Amazon review language — exactly as your strategy doc says. The architecture deliberately makes it a versioned, swappable artifact so you can iterate on it forever against real sales data. Spend disproportionate time there.

**Second:** the discipline that makes this whole thing survive contact with a coding model is *one unit at a time, verified before the next.* The fakes in Units 2–5 are the key trick — they let you build and prove the entire pipeline's logic for free, before any API spend, and they stay as your test backbone forever.
