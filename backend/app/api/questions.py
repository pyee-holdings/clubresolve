"""CaseQuestion endpoints — list, answer, dismiss clarifying questions."""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.case import Case
from app.models.question import CaseQuestion, QuestionStatus
from app.models.user import User
from app.schemas.question import (
    AnswerQuestionRequest,
    CaseQuestionResponse,
    DismissQuestionRequest,
)
from app.services.review_status import refresh_review_status
from app.services.strategic_planner import run_planner_background

router = APIRouter(prefix="/api/cases/{case_id}/questions", tags=["questions"])


async def _load_case_for_user(case_id: str, user: User, db: AsyncSession) -> Case:
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


async def _load_case_and_question(
    case_id: str, question_id: str, user: User, db: AsyncSession
) -> tuple[Case, CaseQuestion]:
    case = await _load_case_for_user(case_id, user, db)
    result = await db.execute(
        select(CaseQuestion).where(
            CaseQuestion.id == question_id, CaseQuestion.case_id == case_id
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return case, question


@router.get("", response_model=list[CaseQuestionResponse])
async def list_questions(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all questions for a case, newest-first within priority tiers."""
    await _load_case_for_user(case_id, current_user, db)
    result = await db.execute(
        select(CaseQuestion)
        .where(CaseQuestion.case_id == case_id)
        .order_by(CaseQuestion.created_at.asc())
    )
    return list(result.scalars().all())


async def _maybe_fire_planner(
    case: Case,
    prev_status: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> None:
    """If this mutation drove the review across the finish line, plan now.

    Skip if the planner is already running to avoid double-fire when two
    concurrent resolutions both flip review_status from needs_input to
    complete (e.g. parallel tabs).

    Commits eagerly so the background task's fresh session sees the
    ``planning`` marker — otherwise the task can race the dependency-teardown
    commit and reset to ``idle`` before the endpoint's commit writes
    ``planning``.
    """
    if prev_status == "complete" or case.review_status != "complete":
        return
    if case.plan_status == "planning":
        return
    case.plan_status = "planning"
    await db.commit()
    background_tasks.add_task(run_planner_background, case.id)


@router.post("/{question_id}/answer", response_model=CaseQuestionResponse)
async def answer_question(
    case_id: str,
    question_id: str,
    payload: AnswerQuestionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case, question = await _load_case_and_question(
        case_id, question_id, current_user, db
    )
    prev_status = case.review_status

    question.answer = payload.answer.strip()
    question.status = QuestionStatus.ANSWERED
    question.answered_at = datetime.utcnow()

    await refresh_review_status(case, db)
    await _maybe_fire_planner(case, prev_status, background_tasks, db)
    await db.flush()
    return question


@router.post("/{question_id}/dismiss", response_model=CaseQuestionResponse)
async def dismiss_question(
    case_id: str,
    question_id: str,
    payload: DismissQuestionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case, question = await _load_case_and_question(
        case_id, question_id, current_user, db
    )
    prev_status = case.review_status

    question.status = QuestionStatus.DISMISSED
    question.answered_at = datetime.utcnow()
    if payload.reason:
        # Store the reason in the answer field so it's preserved in history.
        question.answer = f"[dismissed] {payload.reason.strip()}"

    await refresh_review_status(case, db)
    await _maybe_fire_planner(case, prev_status, background_tasks, db)
    await db.flush()
    return question
