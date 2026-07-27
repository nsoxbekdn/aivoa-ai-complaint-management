# Demo script

Two recordings: Video 1 demonstrates the product; Video 2 follows one request through the code.

## Before recording

```bash
docker compose up -d db
cd backend
alembic upgrade head
uvicorn app.main:app --reload

cd frontend
npm run dev
```

- [ ] `http://localhost:8000/api/health` reports `"llm_configured": true`
- [ ] Keep `backend/samples/02_leaking_bottle.txt` ready for the text flow
- [ ] Keep `backend/samples/04_particulate_in_injectable.pdf` ready for the PDF flow
- [ ] Have at least one saved complaint so duplicate detection has data to compare
- [ ] Use a wide browser window at 100% zoom and hide notifications

---

# VIDEO 1 — Product demonstration (5–7 minutes)

### 0:00 — Problem and product boundary (30s)

> "This is AIVOA, an AI-assisted pharmaceutical customer complaint system. A customer should
> not need to understand a QMS form or terms such as batch number and expiry date. They should
> be able to describe the issue naturally, answer a few focused questions, and lodge it.
> Risk classification, root-cause ideas, investigation steps, and CAPA belong with the QA
> worker who investigates the lodged complaint, not with the person reporting it."

Point to the intake chat and factual form.

> "That separation is the core product decision in this version."

### 0:30 — Start in the reporter's own words (50s)

Paste or type:

> "Apollo Pharmacy received five 100 ml ClearCough bottles with loose caps and syrup leaking
> inside the carton. Nobody was injured and no adverse reaction was reported."

Click **Send to assistant**.

> "The first request runs the LangGraph workflow. The screen deliberately does not show its
> internal risk or CAPA output. The assistant instead says what it understood in plain language,
> fills only factual fields, and asks the most useful missing question."

Point out the populated product, quantity, customer, and complaint details.

### 1:20 — Counter-question, explanation, and correction (1 min 20s)

The assistant should ask for the batch number. Reply:

> "The batch is CC26045. Also, what does expiry date mean?"

> "This message does two jobs. It updates the batch field and answers the reporter's question
> without losing the intake flow. The assistant confirms the update, explains that expiry is
> the date until which the manufacturer guarantees the product when stored correctly, then asks
> one next question."

If useful, demonstrate a correction:

> "Correction: it was six bottles, not five."

> "A correction written naturally updates the same form. The reporter never has to translate
> their words into database field names."

### 2:40 — Ready to lodge (45s)

Answer the remaining required factual question(s), or edit the factual form directly.

> "Completeness is deterministic Python logic. The assistant collects only what is needed for a
> usable complaint record. Optional manufacturing details can remain unknown; they do not force
> the reporter to invent an answer."

Point out the ready state and click **Lodge complaint**.

> "Lodging is an explicit action. The conversation, original input, extracted fields, and the
> preliminary analysis are saved together as provenance."

### 3:25 — Complaint list and internal QA workspace (1 min 30s)

Open **Complaints**, then open the newly lodged record.

> "Now the audience changes. This is the internal QA workspace for someone investigating the
> lodged complaint. Status, severity, and priority are worker-editable."

Walk down the page:

- lodged factual record and original submission;
- intake conversation;
- completeness and AI summary;
- preliminary risk, confidence, safety/quality flags, and rationale;
- possible root causes and initial investigation steps;
- preliminary CAPA suggestions;
- possible duplicates;
- grounded question-and-answer assistant.

> "These are triage and investigation aids, not conclusions. CAPA remains preliminary until a
> qualified investigation approves it."

Ask:

> "Why was this classified as high risk?"

> "The saved-record assistant is grounded only in this complaint. If the record does not contain
> the answer, it says so."

### 4:55 — Groq Vision OCR and safety rule (55s)

Return to intake, choose **Start new complaint**, and upload
`04_particulate_in_injectable.pdf`.

> "This one is an image-only document. pypdf first finds that there is no usable text layer,
> PyMuPDF renders the page as a normalized image, and Qwen Vision on Groq performs the OCR.
> Pydantic validates the ordered transcription before LangGraph sees it. The reporter sees an
> OCR verification notice because batch numbers and dates must never be trusted silently."

Optionally demonstrate a wrong file type:

> "PDF, PNG, and JPG are accepted, including on later chat turns. If OCR is unavailable, typed
> text remains usable and the assistant clearly asks the reporter to retry or type the details."

### 5:50 — Close (20s)

> "The product removes form-filling friction for the reporter and gives QA a structured,
> traceable starting point. AI helps collect and organize the facts; qualified people still own
> severity, investigation, CAPA, and closure."

---

# VIDEO 2 — Code walkthrough (7–10 minutes)

### 0:00 — Repository map (30s)

> "`frontend` is React, TypeScript, Vite, and Redux Toolkit. `backend` is FastAPI, Pydantic,
> SQLAlchemy, Alembic, LangGraph, and Groq. PostgreSQL stores one complaint plus its intake and
> AI provenance."

### 0:30 — Frontend routes and state (1 min 20s)

Open `frontend/src/App.tsx`, `frontend/src/app/store.ts`, and
`frontend/src/features/complaints/complaintsSlice.ts`.

> "There are three screens: intake, list, and detail. One Redux slice holds the factual form,
> field provenance, the initial analysis, the intake transcript and ready state, saving, list,
> detail, and the separate saved-record QA chat."

Show `analyzeComplaint.fulfilled`:

> "The first analysis maps extracted factual fields into the form, then creates the assistant's
> 'what I understood' message and one follow-up. Internal risk output stays in state for
> persistence but is not rendered on intake."

Show `continueIntakeChat`:

> "Later turns send the current fields, recent transcript, and latest message. The reducer
> applies returned corrections and appends both chat messages."

### 1:50 — Intake UI and lodge gate (50s)

Open `ComplaintIntakePanel.tsx` and `ComplaintForm.tsx`.

> "The panel looks like a normal chat: paperclip on the left, auto-growing message area, send on
> the right, attachment chip, Enter to send and Shift+Enter for a newline. The form
> contains reporter facts only—no severity or priority. The lodge button requires an analysis
> and the server-calculated ready state."

### 2:40 — Frontend API boundary (30s)

Open `features/complaints/api.ts`.

> "Components never call Axios. One function starts analysis, another continues intake chat,
> and the rest cover CRUD and saved-record chat. All failures become a readable sentence."

### 3:10 — FastAPI routes (1 min 20s)

Open `backend/app/api/routes/complaints.py`.

> "`/analyze` accepts text, PDF, PNG, or JPG, validates the input, runs LangGraph in a threadpool, and adds
> duplicate candidates. It saves nothing."

Show `/intake/chat`:

> "This route uses a strict Pydantic response for field updates, fields to clear, a definition
> answer, and confirmation. Proposed values are grounded against the reporter's latest message.
> The backend merges them, recalculates completeness, filters internal-only questions such as
> severity and priority, and composes one friendly next turn."

> "The route intentionally cannot write risk, severity, priority, root cause, or CAPA."

Show `document_extract.py` and `complete_vision_json`:

> "pypdf reads selectable PDF text. PyMuPDF only renders scan pages; it is not the OCR engine.
> Qwen Vision performs transcription with the existing Groq key in non-thinking JSON mode.
> Images are RGB, capped at 2048 pixels, kept below the provider request limit, and limited to
> three scanned pages. Pydantic rejects malformed or empty OCR JSON."

### 4:30 — Prompts and structured output (1 min)

Open `backend/app/llm/prompts.py`, `backend/app/schemas/intake.py`, and
`backend/app/llm/groq_client.py`.

> "The intake prompt interprets only the latest message so an old value is not accidentally
> re-extracted over a correction. It supports null clears and definition questions, forbids
> guessing, and treats complaint text as untrusted data."

> "The Groq client requests strict JSON Schema where supported, downgrades response mode only
> when necessary, validates with Pydantic, and keeps all model names environment-configurable."

### 5:30 — LangGraph workflow (1 min)

Open `backend/app/graph/workflow.py` and `backend/app/graph/nodes/`.

> "The initial turn remains a real LangGraph workflow: prepare, extract, validate, deterministic
> completeness, risk, summary, recommendations, and assemble. Validation has an explicit,
> bounded repair edge. A node failure can degrade safely without losing all useful output."

> "There is also a finalization graph seeded from the edited form. It skips extraction and
> regenerates completeness, risk, summary, root causes, investigation, CAPA, and duplicates.
> That is why a manufacturing date typed after the first analysis is present in the saved
> summary and no longer appears as missing."

### 6:30 — Risk safety and negation (45s)

Open `backend/app/services/risk_rules.py`.

> "The deterministic classifier is a floor under the model. It also checks a small negation
> window so phrases such as 'no patient injury' and 'no adverse reaction' do not create a false
> patient-safety flag. Positive evidence still escalates."

### 7:15 — Persistence and QA detail (1 min)

Open `backend/app/models/complaint.py`,
`backend/alembic/versions/a42c7b7d91ef_add_internal_qa_fields.py`, and
`frontend/src/components/ComplaintDetail.tsx`.

> "The migration adds confidence, safety and quality flags, investigation steps, duplicate
> candidates, and the intake transcript. The internal detail screen reads those persisted
> values; it is not reconstructing them from temporary browser state."

> "Status, severity, and priority are editable here because they belong to the investigation
> workflow."

### 8:15 — Tests (45s)

Open `backend/tests/test_intake_chat.py`, `backend/tests/test_domain_logic.py`, and
`backend/tests/test_complaints_crud.py`.

> "There are 74 backend tests with no live network dependency. The new tests cover chat field
> updates, terminology questions, negated versus real safety signals, and persistence of every
> internal QA field and transcript. Frontend lint and production build are also part of the
> preflight."

### 9:00 — Honest limitation / improvement answer (45s)

> "The critical production gap is authorization and a regulated audit trail. Today the UI
> separates reporter and QA workflows, but it does not enforce identity or roles. Before real
> pharmaceutical use I would add authenticated reporter, QA, and approver roles; append-only
> old/new field history with reasons; electronic signatures; and validated deployment controls.
> I left that boundary explicit instead of pretending a take-home login is 21 CFR Part 11
> compliance."

> "Other next steps are streaming and measured OCR/extraction evaluation, but authorization
> and auditability are the first production requirement."
