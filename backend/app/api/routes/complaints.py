"""Complaint endpoints: AI analysis (no write) and CRUD (writes)."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.graph.workflow import run_analysis, run_final_analysis
from app.llm.groq_client import LLMError, complete_json, complete_text
from app.llm.prompts import CHAT_SYSTEM, INTAKE_CHAT_SYSTEM
from app.schemas.analysis import ComplaintAnalysisResponse, ExtractedComplaintFields, SourceDocument
from app.schemas.complaint import (
    ChatRequest,
    ChatResponse,
    ComplaintCreate,
    ComplaintFinalizeRequest,
    ComplaintListResponse,
    ComplaintRead,
    ComplaintUpdate,
)
from app.schemas.intake import (
    IntakeAction,
    IntakeChatInterpretation,
    IntakeChatRequest,
    IntakeChatResponse,
    IntakeFieldCandidate,
)
from app.services import complaint_service
from app.services.completeness import assess_completeness
from app.services.duplicates import find_possible_duplicates
from app.services.document_extract import (
    DocumentExtractionError,
    VisionOcrUnavailableError,
    extract_document,
)
from app.graph.nodes.validate import _ground_fields
from app.services.intake_dialogue import (
    DATE_FIELDS,
    interpret_date_answer,
    is_unavailable_answer,
    issue_reply,
    next_intake_question,
    question_for,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/complaints", tags=["complaints"])

ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}

_INTAKE_FACT_FIELDS = {
    "complaint_source",
    "customer_name",
    "customer_contact",
    "product_name",
    "product_strength_grade",
    "batch_lot_number",
    "manufacturing_date",
    "expiry_date",
    "quantity_affected",
    "quantity_unit",
    "complaint_type",
    "complaint_date",
    "complaint_details",
}

_FIELD_LABELS = {
    "complaint_source": "complaint source",
    "customer_name": "reporter name",
    "customer_contact": "contact information",
    "product_name": "product name",
    "product_strength_grade": "strength or grade",
    "batch_lot_number": "batch or lot number",
    "manufacturing_date": "manufacturing date",
    "expiry_date": "expiry date",
    "quantity_affected": "affected quantity",
    "quantity_unit": "quantity unit",
    "complaint_type": "complaint type",
    "complaint_date": "date the problem was observed",
    "complaint_details": "complaint description",
}

_FOLLOW_UP_BY_LABEL = {
    "complaint source": "How did this complaint reach you — for example by email, distributor, patient, or healthcare professional?",
    "customer name": "Who is reporting the complaint? Please share the person or organisation name.",
    "customer contact": "What is the best email address or phone number for follow-up?",
    "product name": "Which product is the complaint about?",
    "product strength / grade": "What strength or grade is printed on the product?",
    "batch / lot number": "What batch or lot number is printed on the bottle, carton, or blister?",
    "manufacturing date": "What manufacturing date is printed on the product, if available?",
    "expiry date": "What expiry date is printed on the product, if available?",
    "quantity affected": "How many units are affected?",
    "quantity unit": "What type of units are affected — for example bottles, tablets, vials, or packs?",
    "complaint type": "In your own words, is this mainly a product, packaging, labelling, safety, or delivery problem?",
    "complaint date": "On what date was the problem first noticed or reported?",
    "complaint details": "Could you describe exactly what was observed and what happened to the product?",
}


def _field_value_for_message(value: object) -> str:
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, date):
        return value.strftime("%d %B %Y").lstrip("0")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace("_", " ")


def _intake_understanding(fields) -> str:
    parts: list[str] = []
    if fields.quantity_affected is not None:
        quantity = int(fields.quantity_affected) if float(fields.quantity_affected).is_integer() else fields.quantity_affected
        parts.append(f"{quantity} {fields.quantity_unit or 'units'}")
    if fields.product_name:
        parts.append(f"of {fields.product_name}")
    if fields.batch_lot_number:
        parts.append(f"from batch {fields.batch_lot_number}")
    if parts:
        return "The complaint concerns " + " ".join(parts).strip() + "."
    if fields.complaint_details:
        return fields.complaint_details.rstrip(".") + "."
    return "I have recorded the information you provided."


def _next_intake_question(
    completeness,
    unavailable_fields: set[str] | None = None,
) -> tuple[str | None, str | None]:
    return next_intake_question(completeness, unavailable_fields or set())


def _compose_intake_reply_legacy(
    interpretation: IntakeChatInterpretation,
    fields,
    changed_fields: list[str],
    next_question: str | None,
) -> str:
    parts: list[str] = []
    if interpretation.clarification_answer:
        parts.append(interpretation.clarification_answer.strip())
    if changed_fields:
        updates = ", ".join(
            f"{_FIELD_LABELS.get(name, name.replace('_', ' '))} to "
            f"{_field_value_for_message(getattr(fields, name))}"
            for name in changed_fields
        )
        parts.append(f"Got it — I updated {updates}.")
        parts.append(f"Here is what I understand now: {_intake_understanding(fields)}")
    elif interpretation.confirmation:
        parts.append("Thanks for confirming that I understood the complaint correctly.")
    elif not interpretation.clarification_answer:
        parts.append("Thanks. I checked that against the information already in the form.")

    if next_question:
        parts.append(f"I still need one detail: {next_question}")
    else:
        parts.append(
            "I now have the important information needed to lodge the complaint. "
            "Please review the form and correct anything that does not look right."
        )
    return " ".join(parts)


def _compose_intake_reply(
    interpretation: IntakeChatInterpretation,
    fields: ExtractedComplaintFields,
    changed_fields: list[str],
    previous_values: dict[str, object],
    action: IntakeAction,
    feedback: list[IntakeFieldCandidate],
    next_question: str | None,
    unavailable_field: str | None = None,
) -> str:
    """Turn a validated dialogue decision into a short, truthful reporter-facing reply."""

    parts: list[str] = []
    if interpretation.clarification_answer:
        parts.append(interpretation.clarification_answer.strip())

    if feedback and not changed_fields:
        parts.append(issue_reply(feedback[0]))
    elif changed_fields:
        updates = ", ".join(
            f"{_FIELD_LABELS.get(name, name.replace('_', ' '))} as "
            f"{_field_value_for_message(getattr(fields, name))}"
            for name in changed_fields
        )
        corrected = [
            name
            for name in changed_fields
            if previous_values.get(name) not in {None, ""}
        ]
        if corrected:
            old_values = ", ".join(
                f"{_FIELD_LABELS.get(name, name.replace('_', ' '))} from "
                f"{_field_value_for_message(previous_values[name])}"
                for name in corrected
            )
            parts.append(f"No problem—I corrected {old_values}. I’ve recorded {updates}.")
        else:
            parts.append(f"Got it—I recorded {updates}.")
        parts.append(f"This is what I understand so far: {_intake_understanding(fields)}")
        if feedback:
            parts.append(issue_reply(feedback[0]))
    elif unavailable_field:
        label = _FIELD_LABELS.get(unavailable_field, unavailable_field.replace("_", " "))
        parts.append(
            f"That’s okay—I’ve marked the {label} as unavailable and won’t keep asking for it."
        )
    elif interpretation.confirmation:
        parts.append("Thanks for confirming that I understood the complaint correctly.")
    elif not interpretation.clarification_answer and action == "clarify_ambiguous_value":
        parts.append(
            "I couldn’t confidently connect that answer to a form field, so I haven’t changed "
            "the complaint yet."
        )

    if next_question and not feedback:
        if changed_fields or unavailable_field:
            parts.append(f"Next question: {next_question}")
        else:
            parts.append(next_question)
    elif action == "ready_to_lodge":
        parts.append(
            "I now have the important information needed to lodge the complaint. "
            "Please review the form and correct anything that does not look right."
        )

    return " ".join(parts)


async def _read_input(
    request: Request, complaint_text: str | None, file: UploadFile | None
) -> tuple[str, str, str | None, list[str], list[SourceDocument]]:
    """Return text and provenance from an attachment and/or raw text.

    Accepts multipart/form-data (what the frontend sends) and application/json
    (convenient for curl and for the API examples).
    """
    settings = get_settings()

    documents: list[SourceDocument] = []
    warnings: list[str] = []
    attachment_text = ""
    filename: str | None = None
    input_type = "text"

    if file is not None and file.filename:
        suffix = "." + file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
        if suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only PDF, PNG, JPG, and JPEG complaint attachments are supported.",
            )
        data = await file.read()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"The file is larger than the {settings.max_upload_size_mb} MB limit.",
            )
        try:
            document, document_warnings = await run_in_threadpool(
                extract_document, data, file.filename, file.content_type
            )
            documents.append(document)
            warnings.extend(document_warnings)
            attachment_text = document.text
            filename = file.filename
            input_type = "pdf" if suffix == ".pdf" else "image"
        except DocumentExtractionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except VisionOcrUnavailableError as exc:
            if not (complaint_text or "").strip():
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
                ) from exc
            warnings.append(str(exc))

    if complaint_text is None and request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = json.loads(await request.body() or b"{}")
            complaint_text = body.get("complaint_text")
        except (json.JSONDecodeError, AttributeError):
            complaint_text = None

    pieces = [(complaint_text or "").strip(), attachment_text.strip()]
    text = "\n\n".join(piece for piece in pieces if piece)
    return text, input_type, filename, warnings, documents


@router.post("/analyze", response_model=ComplaintAnalysisResponse)
async def analyze_complaint(
    request: Request,
    complaint_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    db: Session = Depends(get_db),
) -> ComplaintAnalysisResponse:
    """Run the LangGraph workflow over a complaint. Nothing is written to the database."""
    settings = get_settings()
    if not settings.llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis is not configured on this server (GROQ_API_KEY is missing).",
        )

    text, input_type, filename, warnings, documents = await _read_input(
        request, complaint_text, file
    )
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Provide complaint text or attach a readable PDF or image. "
                + (" ".join(warnings) if warnings else "")
            ).strip(),
        )

    # The graph is synchronous (the Groq SDK is sync) — keep the event loop free.
    result = await run_in_threadpool(
        run_analysis, text, input_type=input_type, filename=filename, warnings=warnings
    )
    result.duplicate_candidates = find_possible_duplicates(db, result.extracted_fields, text)
    result.source_documents = documents
    return result


async def _interpret_intake_turn(
    payload: IntakeChatRequest,
    *,
    grounding_text: str | None = None,
    source_document: SourceDocument | None = None,
    extra_warnings: list[str] | None = None,
) -> IntakeChatResponse:
    if not get_settings().llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The intake assistant is not configured on this server (GROQ_API_KEY is missing).",
        )

    dialogue = payload.dialogue_state.model_copy(deep=True)
    current = payload.current_fields.model_dump()
    dialogue.unavailable_fields = [
        field
        for field in dialogue.unavailable_fields
        if current.get(field) in {None, ""}
    ]
    dialogue.partial_fields = {
        field: value
        for field, value in dialogue.partial_fields.items()
        if current.get(field) in {None, ""}
    }
    initial_completeness = assess_completeness(payload.current_fields)
    if (
        dialogue.pending_field not in _INTAKE_FACT_FIELDS
        or current.get(dialogue.pending_field) not in {None, ""}
    ):
        dialogue.pending_field, _ = _next_intake_question(
            initial_completeness, set(dialogue.unavailable_fields)
        )

    history = "\n".join(
        f"{message.role.upper()}: {message.text}" for message in payload.history[-8:]
    )
    user_prompt = (
        "CURRENT FORM:\n"
        f"{json.dumps(payload.current_fields.model_dump(mode='json'), indent=2)}\n\n"
        "DIALOGUE STATE:\n"
        f"{json.dumps(dialogue.model_dump(mode='json'), indent=2)}\n\n"
        f"RECENT CONVERSATION:\n{history or '(none)'}\n\n"
        f"LATEST REPORTER MESSAGE:\n"
        f"<complaint>{grounding_text or payload.message}</complaint>\n\n"
        "Return the intake-turn JSON now."
    )
    try:
        raw = await run_in_threadpool(
            complete_json,
            INTAKE_CHAT_SYSTEM,
            user_prompt,
            max_tokens=900,
            schema=IntakeChatInterpretation,
        )
        interpretation = IntakeChatInterpretation.model_validate(raw)
    except (LLMError, ValueError) as exc:
        logger.warning("Conversational intake turn failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The intake assistant could not understand that response. Please try rephrasing it.",
        ) from exc

    grounded_updates, warnings = _ground_fields(
        interpretation.field_updates, grounding_text or payload.message
    )
    feedback_by_field = {
        candidate.field: candidate
        for candidate in interpretation.field_candidates
        if candidate.field in _INTAKE_FACT_FIELDS and candidate.status != "accepted"
    }
    for candidate in interpretation.field_candidates:
        if (
            candidate.field in _INTAKE_FACT_FIELDS
            and candidate.status == "accepted"
            and getattr(grounded_updates, candidate.field) is None
        ):
            feedback_by_field[candidate.field] = candidate.model_copy(
                update={
                    "status": "ambiguous",
                    "reason": (
                        "I understood the attempted value, but could not safely validate it "
                        "against your message."
                    ),
                }
            )

    # Dates need a deterministic second opinion because the model schema intentionally drops
    # incomplete and impossible dates. Preserve a useful partial answer instead of looping.
    date_targets = {
        candidate.field
        for candidate in interpretation.field_candidates
        if candidate.field in DATE_FIELDS
    }
    if dialogue.pending_field in DATE_FIELDS:
        date_targets.add(dialogue.pending_field)
    for field in date_targets:
        if getattr(grounded_updates, field) is not None:
            dialogue.partial_fields.pop(field, None)
            feedback_by_field.pop(field, None)
            continue
        matching = next(
            (
                candidate
                for candidate in interpretation.field_candidates
                if candidate.field == field
            ),
            None,
        )
        raw_date = matching.raw_value if matching else payload.message
        parsed, date_feedback, partial = interpret_date_answer(
            field,
            raw_date,
            dialogue.partial_fields.get(field),
        )
        if parsed is not None:
            grounded_updates = grounded_updates.model_copy(update={field: parsed})
            dialogue.partial_fields.pop(field, None)
            feedback_by_field.pop(field, None)
        elif date_feedback is not None:
            feedback_by_field[field] = date_feedback
            if partial:
                dialogue.partial_fields[field] = partial
            elif date_feedback.status == "invalid":
                dialogue.partial_fields.pop(field, None)

    previous_values = dict(current)
    changed_fields: list[str] = []

    for name in _INTAKE_FACT_FIELDS:
        value = getattr(grounded_updates, name)
        if value is not None and current.get(name) != value:
            current[name] = value
            changed_fields.append(name)

    for name in interpretation.clear_fields:
        if name in _INTAKE_FACT_FIELDS and current.get(name) is not None:
            current[name] = None
            changed_fields.append(name)

    unavailable_field: str | None = None
    if (
        dialogue.pending_field
        and not changed_fields
        and (
            interpretation.intent == "unavailable"
            or is_unavailable_answer(payload.message)
        )
    ):
        unavailable_field = dialogue.pending_field
        if unavailable_field not in dialogue.unavailable_fields:
            dialogue.unavailable_fields.append(unavailable_field)
        dialogue.partial_fields.pop(unavailable_field, None)
        dialogue.retry_counts.pop(unavailable_field, None)
        feedback_by_field.pop(unavailable_field, None)

    for name in changed_fields:
        dialogue.partial_fields.pop(name, None)
        dialogue.retry_counts.pop(name, None)
        if name in dialogue.unavailable_fields:
            dialogue.unavailable_fields.remove(name)

    updated_fields = ExtractedComplaintFields.model_validate(current)
    completeness = assess_completeness(updated_fields)
    feedback = list(feedback_by_field.values())

    action: IntakeAction
    next_field: str | None
    next_question: str | None
    if feedback:
        next_field = feedback[0].field
        dialogue.retry_counts[next_field] = dialogue.retry_counts.get(next_field, 0) + 1
        next_question = None
        action = (
            "clarify_partial_value"
            if feedback[0].status == "partial"
            else "explain_invalid_value"
            if feedback[0].status == "invalid"
            else "clarify_ambiguous_value"
        )
    else:
        next_field, next_question = _next_intake_question(
            completeness, set(dialogue.unavailable_fields)
        )
        if changed_fields:
            action = (
                "confirm_correction"
                if interpretation.intent == "correct_information"
                or any(previous_values.get(name) not in {None, ""} for name in changed_fields)
                else "accept_information"
            )
        elif unavailable_field:
            action = "acknowledge_unavailable"
        elif interpretation.clarification_answer:
            action = "answer_question"
        elif interpretation.confirmation:
            action = "confirm_understanding"
        elif next_field:
            action = "clarify_ambiguous_value"
            dialogue.retry_counts[next_field] = dialogue.retry_counts.get(next_field, 0) + 1
            next_question = question_for(
                next_field, retry_count=dialogue.retry_counts[next_field]
            )
        elif completeness.is_complete:
            action = "ready_to_lodge"
        else:
            action = "ask_missing_detail"
            unavailable_critical = ", ".join(completeness.missing_critical_fields)
            next_question = (
                "The complaint still needs "
                f"{unavailable_critical} before it can be lodged. "
                "Please add it in the form if it becomes available."
            )

    if next_field and next_question:
        dialogue.question_history = [*dialogue.question_history, next_question][-12:]
    dialogue.pending_field = next_field
    dialogue.last_action = action

    assistant_message = _compose_intake_reply(
        interpretation,
        updated_fields,
        changed_fields,
        previous_values,
        action,
        feedback,
        next_question,
        unavailable_field,
    )
    if (
        completeness.is_complete
        and next_question is None
        and not feedback
        and action != "ready_to_lodge"
    ):
        assistant_message += (
            " I now have the important information needed to lodge the complaint. "
            "Please review the form and correct anything that does not look right."
        )

    return IntakeChatResponse(
        assistant_message=assistant_message,
        updated_fields=updated_fields,
        completeness=completeness,
        changed_fields=list(dict.fromkeys(changed_fields)),
        action=action,
        validation_feedback=feedback,
        dialogue_state=dialogue,
        ready_to_lodge=completeness.is_complete,
        warnings=list(dict.fromkeys([*(extra_warnings or []), *warnings])),
        source_document=source_document,
    )


@router.post("/intake/chat", response_model=IntakeChatResponse)
async def continue_intake_chat(payload: IntakeChatRequest) -> IntakeChatResponse:
    """Interpret one natural-language correction or follow-up during complaint intake."""
    return await _interpret_intake_turn(payload)


@router.post("/intake/chat/attachment", response_model=IntakeChatResponse)
async def continue_intake_chat_with_attachment(
    message: Annotated[str, Form()] = "",
    current_fields: Annotated[str, Form()] = "{}",
    history: Annotated[str, Form()] = "[]",
    dialogue_state: Annotated[str, Form()] = "{}",
    file: Annotated[UploadFile, File()] = ...,
) -> IntakeChatResponse:
    """Interpret a later chat turn that includes a PDF or image attachment."""
    try:
        fields = ExtractedComplaintFields.model_validate(json.loads(current_fields))
        history_items = json.loads(history)
        payload = IntakeChatRequest(
            message=message.strip() or f"I attached {file.filename or 'a complaint document'}.",
            current_fields=fields,
            history=history_items,
            dialogue_state=json.loads(dialogue_state),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The intake attachment metadata was invalid.",
        ) from exc

    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"The file is larger than the {settings.max_upload_size_mb} MB limit.",
        )
    try:
        document, warnings = await run_in_threadpool(
            extract_document,
            data,
            file.filename or "attachment",
            file.content_type,
        )
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except VisionOcrUnavailableError as exc:
        if message.strip():
            return await _interpret_intake_turn(
                payload,
                grounding_text=message.strip(),
                extra_warnings=[str(exc)],
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    combined = (
        f"{payload.message}\n\n"
        f"ATTACHED DOCUMENT {document.filename}:\n{document.text}"
    )
    return await _interpret_intake_turn(
        payload,
        grounding_text=combined,
        source_document=document,
        extra_warnings=warnings,
    )


def _canonical_final_text(payload: ComplaintFinalizeRequest) -> str:
    fields = payload.fields.model_dump(mode="json")
    labelled = "\n".join(
        f"{name.replace('_', ' ').title()}: {value}"
        for name, value in fields.items()
        if value is not None and value != ""
    )
    sources = "\n\n".join(
        f"[Attachment: {document.filename}; extraction: {document.extraction_method}]\n"
        f"{document.text}"
        for document in payload.source_documents
    )
    transcript = "\n".join(
        f"{message.role.upper()}: {message.text}" for message in payload.intake_transcript
    )
    return (
        "FINAL AUTHORITATIVE COMPLAINT FORM\n"
        f"{labelled}\n\n"
        f"ORIGINAL REPORTER INPUT\n{payload.original_text or '(not provided)'}\n\n"
        f"SOURCE ATTACHMENTS\n{sources or '(none)'}\n\n"
        f"INTAKE CONVERSATION\n{transcript or '(none)'}"
    )


@router.post("/finalize", response_model=ComplaintRead, status_code=status.HTTP_201_CREATED)
async def finalize_complaint(
    payload: ComplaintFinalizeRequest,
    db: Session = Depends(get_db),
) -> ComplaintRead:
    """Regenerate internal QA support from final form facts, then lodge one consistent row."""
    canonical_text = _canonical_final_text(payload)
    analysis = await run_in_threadpool(
        run_final_analysis,
        payload.fields,
        canonical_text,
        warnings=payload.warnings,
    )
    duplicates = find_possible_duplicates(
        db,
        analysis.extracted_fields,
        canonical_text,
    )
    risk = analysis.risk_assessment
    fields = payload.fields.model_copy(
        update={
            "initial_severity": (
                risk.severity if risk.severity.value != "unknown" else payload.fields.initial_severity
            ),
            "priority": risk.priority,
        }
    )
    create_payload = ComplaintCreate(
        **fields.model_dump(),
        risk_level=risk.risk_level,
        risk_rationale=risk.rationale,
        risk_confidence=risk.confidence,
        patient_safety_concern=risk.patient_safety_concern,
        product_quality_concern=risk.product_quality_concern,
        ai_summary=analysis.summary,
        completeness_score=analysis.completeness.score,
        missing_fields=[
            *analysis.completeness.missing_critical_fields,
            *analysis.completeness.missing_optional_fields,
        ],
        root_cause_recommendations=analysis.recommendations.possible_root_causes,
        initial_investigation_steps=analysis.recommendations.initial_investigation_steps,
        capa_recommendations=analysis.recommendations.preliminary_capa_suggestions,
        duplicate_candidates=[candidate.model_dump(mode="json") for candidate in duplicates],
        analysis_warnings=analysis.warnings,
        original_text=payload.original_text,
        input_filename=payload.input_filename,
        intake_transcript=[
            message.model_dump(mode="json") for message in payload.intake_transcript
        ],
        source_documents=[
            document.model_dump(mode="json") for document in payload.source_documents
        ],
        status="open",
    )
    complaint = complaint_service.create_complaint(db, create_payload)
    return ComplaintRead.model_validate(complaint)


@router.post("", response_model=ComplaintRead, status_code=status.HTTP_201_CREATED)
def create_complaint(payload: ComplaintCreate, db: Session = Depends(get_db)) -> ComplaintRead:
    """Save a complaint after a human has reviewed it."""
    complaint = complaint_service.create_complaint(db, payload)
    return ComplaintRead.model_validate(complaint)


@router.get("", response_model=ComplaintListResponse)
def list_complaints(
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status"),
) -> ComplaintListResponse:
    rows, total = complaint_service.list_complaints(
        db, limit=limit, offset=offset, search=search, status=status_filter
    )
    return ComplaintListResponse(
        items=[ComplaintRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{complaint_id}", response_model=ComplaintRead)
def get_complaint(complaint_id: int, db: Session = Depends(get_db)) -> ComplaintRead:
    return ComplaintRead.model_validate(_get_or_404(db, complaint_id))


@router.put("/{complaint_id}", response_model=ComplaintRead)
def update_complaint(
    complaint_id: int, payload: ComplaintUpdate, db: Session = Depends(get_db)
) -> ComplaintRead:
    _get_or_404(db, complaint_id)
    return ComplaintRead.model_validate(complaint_service.update_complaint(db, complaint_id, payload))


@router.delete("/{complaint_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_complaint(complaint_id: int, db: Session = Depends(get_db)) -> Response:
    _get_or_404(db, complaint_id)
    complaint_service.delete_complaint(db, complaint_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{complaint_id}/chat", response_model=ChatResponse)
async def chat_about_complaint(
    complaint_id: int, payload: ChatRequest, db: Session = Depends(get_db)
) -> ChatResponse:
    """Answer a question using only the stored complaint record."""
    if not get_settings().llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is not configured on this server (GROQ_API_KEY is missing).",
        )
    complaint = _get_or_404(db, complaint_id)

    record = {
        field: getattr(complaint, field)
        for field in (
            "complaint_number", "complaint_source", "customer_name", "product_name",
            "product_strength_grade", "batch_lot_number", "manufacturing_date", "expiry_date",
            "quantity_affected", "quantity_unit", "complaint_type", "complaint_date",
            "complaint_details", "initial_severity", "priority", "risk_level", "risk_rationale",
            "ai_summary", "status",
        )
    }
    user_prompt = (
        f"COMPLAINT RECORD:\n{json.dumps(record, indent=2, default=str)}\n\n"
        f"QUESTION: {payload.question}"
    )
    try:
        answer = await run_in_threadpool(complete_text, CHAT_SYSTEM, user_prompt, max_tokens=400)
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return ChatResponse(answer=answer, grounded_in=complaint.complaint_number)


def _get_or_404(db: Session, complaint_id: int):
    try:
        return complaint_service.get_complaint(db, complaint_id)
    except complaint_service.ComplaintNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
