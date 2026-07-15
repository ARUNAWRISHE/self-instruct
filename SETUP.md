# AIDEP — Autonomous Instruction Data Engineering Platform

> **The project has evolved from SELF-INSTRUCT into a full platform.**
> The original CLI pipeline (`next_gen_self_instruct/`) is preserved as a reference.
> The new platform lives in `aidep/`.

---

## What Is AIDEP?

AIDEP transforms human seed knowledge into structured, validated, and reusable instruction datasets for LLM alignment — autonomously.

```
Human Expert
      │
      ▼
Upload Seed Tasks (20–100)
      │
      ▼
Knowledge Repository
      │
      ▼
Generate New Instructions
      │
      ▼
Analyze Each Task (Task Intelligence)
      │
      ▼
Generate Training Examples
      │
      ▼
Validate Samples
      │
      ▼
Assign Quality Scores
      │
      ▼
Store Approved Samples
      │
      ▼
Export dataset.jsonl
```

---

## Project Structure

```
self-instruct/
├── aidep/                          # NEW — AIDEP Platform (FastAPI + PostgreSQL)
│   ├── api/
│   │   ├── deps.py                 # FastAPI dependency injection
│   │   └── routes/
│   │       ├── seed.py             # POST /seed, GET /seed
│   │       ├── instructions.py     # POST /instructions/generate, /analyze
│   │       └── pipeline.py         # POST /examples/generate, /validate, /quality
│   │                               #       /dataset/export, /pipeline/run
│   ├── core/
│   │   ├── config.py               # pydantic-settings + YAML + env vars
│   │   ├── llm.py                  # LiteLLM multi-provider client (+ mock mode)
│   │   ├── models.py               # Pydantic domain models
│   │   └── interfaces.py           # ABCs for all engines
│   ├── database/
│   │   ├── base.py                 # SQLAlchemy engine + session factory
│   │   ├── models.py               # ORM table models (11 tables)
│   │   └── repositories/           # Repository pattern (seed, instruction, example, dataset)
│   ├── engines/
│   │   ├── knowledge_engine/       # Phase 1 — Seed loading & Knowledge Foundation
│   │   ├── instruction_engine/     # Phase 2 — Instruction generation + domain expansion
│   │   ├── intelligence_engine/    # Phase 3 — Task Intelligence (type, domain, difficulty)
│   │   ├── example_engine/         # Phase 4 — Training example generation
│   │   ├── validation_engine/      # Phase 5 — Duplicate + semantic + structural validation
│   │   ├── quality_engine/         # Phase 6 — 8-dimension quality scoring
│   │   └── dataset_engine/         # Phase 7 — Export dataset.jsonl + quality report
│   ├── orchestrator/
│   │   └── pipeline.py             # Thin orchestrator (sequences engines, no business logic)
│   ├── schemas/                    # Pydantic API request/response schemas
│   ├── services/                   # Business logic services (called by routes)
│   └── main.py                     # FastAPI app factory + lifespan
├── next_gen_self_instruct/         # PRESERVED — original CLI pipeline
├── alembic/                        # Database migrations
│   └── versions/
│       └── 0001_initial_aidep_tables.py
├── alembic.ini
├── config.yaml                     # App configuration
├── docker-compose.yml              # PostgreSQL via Docker
├── requirements.txt                # All dependencies
└── .env.example                    # Environment variables template
```

---

## Quick Start

### Option A — No Database (Mock Mode, zero setup)

```bash
# Install dependencies
pip install -r requirements.txt

# Start the API server (mock LLM, no DB required)
python -m uvicorn aidep.main:app --reload

# Open interactive docs
start http://localhost:8000/docs
```

The server starts in mock mode — all LLM calls return realistic canned responses, and DB endpoints gracefully report a connection warning. **The API is fully usable for exploring the platform structure.**

---

### Option B — Full Mode (with PostgreSQL + Real LLM)

#### 1. Start PostgreSQL

```bash
docker-compose up -d
```

#### 2. Create a `.env` file

```bash
copy .env.example .env
```

Edit `.env`:
```env
DATABASE_URL=postgresql+psycopg2://aidep:aidep_secret@localhost:5432/aidep_db
LLM_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=sk-...
```

#### 3. Apply database migrations

```bash
python -m alembic upgrade head
```

#### 4. Start the server

```bash
python -m uvicorn aidep.main:app --reload
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/health` | Detailed health + DB status |
| `POST` | `/seed` | Upload a seed task |
| `POST` | `/seed/bulk` | Upload multiple seed tasks |
| `GET` | `/seed` | List all seed tasks |
| `POST` | `/instructions/generate` | Generate instruction candidates |
| `POST` | `/instructions/analyze` | Run Task Intelligence |
| `POST` | `/examples/generate` | Generate training examples |
| `POST` | `/validate` | Validate examples |
| `POST` | `/quality` | Score quality |
| `POST` | `/dataset/export` | Export `dataset.jsonl` |
| `POST` | `/pipeline/run` | Run full end-to-end pipeline |

Interactive docs: **http://localhost:8000/docs**

---

## LLM Configuration

AIDEP uses **LiteLLM** — you can use any provider:

| Provider | `LLM_MODEL` value |
|---|---|
| Mock (offline) | `mock` |
| OpenAI | `openai/gpt-4o-mini` |
| Gemini | `gemini/gemini-1.5-flash` |
| OpenRouter | `openrouter/openai/gpt-4o` |

Set in `config.yaml` or override with `LLM_MODEL` env var.

---

## Database Tables

| Table | Purpose |
|---|---|
| `seed_tasks` | Human-authored seed instructions |
| `prompt_templates` | Reusable LLM prompt templates |
| `domains` | Domain Library |
| `constraints` | Constraint Library |
| `taxonomy` | Task taxonomy hierarchy |
| `generated_instructions` | Machine-generated instruction candidates |
| `instruction_metadata` | Task Intelligence analysis results |
| `training_examples` | Generated training pairs |
| `validation_results` | Validation pass/fail records |
| `quality_scores` | Per-dimension quality scores |
| `datasets` | Dataset export metadata |

---

## Running the Legacy CLI Pipeline

The original `next_gen_self_instruct/` pipeline still works:

```bash
python -m next_gen_self_instruct.main --verbose
python -m unittest discover -s next_gen_self_instruct/tests
```

---

## Architecture

```
                   Human Expert
                        │
                        ▼
══════════════════════════════════════════════════
        Orchestrator (aidep/orchestrator/pipeline.py)
        Sequences engines — zero business logic
══════════════════════════════════════════════════
        │
        ├── KnowledgeEngine   Phase 1 — Seed Repository
        ├── InstructionEngine Phase 2 — Generate candidates
        ├── IntelligenceEngine Phase 3 — Task analysis
        ├── ExampleEngine     Phase 4 — Generate training pairs
        ├── ValidationEngine  Phase 5 — Duplicate + structural checks
        ├── QualityEngine     Phase 6 — 8-dimension scoring
        └── DatasetEngine     Phase 7 — Export dataset.jsonl
```
