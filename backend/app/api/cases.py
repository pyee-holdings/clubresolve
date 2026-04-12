"""Case CRUD endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.case import Case
from app.api.auth import get_current_user
from app.schemas.case import CaseCreate, CaseUpdate, CaseResponse

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", response_model=CaseResponse)
async def create_case(
    case_data: CaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new case from structured intake form."""
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
