"""CaseQuestion endpoints — list, answer, dismiss clarifying questions."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/{question_id}/answer", response_model=CaseQuestionResponse)
async def answer_question(
    case_id: str,
    question_id: str,
    payload: AnswerQuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case, question = await _load_case_and_question(
        case_id, question_id, current_user, db
    )

    question.answer = payload.answer.strip()
    question.status = QuestionStatus.ANSWERED
    question.answered_at = datetime.utcnow()

    await refresh_review_status(case, db)
    await db.flush()
    return question


@router.post("/{question_id}/dismiss", response_model=CaseQuestionResponse)
async def dismiss_question(
    case_id: str,
    question_id: str,
    payload: DismissQuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case, question = await _load_case_and_question(
        case_id, question_id, current_user, db
    )

    question.status = QuestionStatus.DISMISSED
    question.answered_at = datetime.utcnow()
    if payload.reason:
        # Store the reason in the answer field so it's preserved in history.
        question.answer = f"[dismissed] {payload.reason.strip()}"

    await refresh_review_status(case, db)
    await db.flush()
    return question
