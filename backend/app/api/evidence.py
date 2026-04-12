"""Evidence and timeline management endpoints."""

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.case import Case
from app.models.evidence import EvidenceItem, TimelineEvent
from app.api.auth import get_current_user
from app.schemas.evidence import (
    EvidenceCreate,
    EvidenceResponse,
    TimelineEventCreate,
    TimelineEventResponse,
    DraftCreate,
    DraftResponse,
)
from app.models.draft import Draft

router = APIRouter(prefix="/api/cases/{case_id}", tags=["evidence"])


async def _get_case(case_id: str, user: User, db: AsyncSession) -> Case:
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


# --- Evidence ---


@router.post("/evidence", response_model=EvidenceResponse)
async def add_evidence(
    case_id: str,
    evidence_data: EvidenceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_case(case_id, current_user, db)

    item = EvidenceItem(
        case_id=case_id,
        title=evidence_data.title,
        description=evidence_data.description,
        evidence_type=evidence_data.evidence_type,
        source_reference=evidence_data.source_reference,
        content=evidence_data.content,
        tags=evidence_data.tags,
        event_date=evidence_data.event_date,
        collected_by="user",
    )
    db.add(item)
    await db.flush()
    return item


@router.post("/evidence/upload", response_model=EvidenceResponse)
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    title: str = Form(...),
    evidence_type: str = Form("document"),
    description: str | None = Form(None),
    event_date: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file as evidence."""
    await _get_case(case_id, current_user, db)

    # Save file
    upload_dir = os.path.join(settings.upload_dir, case_id)
    os.makedirs(upload_dir, exist_ok=True)

    file_id = str(uuid.uuid4())[:8]
    filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(upload_dir, filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    item = EvidenceItem(
        case_id=case_id,
        title=title,
        description=description,
        evidence_type=evidence_type,
        file_path=file_path,
        event_date=event_date,
        collected_by="user",
    )
    db.add(item)
    await db.flush()
    return item


@router.get("/evidence", response_model=list[EvidenceResponse])
async def list_evidence(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_case(case_id, current_user, db)
    result = await db.execute(
        select(EvidenceItem)
        .where(EvidenceItem.case_id == case_id)
        .order_by(EvidenceItem.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/evidence/{evidence_id}")
async def delete_evidence(
    case_id: str,
    evidence_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_case(case_id, current_user, db)
    result = await db.execute(
        select(EvidenceItem).where(EvidenceItem.id == evidence_id, EvidenceItem.case_id == case_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found")
    await db.delete(item)
    return {"detail": "Evidence deleted"}


# --- Timeline ---


@router.post("/timeline", response_model=TimelineEventResponse)
async def add_timeline_event(
    case_id: str,
    event_data: TimelineEventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_case(case_id, current_user, db)
    event = TimelineEvent(
        case_id=case_id,
        event_date=event_data.event_date,
        description=event_data.description,
        evidence_ids=event_data.evidence_ids,
        source=event_data.source,
        event_type=event_data.event_type,
    )
    db.add(event)
    await db.flush()
    return event


@router.get("/timeline", response_model=list[TimelineEventResponse])
async def list_timeline(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_case(case_id, current_user, db)
    result = await db.execute(
        select(TimelineEvent)
        .where(TimelineEvent.case_id == case_id)
        .order_by(TimelineEvent.event_date.asc())
    )
    return result.scalars().all()


# --- Drafts ---


@router.post("/drafts", response_model=DraftResponse)
async def create_draft(
    case_id: str,
    draft_data: DraftCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_case(case_id, current_user, db)
    draft = Draft(
        case_id=case_id,
        draft_type=draft_data.draft_type,
        title=draft_data.title,
        content=draft_data.content,
        recipient=draft_data.recipient,
        tone=draft_data.tone,
    )
    db.add(draft)
    await db.flush()
    return draft


@router.get("/drafts", response_model=list[DraftResponse])
async def list_drafts(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_case(case_id, current_user, db)
    result = await db.execute(
        select(Draft)
        .where(Draft.case_id == case_id)
        .order_by(Draft.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/drafts/{draft_id}", response_model=DraftResponse)
async def update_draft(
    case_id: str,
    draft_id: str,
    draft_data: DraftCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_case(case_id, current_user, db)
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id, Draft.case_id == case_id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft.content = draft_data.content
    draft.title = draft_data.title
    draft.recipient = draft_data.recipient
    draft.tone = draft_data.tone
    await db.flush()
    return draft
