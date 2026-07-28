# AIVOA — AI-Powered Customer Complaint Management System

An AI-assisted intake system for **pharmaceutical customer complaints**.

Published for internship evaluation only. Copyright © 2026 Chitrash; all rights reserved.
This repository has no open-source license. See [COPYRIGHT.md](COPYRIGHT.md).

A reporter describes the problem in their own words or uploads a complaint PDF. The intake
assistant extracts the factual details, says what it understood, explains unfamiliar terms, and
asks one focused follow-up question at a time until the complaint is ready to lodge. After it is
lodged, the internal QA workspace shows the LangGraph/Groq summary, completeness, preliminary
risk, possible root causes, investigation steps, duplicate hints, and CAPA suggestions.

> **The UI separates reporting from investigation.** A reporter sees only the conversation and
> factual complaint form. Preliminary risk and investigation guidance are shown after lodging,
> where a QA worker can review and change status, severity, and priority. Authentication and
> role enforcement are deliberately outside this prototype's scope.

### A note on the Groq model

The original technical requirement requested `gemma2-9b-it`. Groq retired that model before
implementation was completed, so this project keeps model selection environment-configurable and
uses a currently supported Groq production model. Defaults:

```
GROQ_MODEL=openai/gpt-oss-120b
GROQ_FALLBACK_MODEL=openai/gpt-oss-20b
```

Model defaults are centralized in `app/config.py` and can be overridden through the environment;
`app/llm/groq_client.py` is their only consumer, so changing a model is an `.env` edit and restart.
The backend pins the current stable Groq Python SDK (`groq==1.6.0`). Calls use the SDK's typed
Chat Completions responses, `APIError` hierarchy, `max_completion_tokens`, and the first-class
Qwen `reasoning_effort="none"` parameter.

Where a Pydantic model exists for the answer, its **strict JSON Schema is sent as
`response_format`** (Groq structured output); if a model rejects that, the client falls back to
`json_object` and then to prompt-only JSON, and the reply is validated by Pydantic either way.
Verified live against `openai/gpt-oss-120b`: schema mode is accepted and used on the first call.

### OCR data flow

`pypdf` reads PDFs that already contain selectable text. For a scanned PDF, `PyMuPDF` renders
each unreadable page as a normalized RGB image; it does **not** transcribe it. The existing Groq
API key sends those images to `qwen/qwen3.6-27b`, which performs the OCR in non-thinking JSON
mode. Pydantic validates the ordered page transcriptions, and LangGraph then processes the
recovered complaint text. PNG and JPG attachments use the same Qwen path.

The renderer caps the long edge at 2048 pixels, keeps the encoded request below 20 MB with
headroom, OCRs at most three scanned pages per file, and preserves native and OCR pages in their
original order. If vision is unavailable, the UI asks the reporter to retry or type the details;
typed text in the same message remains usable.

---

## Screenshots

### Normal-chat complaint intake

![Empty complaint-assistant chat](docs/screenshot-intake-empty.png)

### Groq Vision OCR with the factual form populated

![OCR complaint intake](docs/screenshot-intake-analysed.png)

### Lodged complaint list

![Complaint list](docs/screenshot-list.png)

### Internal QA workspace

![Internal QA investigation workspace](docs/screenshot-detail.png)

---

## Architecture

```mermaid
flowchart LR
    subgraph Browser["React + TypeScript (Vite)"]
        UI["Intake screen<br/>ComplaintForm + IntakePanel"]
        RTK["Redux Toolkit store<br/>complaints slice + thunks"]
        UI <--> RTK
    end

    subgraph API["FastAPI backend"]
        R["/api/complaints/* routes"]
        S["services<br/>documents · dialogue · completeness · risk · duplicates"]
        G["LangGraph StateGraphs<br/>intake + authoritative finalization"]
        L["Groq client<br/>text models + Qwen Vision OCR"]
        DB[("PostgreSQL<br/>SQLAlchemy + Alembic")]
        R --> S
        R --> G
        G --> L
        S --> DB
        R --> DB
    end

    RTK -- "axios · JSON / multipart" --> R
    L -- "HTTPS" --> Groq["Groq API<br/>text model + qwen/qwen3.6-27b"]
```

Full detail — request flow, node-by-node graph description, failure handling — is in
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Features

**Conversational intake**
- One familiar chat composer: paperclip, auto-growing text field, attachment chip, and send button
- Text-only, file-only, and combined messages; attachments also work on later turns
- PDF, PNG, JPG, and JPEG input; native PDF text via `pypdf`, scanned pages via Groq Qwen Vision
- The assistant repeats its understanding before moving on
- Replies are written by the model, not chosen from a template: every turn is decided
  deterministically first, then re-worded from a plain-language fact sheet. A greeting, an
  apology or an off-topic remark gets a human answer and the pending question is put back on the
  table — while a reply that states a number nobody supplied is discarded for the deterministic
  sentence, as is every reply when the provider is unavailable
- Missing information is collected with one focused counter-question at a time
- Explicit dialogue state remembers the pending question and useful partial answers across turns
- Invalid or ambiguous values receive a specific explanation instead of a repeated generic prompt
- Reporters can correct facts, ask why information is needed, or mark optional data unavailable
- Loop protection changes the wording and provides an example after repeated unclear answers
- Form-first and chat-first entry are interchangeable; chat continues from existing manual facts
  and never replaces them with a stale AI snapshot
- Extracted facts populate an editable complaint form with visible AI provenance
- A manually or conversationally completed complaint can be lodged once the minimum factual
  record is complete

**Internal QA workspace**
- Structured field extraction — constrained by a strict JSON Schema at generation time, then
  validated against the same Pydantic model
- Completeness score (deterministic) and the saved intake conversation
- Preliminary risk level, severity, priority, patient-safety and product-quality flags,
  written rationale and a confidence value
- Factual summary
- Possible root causes, initial investigation steps, preliminary CAPA suggestions
- Possible-duplicate detection against complaints already in the database
- Worker-editable complaint status, severity, and priority

**Record keeping**
- Human-readable complaint numbers (`CC-2026-0001`), allocated race-safely
- Full CRUD, search, pagination
- Atomic final QA handoff: edited form values are authoritative and all internal analysis is
  regenerated immediately before the complaint is persisted
- Complaint detail page showing the original input, full intake transcript, attachment
  transcriptions, extraction method, warnings, and refreshed AI output
- Grounded assistant: ask questions about one saved complaint, answered only from that record

**Safety**
- Deterministic rule engine acts as a *floor* — the model can raise a risk rating, never lower it
- Values that do not appear in the source document are discarded rather than trusted
- Document text is treated as untrusted data; prompt-injection instructions are ignored
- The system degrades to rule-based output instead of failing when the provider is unreachable

---

## Technology choices

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | React 18 + TypeScript + Vite | Fast dev loop, types across the API boundary |
| State | Redux Toolkit + `createAsyncThunk` | One place holds the form, the AI result and every loading/error flag; components stay dumb |
| Routing | React Router 7 | Three screens: intake, list, detail |
| HTTP | axios | One instance, one error-normalising helper |
| Styling | Hand-written CSS + Inter | Purpose-built interface without a third-party component library |
| Backend | FastAPI + Pydantic v2 | Validation and OpenAPI docs come from the same type definitions |
| ORM | SQLAlchemy 2.0 (typed `Mapped[...]`) | Explicit models, no magic |
| Migrations | Alembic | Reproducible schema, works on Postgres and SQLite |
| Database | PostgreSQL (JSONB for AI lists) | Relational record + flexible AI output in one row |
| AI orchestration | LangGraph `StateGraph` | Typed state, one concern per node, an explicit retry edge |
| LLM | Groq (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b`) | Fast and cheap; model names come from env vars only |
| Documents | pypdf + PyMuPDF + Groq Qwen Vision | pypdf reads native text, PyMuPDF renders scan pages, Qwen performs OCR |

---

## Local setup

### 0. Prerequisites
Python 3.11+, Node 18+, Docker (optional — see the SQLite note below), and a free
[Groq API key](https://console.groq.com/keys).

### 1. Database — PostgreSQL is the target

**PostgreSQL is the database this assignment implements against.** Start it with:

```bash
docker compose up -d db
```

On Windows, Docker Desktop must be running first (start it from the Start menu and wait for the
whale icon to stop animating), otherwise the command fails with
`failed to connect to the docker API at npipe:...`.

and use the URL that matches the compose credentials:

```
DATABASE_URL=postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa
```

Verified on PostgreSQL 16 (`postgres:16-alpine`): the Alembic migration creates the table with
`jsonb` columns, and the full chat intake → lodge → list → internal detail flow round-trips against
it.

**Fallback if you have no Docker/PostgreSQL:** set `DATABASE_URL=sqlite:///./aivoa.db` instead.
This is a convenience only — it is what the test suite uses so the tests need no
infrastructure. The models, the Alembic migration and every endpoint are identical; the JSON
columns become plain `JSON` instead of `JSONB`. Evaluate the project against PostgreSQL.

### 2. Backend

macOS / Linux:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your GROQ_API_KEY
alembic upgrade head
uvicorn app.main:app --reload
```

Windows (PowerShell):

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

API on <http://localhost:8000> · interactive docs on <http://localhost:8000/docs>

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env     # Windows: Copy-Item .env.example .env
npm run dev
```

App on <http://localhost:5173>

### 4. Sample PDFs (optional)

```bash
cd backend
python samples/make_sample_pdfs.py
```

---

## Environment variables

`backend/.env`

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | code default `sqlite:///./aivoa.db`; **`.env.example` ships the PostgreSQL URL** | Target: `postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa`. SQLite is the no-infrastructure fallback used by the tests |
| `GROQ_API_KEY` | *(empty)* | Required for AI analysis. Backend only — never sent to the browser |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Primary model |
| `GROQ_FALLBACK_MODEL` | `openai/gpt-oss-20b` | Tried if the primary model fails |
| `GROQ_VISION_MODEL` | `qwen/qwen3.6-27b` | Vision model used for scanned-page and image OCR |
| `GROQ_REPLY_MODEL` | `openai/gpt-oss-20b` | Wording of the intake assistant's replies only — never a decision and never a stored value. Deliberately the small model, so a cosmetic call cannot spend `GROQ_MODEL`'s token budget |
| `GROQ_REASONING_EFFORT` | `low` | Caps the private chain of thought of a reasoning model, which is billed against the same completion budget as the answer. Groq accepts only `low`, `medium` or `high`; leave it **empty** for a model with no reasoning mode |
| `FRONTEND_ORIGIN` | `http://localhost:5173,http://127.0.0.1:5173` | CORS allow-list (comma-separated) |
| `MAX_UPLOAD_SIZE_MB` | `5` | Upload limit |
| `MAX_INPUT_CHARS` | `40000` | Longer input is truncated with a warning |
| `MAX_EXTRACTION_RETRIES` | `1` | How many times the graph may run the repair node |

`frontend/.env`

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://localhost:8000/api` | Where the SPA calls the API |

Only `VITE_`-prefixed variables are exposed to the browser — that is exactly why the Groq key
lives on the backend and nowhere else.

---

## Database migrations

```bash
cd backend
alembic upgrade head                              # apply
alembic revision --autogenerate -m "add column"   # create a new migration after model changes
alembic downgrade -1                              # roll back one
```

`alembic.ini` holds **no** credentials: `alembic/env.py` reads `DATABASE_URL` through
`app.config`, so migrations always target the same database as the app.

---

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness + whether the LLM is configured |
| POST | `/api/complaints/analyze` | Start intake from PDF **or** text and run the AI workflow. **Saves nothing** |
| POST | `/api/complaints/intake/chat` | Interpret a stateful human-language turn and return validated fields, feedback, action, and next dialogue state |
| POST | `/api/complaints/intake/chat/attachment` | Continue the same stateful intake with text and/or another PDF/image |
| POST | `/api/complaints/finalize` | Regenerate QA analysis from final form facts and atomically lodge the complaint |
| POST | `/api/complaints` | Backward-compatible direct create endpoint |
| GET | `/api/complaints` | List with `limit`, `offset`, `search`, `status` |
| GET | `/api/complaints/{id}` | One complaint |
| PUT | `/api/complaints/{id}` | Partial update |
| DELETE | `/api/complaints/{id}` | Delete |
| POST | `/api/complaints/{id}/chat` | Question answered only from that complaint record |

Every error uses one shape:

```json
{ "error": { "code": "validation_error", "message": "…", "details": [] } }
```

Copy-paste examples: [API_EXAMPLES.md](API_EXAMPLES.md).

---

## LangGraph flow

```mermaid
flowchart TD
    START([START]) --> P[prepare_input]
    P --> E[extract_complaint_fields]
    E --> V{validate_extraction}
    V -- "invalid & retries left" --> RP[repair_extraction]
    RP --> V
    V -- "valid / out of retries" --> C[assess_completeness]
    C --> R[classify_risk]
    R --> S[generate_summary]
    S --> G[generate_recommendations]
    G --> A[assemble_result]
    A --> END([END])
```

| Node | File | Does |
| --- | --- | --- |
| `prepare_input` | `graph/nodes/prepare_input.py` | Normalise whitespace, enforce the size cap |
| `extract_complaint_fields` | `graph/nodes/extract.py` | Structured extraction call |
| `validate_extraction` | `graph/nodes/validate.py` | Pydantic validation **+** grounding check against the source text |
| `repair_extraction` | `graph/nodes/extract.py` | One retry with the validation error attached |
| `assess_completeness` | `graph/nodes/completeness_node.py` | Deterministic score, LLM-phrased follow-up questions |
| `classify_risk` | `graph/nodes/risk.py` | Rule engine + model opinion, merged with a safety floor |
| `generate_summary` | `graph/nodes/summary.py` | Factual 2–4 sentence summary |
| `generate_recommendations` | `graph/nodes/recommendations.py` | Root causes, investigation steps, CAPA ideas |
| `assemble_result` | `graph/nodes/assemble.py` | Fill severity/priority from the risk rating, add escalation warnings |

---

## AI limitations

- **It is not a QA decision.** Output is decision support. Severity, regulatory
  classification, recall decisions and CAPA approval stay with qualified personnel.
- **The model can be wrong.** Extraction is validated, but a mis-read strength or a mis-typed
  batch number can still slip through — that is why the form is editable and required.
- **OCR must be verified.** Scans can contain ambiguous characters, especially in batch numbers
  and dates. Every Qwen-derived document is marked “OCR used — please verify.”
- **The risk heuristic is intentionally cautious.** It uses a small negation-aware window for
  phrases such as "no patient injury" and otherwise prefers escalation over
  under-classification. It is still a heuristic and must be reviewed by QA.
- **Duplicate detection is a hint** — SQL filter plus text similarity, never a verdict.
- **No live streaming.** Progress wording is client-side while each API request completes.
- **English-language complaints** are what the prompts and heuristics were written for.

### What is stored is provenance, not a QMS audit trail

Each saved complaint keeps the original submitted text, the AI analysis produced at intake
(risk level, rationale, summary, completeness score, missing fields, root causes, CAPA
suggestions), and created/updated timestamps. That is a useful **provenance snapshot of the
AI-assisted intake result** — it lets a reviewer see what the model proposed next to what a
human approved.

It is deliberately **not** described as a pharmaceutical audit trail. A regulated QMS audit
trail (21 CFR Part 11 / EU GMP Annex 11 territory) additionally requires:

- authenticated user identity attached to every action;
- immutable, append-only, field-level change history;
- the old value **and** the new value for every change;
- secure, system-generated timestamps that a user cannot alter;
- a recorded reason for change;
- role-based access controls;
- electronic signatures where the process demands them;
- and the whole thing running on a validated, change-controlled system.

This project has none of those: it is single-user, has no authentication, and an update
overwrites the previous value in place. Adding them is the first item in *Future improvements*.

---

## Security considerations

- The Groq key lives only in `backend/.env`, is read through `app.config`, and never appears in
  any API response, log line or frontend bundle.
- Uploaded documents are **untrusted data**. Every system prompt contains an injection guard
  telling the model to ignore instructions found inside `<complaint>` tags.
- Input is capped (`MAX_INPUT_CHARS`, `MAX_UPLOAD_SIZE_MB`); oversized input is truncated or
  rejected with a clear message.
- Only PDF, PNG, JPG, and JPEG complaint attachments are accepted; extensions and decoded content
  are checked.
- CORS is an explicit allow-list, not `*`.
- All queries go through SQLAlchemy (parameterised) — no string-built SQL.
- Errors are logged by type; secrets are never logged.
- `.gitignore` excludes every `.env`, the SQLite file and `node_modules`.

---

## Sample inputs

`backend/samples/`

| File | Scenario | Expected preliminary risk |
| --- | --- | --- |
| `01_tablet_discoloration.txt` | Discoloured tablets returned by a pharmacy | high |
| `02_leaking_bottle.txt` | Leaking syrup bottles reported by a distributor | high |
| `03_incorrect_label_strength.txt` | 10 mg blisters inside a 5 mg carton | critical |
| `04_particulate_in_injectable.txt` | Visible particles in a sterile injectable | critical |
| `05_scanned_leaking_bottle.pdf` / `.jpg` | Image-only leaking-bottle complaint for Qwen Vision OCR | high |

`expected_fields.json` holds the reference answers. `python samples/make_sample_pdfs.py`
turns each `.txt` into a text-layer PDF for testing the upload path. All names, products,
batches and contacts are fictional.

`python samples/make_scanned_sample.py` regenerates the image-only OCR sample.

---

## Tests

```bash
cd backend
python -m pytest              # 116 tests, no network access — the Groq client is mocked
```

```bash
cd frontend
npm run lint
npm run build                 # tsc -b && vite build
```

Backend coverage: health, analyze validation (missing input, wrong file type, corrupt PDF,
oversized upload, provider not configured), the full analyze happy path, native/scanned/mixed
PDF extraction, PNG/JPG OCR, the three-page OCR cap, malformed vision JSON, CRUD + complaint
numbering + JSON columns, authoritative finalization, provider-down lodging, list/search, update,
delete, conversational updates, definition questions, invalid and partial dates, later-turn
completion, number words, corrections, unavailable information, repeated unclear answers,
persisted intake/internal QA fields, completeness scoring, negation-aware risk rules and floor
behaviour, JSON repair, schema hardening (null-ish strings, unparseable dates, unknown enums),
the graph's repair loop and retry ceiling, provider-down degradation, input truncation, and
duplicate detection.

The Groq client has its own suite (`tests/test_llm_client.py`) covering the strict-schema
builder, the `json_schema → json_object → prompt-only` downgrade and its per-model cache, and
the separation of failure kinds: a **provider** failure moves to the fallback model, while an
**unusable reply** raises `LLMOutputError` and is handed to the graph's repair node instead of
burning the fallback model on a shape problem. Its mocks use Groq 1.6's real typed
`ChatCompletion`, `BadRequestError`, `RateLimitError`, and `APITimeoutError` classes; it also
checks empty/no-choice responses, current request parameter names, client timeout/retries, and
Qwen JSON-mode fallback.

---

## Trade-offs

| Decision | Why | What it costs |
| --- | --- | --- |
| Completeness scored in Python, not by the LLM | Deterministic, testable, free | Cannot judge "is this description detailed enough?" |
| Rule engine as a floor under the model | A model that under-rates "sterility" is a patient-safety problem | Occasional over-escalation |
| Single request, no streaming | Much simpler frontend and backend | The user watches a spinner for a few seconds |
| Sequential graph nodes | Easy to read and explain | Slower than running summary/risk in parallel |
| `difflib` for duplicates | No vector DB, no embedding cost | Misses paraphrased duplicates |
| Handwritten CSS | No component-library weight | More CSS to maintain |
| Qwen Vision for OCR | One API key and an easy-to-explain path | Hosted availability and OCR accuracy require clear fallback/review |
| One `complaints` table | The assignment is one workflow | Attachments/comments would need more tables |

---

## Future improvements

1. Authentication plus a real audit trail: user identity, immutable field-level change history
   with old/new values, reason for change, access controls, e-signatures where required.
2. Stream node completion over SSE so the progress panel is live.
3. Add measured OCR accuracy tests for printed, skewed, low-contrast, and handwritten documents.
4. Trend analytics: complaints per batch/product over time, with recurrence alerts.
5. Embedding-based duplicate detection once the complaint volume justifies it.
6. Attachments (photographs of the defect) stored in object storage.
7. Export to the CAPA/QMS system, plus a printable complaint form.
8. Golden-set evaluation harness scoring extraction accuracy against `expected_fields.json`.
