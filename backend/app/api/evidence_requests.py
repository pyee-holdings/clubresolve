"""EvidenceRequest endpoints — list, fulfill (text or file), mark unavailable, dismiss.

Fulfilling a request atomically creates an EvidenceItem and links it back
so the provenance (agent asked → user provided) is preserved.
"""

import os
import re
import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.case import Case
from app.models.evidence import EvidenceItem
from app.models.evidence_request import EvidenceRequest, EvidenceRequestStatus
from app.models.user import User
from app.schemas.evidence_request import (
    EvidenceRequestResponse,
    FulfillWithTextRequest,
    MarkUnavailableRequest,
)
from app.services.review_status import refresh_review_status
from app.services.strategic_planner import run_planner_background

# 25 MB cap on uploaded evidence files.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MB streaming chunks

# Allow letters, numbers, dot, underscore, dash. Anything else is stripped.
_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_MAX_FILENAME_LENGTH = 100

router = APIRouter(
    prefix="/api/cases/{case_id}/evidence-requests", tags=["evidence-requests"]
)


async def _load_case_for_user(case_id: str, user: User, db: AsyncSession) -> Case:
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


async def _load_case_and_request(
    case_id: str, request_id: str, user: User, db: AsyncSession
) -> tuple[Case, EvidenceRequest]:
    """Load the case (owner-checked) and the evidence request in one pass."""
    case = await _load_case_for_user(case_id, user, db)
    result = await db.execute(
        select(EvidenceRequest).where(
            EvidenceRequest.id == request_id,
            EvidenceRequest.case_id == case_id,
        )
    )
    er = result.scalar_one_or_none()
    if er is None:
        raise HTTPException(status_code=404, detail="Evidence request not found")
    return case, er


async def _maybe_fire_planner(
    case: Case,
    prev_status: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> None:
    """Fire the strategic planner once the review flips to complete.

    Skips if the planner is already running so concurrent resolutions on
    separate items (e.g., from two browser tabs) don't launch two planners.

    Commits eagerly so the background task's fresh session sees the
    ``planning`` marker — otherwise the task can race the dependency-teardown
    commit.
    """
    if prev_status == "complete" or case.review_status != "complete":
        return
    if case.plan_status == "planning":
        return
    case.plan_status = "planning"
    await db.commit()
    background_tasks.add_task(run_planner_background, case.id)


async def _claim_request(
    request_id: str, case_id: str, db: AsyncSession
) -> bool:
    """Atomically flip an OPEN request to an in-flight FULFILLED state.

    Returns True if the current caller won the race and should proceed
    with creating the EvidenceItem. Returns False if another caller has
    already claimed it (double-submit) — the caller should 409.

    We set the status to FULFILLED now (optimistic) and roll back in the
    caller's ``except`` path if anything downstream fails. The evidence_item_id
    is stamped by the caller once the item has been flushed.
    """
    stmt = (
        update(EvidenceRequest)
        .where(
            EvidenceRequest.id == request_id,
            EvidenceRequest.case_id == case_id,
            EvidenceRequest.status == EvidenceRequestStatus.OPEN,
        )
        .values(status=EvidenceRequestStatus.FULFILLED, fulfilled_at=datetime.utcnow())
        .execution_options(synchronize_session="fetch")
    )
    result = await db.execute(stmt)
    return result.rowcount == 1


def _sanitize_filename(raw: str | None) -> str:
    name = (raw or "upload").strip()
    # Strip any path components leading dots/dashes.
    name = os.path.basename(name).lstrip(".-")
    if not name:
        name = "upload"
    name = _SAFE_FILENAME_CHARS.sub("_", name)
    if len(name) > _MAX_FILENAME_LENGTH:
        # Keep the extension if there is one.
        base, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 12:
            keep = _MAX_FILENAME_LENGTH - len(ext) - 1
            name = f"{base[:keep]}.{ext}"
        else:
            name = name[:_MAX_FILENAME_LENGTH]
    return name


async def _stream_to_disk(
    file: UploadFile, dest_path: str, max_bytes: int
) -> int:
    """Stream the upload to `dest_path`, aborting if it exceeds max_bytes.

    Deletes the partial file on abort so the directory doesn't fill up.
    Returns total bytes written.
    """
    total = 0
    with open(dest_path, "wb") as out:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"File too large. Maximum size is "
                        f"{max_bytes // (1024 * 1024)} MB."
                    ),
                )
            out.write(chunk)
    return total


@router.get("", response_model=list[EvidenceRequestResponse])
async def list_evidence_requests(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_case_for_user(case_id, current_user, db)
    result = await db.execute(
        select(EvidenceRequest)
        .where(EvidenceRequest.case_id == case_id)
        .order_by(EvidenceRequest.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("/{request_id}/fulfill-text", response_model=EvidenceRequestResponse)
async def fulfill_with_text(
    case_id: str,
    request_id: str,
    payload: FulfillWithTextRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User describes the evidence in their own words (e.g., pasting email text).

    Creates an EvidenceItem with the provided content and links it to the request.
    """
    case, er = await _load_case_and_request(case_id, request_id, current_user, db)
    prev_status = case.review_status
    if er.status != EvidenceRequestStatus.OPEN:
        raise HTTPException(
            status_code=409, detail=f"Request already {er.status.value}"
        )
    # Atomic claim — returns False if another request already fulfilled this one.
    claimed = await _claim_request(request_id, case_id, db)
    if not claimed:
        raise HTTPException(status_code=409, detail="Request already resolved")

    item = EvidenceItem(
        case_id=case_id,
        title=payload.title or er.title,
        description=er.description,
        evidence_type=er.evidence_type,
        source_reference=payload.source_reference,
        content=payload.content,
        event_date=payload.event_date or er.expected_date,
        collected_by="user",
        source_request_id=er.id,
    )
    db.add(item)
    await db.flush()

    await db.refresh(er)  # pick up the status/fulfilled_at the update set
    er.evidence_item_id = item.id
    await refresh_review_status(case, db)
    await _maybe_fire_planner(case, prev_status, background_tasks, db)
    await db.flush()
    return er


@router.post("/{request_id}/fulfill-file", response_model=EvidenceRequestResponse)
async def fulfill_with_file(
    case_id: str,
    request_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source_reference: str | None = Form(default=None),
    event_date: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User attaches a file to fulfill the request.

    Streams the upload chunk-by-chunk with a hard size cap rather than
    buffering the whole body in memory.
    """
    case, er = await _load_case_and_request(case_id, request_id, current_user, db)
    prev_status = case.review_status
    if er.status != EvidenceRequestStatus.OPEN:
        raise HTTPException(
            status_code=409, detail=f"Request already {er.status.value}"
        )
    claimed = await _claim_request(request_id, case_id, db)
    if not claimed:
        raise HTTPException(status_code=409, detail="Request already resolved")

    upload_dir = os.path.join(settings.upload_dir, case_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_id = uuid.uuid4().hex[:8]
    safe_name = _sanitize_filename(file.filename)
    file_path = os.path.join(upload_dir, f"{file_id}_{safe_name}")

    try:
        bytes_written = await _stream_to_disk(file, file_path, MAX_UPLOAD_BYTES)
    except Exception:
        # Roll back the claim so the user can retry with a smaller file.
        er.status = EvidenceRequestStatus.OPEN
        er.fulfilled_at = None
        await db.flush()
        raise

    if bytes_written == 0:
        try:
            os.remove(file_path)
        except OSError:
            pass
        er.status = EvidenceRequestStatus.OPEN
        er.fulfilled_at = None
        await db.flush()
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    item = EvidenceItem(
        case_id=case_id,
        title=title or er.title,
        description=er.description,
        evidence_type=er.evidence_type,
        source_reference=source_reference,
        file_path=file_path,
        event_date=event_date or er.expected_date,
        collected_by="user",
        source_request_id=er.id,
    )
    db.add(item)
    await db.flush()

    await db.refresh(er)
    er.evidence_item_id = item.id
    await refresh_review_status(case, db)
    await _maybe_fire_planner(case, prev_status, background_tasks, db)
    await db.flush()
    return er


@router.post(
    "/{request_id}/mark-unavailable", response_model=EvidenceRequestResponse
)
async def mark_unavailable(
    case_id: str,
    request_id: str,
    payload: MarkUnavailableRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case, er = await _load_case_and_request(case_id, request_id, current_user, db)
    prev_status = case.review_status
    if er.status == EvidenceRequestStatus.FULFILLED:
        raise HTTPException(
            status_code=409, detail="Cannot mark a fulfilled request unavailable"
        )

    er.status = EvidenceRequestStatus.UNAVAILABLE
    er.unavailable_reason = (payload.reason or "").strip() or None
    er.fulfilled_at = datetime.utcnow()  # reused as "resolved_at"
    await refresh_review_status(case, db)
    await _maybe_fire_planner(case, prev_status, background_tasks, db)
    await db.flush()
    return er


@router.post("/{request_id}/dismiss", response_model=EvidenceRequestResponse)
async def dismiss_request(
    case_id: str,
    request_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case, er = await _load_case_and_request(case_id, request_id, current_user, db)
    prev_status = case.review_status
    if er.status == EvidenceRequestStatus.FULFILLED:
        raise HTTPException(
            status_code=409, detail="Cannot dismiss a fulfilled request"
        )

    er.status = EvidenceRequestStatus.DISMISSED
    er.fulfilled_at = datetime.utcnow()
    await refresh_review_status(case, db)
    await _maybe_fire_planner(case, prev_status, background_tasks, db)
    await db.flush()
    return er
