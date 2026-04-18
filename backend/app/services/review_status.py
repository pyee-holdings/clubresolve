"""Single source of truth for `case.review_status` transitions.

The review is "complete" only when every clarifying question AND every
evidence request is resolved (answered/dismissed, or fulfilled/unavailable/
dismissed). Both domains live in different tables; this helper centralizes
the check so the questions and evidence-requests endpoints can't drift.

Only affects transitions *after* the intake review has produced items. If
the review is still "pending" or "reviewing", we don't touch the status.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.evidence_request import EvidenceRequest, EvidenceRequestStatus
from app.models.question import CaseQuestion, QuestionStatus


async def refresh_review_status(case: Case, db: AsyncSession) -> None:
    """Recalculate case.review_status based on open questions + evidence requests.

    Rules:
      - If status is "pending" or "reviewing", don't touch — the review agent
        is the only thing that should move it out of those states.
      - If any question is OPEN → "needs_input"
      - If any evidence request is OPEN → "needs_input"
      - Otherwise → "complete"
    """
    if case.review_status in {"pending", "reviewing"}:
        return

    open_q = (
        await db.execute(
            select(CaseQuestion).where(
                CaseQuestion.case_id == case.id,
                CaseQuestion.status == QuestionStatus.OPEN,
            )
        )
    ).scalars().first()
    if open_q is not None:
        case.review_status = "needs_input"
        return

    open_e = (
        await db.execute(
            select(EvidenceRequest).where(
                EvidenceRequest.case_id == case.id,
                EvidenceRequest.status == EvidenceRequestStatus.OPEN,
            )
        )
    ).scalars().first()
    if open_e is not None:
        case.review_status = "needs_input"
        return

    case.review_status = "complete"
