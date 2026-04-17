"""Schemas for the Wizard action plan generator."""

from pydantic import BaseModel, Field


class WizardIntakeRequest(BaseModel):
    """Intake form submission from the Wizard."""
    province: str = Field(default="BC", description="Province/jurisdiction")
    sport: str = Field(..., description="Type of sport or club")
    category: str = Field(..., description="Dispute category")
    tried: str = Field(default="", description="What the parent has already tried")
    desired_outcome: str = Field(default="", description="What outcome the parent wants")
    description: str = Field(default="", description="Free-text description of the situation")
    email: str = Field(default="", description="Email for follow-up (optional)")


class ActionStep(BaseModel):
    """A single step in the action plan."""
    title: str
    description: str
    citation: str = ""
    template: str = ""
    deadline: str = ""


class EscalationStep(BaseModel):
    """A single step in the escalation timeline."""
    condition: str = Field(..., alias="if")
    action: str = Field(..., alias="then")
    deadline: str = ""

    class Config:
        populate_by_name = True


class ActionPlanResponse(BaseModel):
    """The generated action plan."""
    summary: str
    steps: list[ActionStep]
    escalation_timeline: list[EscalationStep]
    disclaimer: str
