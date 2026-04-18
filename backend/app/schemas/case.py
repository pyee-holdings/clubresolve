"""Case schemas."""

from datetime import datetime

from pydantic import BaseModel


class CaseCreate(BaseModel):
    """Structured intake form data."""
    title: str
    category: str | None = None
    club_name: str | None = None
    sport: str | None = None
    description: str | None = None
    desired_outcome: str | None = None
    urgency: str = "medium"
    risk_flags: list[str] | None = None  # ["athlete_safety", "retaliation", "eligibility", "financial", "child_welfare"]
    people_involved: list[dict] | None = None  # [{"name": "...", "role": "..."}]
    prior_attempts: str | None = None
    timeline_start: str | None = None


class CaseUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    club_name: str | None = None
    sport: str | None = None
    description: str | None = None
    desired_outcome: str | None = None
    urgency: str | None = None
    risk_flags: list[str] | None = None
    people_involved: list[dict] | None = None
    prior_attempts: str | None = None
    status: str | None = None


class CaseResponse(BaseModel):
    id: str
    title: str
    category: str | None
    club_name: str | None
    sport: str | None
    description: str | None
    desired_outcome: str | None
    urgency: str
    risk_flags: list[str] | None
    people_involved: list[dict] | None
    prior_attempts: str | None
    status: str
    review_status: str
    escalation_level: int
    strategy_plan: str | None
    legal_summary: str | None
    next_steps: list[dict] | None
    missing_info: list[str] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
