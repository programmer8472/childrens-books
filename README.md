# Children's Book Pipeline

AI-powered children's book publishing pipeline. Submit a story brief; competing writer agents draft chapters, a judge scores and loops until quality passes, then the system generates illustrations and KDP-ready export files. Human approves at one defined gate; the rest is automated.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker + Docker Compose | any recent | API, worker, Postgres, Redis |
| Node.js | 18+ | Next.js frontend |
| Python + [uv](https://docs.astral.sh/uv/) | 3.11+ | running tests locally |

---

## First-time setup

### 1. Backend environment

```bash
cp .env.example .env
```

Edit `.env` and set the providers you want:

```dotenv
# Use real LLM generation (needs a DeepSeek key)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-key-here

# Use labeled placeholder images while Leonardo key is pending
IMAGE_PROVIDER=placeholder
```

Leave `LLM_PROVIDER=fake` and `IMAGE_PROVIDER=fake` if you only want to smoke-test plumbing without API calls.

### 2. Frontend environment

```bash
cp frontend/.env.local.example frontend/.env.local
```

The defaults point at `localhost:8001` (where the API will listen) and need no changes for local dev.

### 3. Install frontend dependencies

```bash
cd frontend && npm install
```

---

## Running the app

### Start the backend (API + worker + DB + Redis)

```bash
make up
```

This builds images and starts four containers. On first run, wait for all four to report healthy, then in a second terminal run the migrations:

```bash
make migrate
```

You only need `make migrate` once (and again after any new migration is added). The API is now live at **http://localhost:8001**. Interactive docs are at **http://localhost:8001/docs**.

### Start the frontend

```bash
cd frontend && npm run dev
```

Open **http://localhost:3000** — the Kanban dashboard loads immediately.

---

## Using the app

1. Click **New Book** on the dashboard and fill in the brief (title, characters, setting, age range, theme).
2. The pipeline advances automatically: writing → judging → revision loops → **Awaiting Approval** (highlighted in blue at the top of the board).
3. Open the book detail, review story variants with judge scores, then **Approve** or **Reject** (rejection re-enters the loop).
4. After approval the pipeline continues automatically: image generation → cover → metadata draft → export.
5. When the book reaches **Export Ready**, download the KDP package (interior PDF, cover PDF, Word, Markdown, plain text, images) from the detail page.

---

## Other commands

```bash
make down        # stop and remove containers
make logs        # tail all container logs
make test        # run the full test suite (229 tests)
make test-one T=tests/test_unit9_api.py::test_name   # run one test
```

---

## Status

| Unit | Goal | State |
|------|------|-------|
| 0 | Docker stack, /health, trivial worker task | Done |
| 1 | DB tables, migrations, status enum, repo layer | Done |
| 2 | LLMProvider / ImageProvider interfaces + Fake impls | Done |
| 3 | WriterAgent + JudgeAgent | Done |
| 4 | Orchestrator + writer/judge loop | Done |
| 5 | FastAPI endpoints + WebSocket progress | Done |
| 6 | Real LLM provider (DeepSeek) | Done |
| 7 | PlaceholderImageProvider (working); LeonardoImageProvider (pending API key — swap `IMAGE_PROVIDER=leonardo`, no other changes) | Partial |
| 8 | Compositor (PDF, DOCX, Markdown), MetadataAgent, export API | Done |
| 9 | Next.js frontend: Kanban, detail page, paragraph editor, metadata editor, export downloads | Done |
