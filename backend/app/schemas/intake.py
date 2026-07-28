"""Schemas for the conversational complaint-intake assistant."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import CompletenessAssessment, ExtractedComplaintFields, SourceDocument


class IntakeChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


IntakeAction = Literal[
    "accept_information",
    "confirm_correction",
    "ask_missing_detail",
    "clarify_partial_value",
    "explain_invalid_value",
    "clarify_ambiguous_value",
    "answer_question",
    "acknowledge_unavailable",
    "acknowledge_smalltalk",
    "confirm_understanding",
    "ready_to_lodge",
]


class IntakeFieldCandidate(BaseModel):
    """One value mentioned by the reporter, including values that cannot yet be saved."""

    field: str = Field(min_length=1, max_length=80)
    raw_value: str = Field(min_length=1, max_length=500)
    status: Literal["accepted", "partial", "invalid", "ambiguous"] = "accepted"
    reason: str | None = Field(default=None, max_length=240)


class IntakeDialogueState(BaseModel):
    """Small, client-carried state that makes terse follow-up answers understandable."""

    pending_field: str | None = None
    partial_fields: dict[str, str] = Field(default_factory=dict)
    unavailable_fields: list[str] = Field(default_factory=list)
    question_history: list[str] = Field(default_factory=list, max_length=12)
    retry_counts: dict[str, int] = Field(default_factory=dict)
    last_action: IntakeAction | None = None


class IntakeChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    current_fields: ExtractedComplaintFields
    history: list[IntakeChatMessage] = Field(default_factory=list, max_length=20)
    dialogue_state: IntakeDialogueState = Field(default_factory=IntakeDialogueState)


class IntakeChatInterpretation(BaseModel):
    """Strict LLM output for one intake turn."""

    intent: Literal[
        "provide_information",
        "correct_information",
        "confirm",
        "ask_question",
        "unavailable",
        "unrelated",
    ] = "provide_information"
    field_updates: ExtractedComplaintFields = Field(default_factory=ExtractedComplaintFields)
    field_candidates: list[IntakeFieldCandidate] = Field(default_factory=list, max_length=20)
    clear_fields: list[str] = Field(default_factory=list)
    clarification_answer: str | None = None
    confirmation: bool = False


class IntakeChatResponse(BaseModel):
    assistant_message: str
    updated_fields: ExtractedComplaintFields
    completeness: CompletenessAssessment
    changed_fields: list[str] = Field(default_factory=list)
    action: IntakeAction = "ask_missing_detail"
    validation_feedback: list[IntakeFieldCandidate] = Field(default_factory=list)
    dialogue_state: IntakeDialogueState = Field(default_factory=IntakeDialogueState)
    ready_to_lodge: bool = False
    warnings: list[str] = Field(default_factory=list)
    source_document: SourceDocument | None = None
