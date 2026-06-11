---
name: project_reasoning_token_budgets
description: DeepSeek v4 models are reasoning models — token budgets must cover reasoning tokens; never route model choice by json_schema
metadata:
  type: project
---

Both `deepseek-v4-pro` (writer) and `deepseek-v4-flash` (judge/metadata) are **reasoning models**: `reasoning_tokens` count against `max_tokens` BEFORE any visible content. If the cap is too low the model spends the whole budget thinking, emits empty content, and the OpenAI SDK raises `LengthFinishReasonError` (`finish_reason=length`). This is deterministic, so Celery retries can't help — the book just exhausts backoff and goes RETIRED.

Caused the "every real run retires at revision" bug (fixed 2026-06-10): the writer started passing a `json_schema`, and `DeepSeekLLMProvider` was routing model + token-cap off `json_schema is not None` — so writer calls got the flash model AND the 1024-token judge cap. Round 1 squeaked by; revision (longer prompt → more reasoning) always blew the cap.

Rules going forward:
- Model selection is by the explicit `tier` arg on `LLMProvider.generate` ("high"=pro, "fast"=flash), NEVER by json_schema. See [[project_deepseek]].
- Keep generous token headroom above reasoning overhead: writer 8192, judge/metadata 4096 (was 1024). A reasoning burst can still occasionally hit the cap → it retries and recovers; that's fine, but never set caps near the reasoning floor.
