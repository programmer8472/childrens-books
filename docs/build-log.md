# Build Log — Completed Units

What was built in each completed unit. See [CLAUDE.md](../CLAUDE.md) for the build sequence table and unit goals.

---

**Unit 0** — `docker-compose.yml` (Postgres 16 on 5433, Redis 7, API on 8001, Celery worker), `app/main.py` (`GET /health`, `POST /health/worker`), `app/tasks.py` (`ping` task).

**Unit 1** — `app/db/enums.py` (`BookStatus` + `LEGAL_TRANSITIONS` + `assert_legal_transition`), `app/db/models.py` (all 6 tables), `app/db/repos/` (one class per table), `migrations/versions/0002_schema.py`.

**Unit 2** — `app/providers/base.py` (`LLMProvider`, `ImageProvider` ABCs; `LLMResponse`, `CharacterRef`, `ImageResult` dataclasses), `app/providers/fake_llm.py` (`FakeLLMProvider` — injectable response queue, records calls), `app/providers/fake_image.py` (`FakeImageProvider`), `app/providers/factory.py` (`get_llm_provider` / `get_image_provider` driven by `Settings.llm_provider` / `Settings.image_provider`, both default to `"fake"`).

**Unit 3** — `app/agents/writer.py` (`WriterAgent.write(brief, method, prior_critique)` — 4 named methods, revision vs. fresh system prompts), `app/agents/judge.py` (`JudgeAgent.judge(story_versions, criteria)` — one LLM call per version, 3-retry loop with error fed back to LLM, `PROMPT_VERSION = "v1"`), `app/agents/base.py` (`JudgementResult`, `validate_judgement_json` — computes `passed` from threshold, not LLM opinion).

**Unit 4** — `app/orchestrator.py` (`Orchestrator` — sole owner of `BookRepo.transition()`; `start`, `run_judging`, `handle_revision` as the three pipeline phase methods; idempotent `_run_writing_round`; `_build_prior_critique` from best judgement of prior round), pipeline Celery tasks in `app/tasks.py` (`pipeline_start` → `pipeline_run_judging` → `pipeline_handle_revision` chain), `app/db/session.py` gains `get_task_session()` context manager.
