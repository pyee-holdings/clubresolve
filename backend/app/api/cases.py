"""Case CRUD endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.case import Case
from app.models.evidence_request import EvidenceRequest
from app.models.question import CaseQuestion
from app.api.auth import get_current_user
from app.schemas.case import CaseCreate, CaseUpdate, CaseResponse, VisitResponse
from app.services.intake_review import run_intake_review_background
from app.services.strategic_planner import run_planner_background

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", response_model=CaseResponse)
async def create_case(
    case_data: CaseCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new case from structured intake form.

    After the case is saved, an intake review runs in the background to
    produce clarifying questions for the user. The endpoint returns
    immediately; the frontend polls /questions to pick them up.
    """
    case = Case(
        user_id=current_user.id,
        title=case_data.title,
        category=case_data.category,
        club_name=case_data.club_name,
        sport=case_data.sport,
        description=case_data.description,
        desired_outcome=case_data.desired_outcome,
        urgency=case_data.urgency,
        risk_flags=case_data.risk_flags,
        people_involved=case_data.people_involved,
        prior_attempts=case_data.prior_attempts,
        timeline_start=case_data.timeline_start,
        langgraph_thread_id=str(uuid.uuid4()),
    )
    db.add(case)
    await db.flush()
    case_id = case.id
    await db.commit()

    background_tasks.add_task(run_intake_review_background, case_id)
    return case


@router.get("", response_model=list[CaseResponse])
async def list_cases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case)
        .where(Case.user_id == current_user.id)
        .order_by(Case.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == current_user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    case_data: CaseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == current_user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    update_data = case_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(case, key, value)

    await db.flush()
    return case


@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == current_user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await db.delete(case)
    return {"detail": "Case deleted"}


@router.post("/{case_id}/review/retry", response_model=CaseResponse)
async def retry_intake_review(
    case_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run the intake review for this case.

    Use when the background review got stuck in ``reviewing`` (worker died
    mid-flight) or when the user added an API key after creating the case
    and now wants a review. Clears all agent-generated questions and
    evidence requests, resets review_status to ``pending``, and kicks off
    a fresh background task.

    Only deletes agent-generated items. Does not touch user-created
    evidence items in the vault.
    """
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == current_user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await db.execute(delete(CaseQuestion).where(CaseQuestion.case_id == case_id))
    await db.execute(
        delete(EvidenceRequest).where(
            EvidenceRequest.case_id == case_id,
            EvidenceRequest.generated_by == "intake_review_agent",
        )
    )
    case.review_status = "pending"
    await db.commit()

    background_tasks.add_task(run_intake_review_background, case_id)
    return case


@router.post("/{case_id}/visit", response_model=VisitResponse)
async def mark_case_visited(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record that the user has opened this case.

    Returns the PREVIOUS last_visited_at (before this call) alongside the
    new value. The frontend uses the previous value to compute "what's
    new since your last visit" against entity created_at timestamps.

    Called by the case detail page on mount. Safe to call repeatedly —
    the previous_visited_at will simply move forward with each call.
    """
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == current_user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    previous = case.last_visited_at
    current = datetime.utcnow()
    case.last_visited_at = current
    await db.flush()
    return VisitResponse(previous_visited_at=previous, current_visited_at=current)


@router.post("/{case_id}/plan/regenerate", response_model=CaseResponse)
async def regenerate_plan(
    case_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kick off a strategic planner run. Returns immediately; the plan is
    produced in the background. Frontend should poll ``plan_status`` until
    it is ``ready`` or ``error``.

    Safe to call at any time; overwrites the existing plan fields.
    """
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == current_user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.plan_status = "planning"
    await db.commit()
    background_tasks.add_task(run_planner_background, case_id)
    return case
