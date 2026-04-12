"""Shared case state — the contract between all agents.

This TypedDict defines what flows through the LangGraph StateGraph.
The Navigator (strategy agent) is the supervisor that maintains this state
and delegates to specialists via Command routing.
"""

from typing import Annotated, Literal
from operator import add

from langgraph.graph import MessagesState


class CaseState(MessagesState):
    """Extends MessagesState (gives us 'messages' with append semantics).

    This is the canonical case state shared across all agents.
    """

    # Case identity
    case_id: str
    case_category: str | None  # billing, safety, governance, coaching, eligibility, other

    # Structured intake data
    club_name: str | None
    sport: str | None
    description: str | None
    desired_outcome: str | None
    urgency: str  # low, medium, high, critical
    risk_flags: list[str]  # ["athlete_safety", "retaliation", "eligibility", "financial", "child_welfare"]
    people_involved: list[dict]  # [{"name": "...", "role": "..."}]
    prior_attempts: str | None

    # Intake state
    intake_complete: bool

    # Agent routing
    current_agent: Literal["navigator", "counsel", "vault", "drafts"]
    delegation_task: str | None  # What the specialist should do

    # Navigator outputs
    issue_assessment: str | None
    strategy_plan: str | None
    next_steps: list[dict]  # [{"step": "...", "due": "this week", "priority": "high"}]
    escalation_ladder: list[dict]  # [{"level": 0, "action": "...", "trigger": "..."}]
    missing_info: list[str]  # ["Need copy of bylaws", ...]
    escalation_level: int  # 0=internal, 1=governing body, 2=formal, 3=legal
    action_risks: str | None  # Risks of acting too early or too aggressively

    # Counsel outputs (accumulated)
    legal_findings: Annotated[list[dict], add]  # [{"finding": "...", "source": "...", "confidence": "high/medium/low"}]
    legal_summary: str | None

    # Vault outputs (accumulated)
    evidence_items: Annotated[list[dict], add]  # Evidence metadata
    timeline_events: Annotated[list[dict], add]  # Chronology entries
    contradictions: Annotated[list[str], add]  # Noted contradictions in evidence
    unanswered_questions: Annotated[list[str], add]
    evidence_summary: str | None

    # Draft Studio outputs (accumulated)
    drafts_generated: Annotated[list[dict], add]  # [{"type": "email", "title": "...", "content": "..."}]

    # Safety rails
    confidence_level: str | None  # Overall confidence: high/medium/low
    resolution_status: str | None
