"""Pydantic schemas for EvidenceRequest."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.evidence_request import EvidenceRequestStatus


# Canonical evidence types — stay aligned with EvidenceItem.evidence_type.
EVIDENCE_TYPES = {
    "email",
    "screenshot",
    "document",
    "receipt",
    "correspondence",
    "policy",
    "note",
    "contract",
    "testimony",
    "other",
}


class EvidenceRequestDraft(BaseModel):
    """Shape the LLM returns, before persistence."""

    title: str = Field(..., min_length=3, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    evidence_type: str = Field(default="document", max_length=50)
    expected_date: str | None = Field(default=None, max_length=20)
    priority: str = Field(default="important", max_length=20)


class EvidenceRequestResponse(BaseModel):
    id: str
    case_id: str
    title: str
    description: str | None
    evidence_type: str
    expected_date: str | None
    priority: str
    generated_by: str
    status: EvidenceRequestStatus
    fulfilled_at: datetime | None
    evidence_item_id: str | None
    unavailable_reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FulfillWithTextRequest(BaseModel):
    """User describes the evidence in their own words rather than uploading a file."""

    title: str | None = Field(default=None, max_length=500)  # optional override
    content: str = Field(..., min_length=1, max_length=20000)
    source_reference: str | None = Field(default=None, max_length=500)
    event_date: str | None = Field(default=None, max_length=20)


class MarkUnavailableRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
