"""Schemas for the conversational complaint-intake assistant."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import CompletenessAssessment, ExtractedComplaintFields, SourceDocument


class IntakeChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class IntakeChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    current_fields: ExtractedComplaintFields
    history: list[IntakeChatMessage] = Field(default_factory=list, max_length=20)


class IntakeChatInterpretation(BaseModel):
    """Strict LLM output for one intake turn."""

    field_updates: ExtractedComplaintFields = Field(default_factory=ExtractedComplaintFields)
    clear_fields: list[str] = Field(default_factory=list)
    clarification_answer: str | None = None
    confirmation: bool = False


class IntakeChatResponse(BaseModel):
    assistant_message: str
    updated_fields: ExtractedComplaintFields
    completeness: CompletenessAssessment
    changed_fields: list[str] = Field(default_factory=list)
    ready_to_lodge: bool = False
    warnings: list[str] = Field(default_factory=list)
    source_document: SourceDocument | None = None
