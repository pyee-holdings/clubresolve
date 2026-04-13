"""Chat endpoint — SSE streaming interface to the agent graph."""

import json

from dateutil import parser as dateutil_parser
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, APIKeyConfig
from app.models.case import Case, CaseStatus
from app.models.message import ChatMessage
from app.models.evidence import EvidenceItem, TimelineEvent
from app.models.draft import Draft
from app.api.auth import get_current_user
from app.schemas.chat import ChatRequest, ChatMessageResponse
from app.services.llm_router import create_chat_model
from app.agents.graph import build_case_graph, invoke_graph


def _normalize_date(raw: str | None) -> str | None:
    """Parse a free-form date string into YYYY-MM-DD, or return None."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw or raw.lower() in ("unknown", "n/a", "none", "null", "?"):
        return None
    try:
        dt = dateutil_parser.parse(raw, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None

router = APIRouter(prefix="/api/cases/{case_id}", tags=["chat"])


async def _get_user_llm(user: User, db: AsyncSession, tier: str = "strong"):
    """Resolve the user's LLM from their BYOK config."""
    result = await db.execute(
        select(APIKeyConfig).where(
            APIKeyConfig.user_id == user.id,
            APIKeyConfig.is_active == True,  # noqa: E712
        )
    )
    configs = result.scalars().all()

    if not configs:
        raise HTTPException(
            status_code=400,
            detail="No API key configured. Please add an LLM API key in Settings.",
        )

    config = next((c for c in configs if c.model_tier == tier), configs[0])

    return create_chat_model(
        provider=config.provider,
        encrypted_key=config.encrypted_key,
        model_tier=config.model_tier,
        preferred_model=config.preferred_model,
    )


async def _sync_graph_results_to_db(case: Case, response: dict, db: AsyncSession):
    """Write agent graph results back to the database.

    Updates case status, next steps, evidence items, timeline events, and drafts.
    """
    metadata = response.get("metadata", {})

    # Update case status — move out of intake after first meaningful exchange
    if case.status == CaseStatus.INTAKE:
        case.status = CaseStatus.RESEARCHING

    # Update escalation level if changed
    if metadata.get("escalation_level") is not None:
        case.escalation_level = metadata["escalation_level"]

    # Update missing info
    if metadata.get("missing_info"):
        case.missing_info = metadata["missing_info"]

    # --- Load existing items for dedup ---
    existing_evidence = (await db.execute(
        select(EvidenceItem.title, EvidenceItem.event_date)
        .where(EvidenceItem.case_id == case.id)
    )).all()
    evidence_keys = {(row.title, row.event_date) for row in existing_evidence}

    existing_timeline = (await db.execute(
        select(TimelineEvent.description, TimelineEvent.event_date)
        .where(TimelineEvent.case_id == case.id)
    )).all()
    timeline_keys = {(row.description, row.event_date) for row in existing_timeline}

    existing_drafts = (await db.execute(
        select(Draft.title, Draft.draft_type)
        .where(Draft.case_id == case.id)
    )).all()
    draft_keys = {(row.title, row.draft_type) for row in existing_drafts}

    # Save evidence items from vault agent (with validation + dedup)
    evidence_items = response.get("evidence_added") or []
    _generic_sources = {"conversation context", "conversation", "context", "mentioned", "unknown", ""}
    for item in evidence_items:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        # Skip items without a real source reference — likely fabricated
        source_ref = (item.get("source_reference") or "").strip().lower()
        if not source_ref or source_ref in _generic_sources:
            continue
        # Normalize date
        event_date = _normalize_date(item.get("event_date"))
        # Dedup: skip if same title + date already exists
        if (item["title"], event_date) in evidence_keys:
            continue
        evidence = EvidenceItem(
            case_id=case.id,
            title=item.get("title", "Untitled"),
            description=item.get("description"),
            evidence_type=item.get("type", "note"),
            source_reference=item.get("source_reference"),
            content=item.get("content"),
            tags=item.get("tags"),
            event_date=event_date,
            collected_by="evidence_agent",
        )
        db.add(evidence)
        evidence_keys.add((item["title"], event_date))

    # Save timeline events from vault agent (with dedup)
    timeline_events = response.get("timeline_events") or []
    for event in timeline_events:
        if not isinstance(event, dict) or not event.get("description"):
            continue
        event_date = _normalize_date(event.get("event_date")) or "unknown"
        # Dedup
        if (event["description"], event_date) in timeline_keys:
            continue
        te = TimelineEvent(
            case_id=case.id,
            event_date=event_date,
            description=event["description"],
            source=event.get("source"),
            event_type=event.get("event_type"),
        )
        db.add(te)
        timeline_keys.add((event["description"], event_date))

    # Save drafts from drafts agent (with dedup)
    drafts = response.get("draft_generated") or []
    for draft_data in drafts:
        if not isinstance(draft_data, dict) or not draft_data.get("content"):
            continue
        title = draft_data.get("title", "Draft Communication")
        draft_type = draft_data.get("type", "email")
        # Dedup
        if (title, draft_type) in draft_keys:
            continue
        draft = Draft(
            case_id=case.id,
            draft_type=draft_type,
            title=title,
            content=draft_data["content"],
            recipient=draft_data.get("recipient"),
            tone=draft_data.get("tone", "professional"),
        )
        db.add(draft)
        draft_keys.add((title, draft_type))

    # Save legal summary
    legal_findings = response.get("legal_findings") or []
    if legal_findings:
        case.legal_summary = json.dumps(legal_findings)

    await db.flush()


@router.post("/chat")
async def chat(
    case_id: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and receive SSE-streamed agent response."""
    # Verify case ownership
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == current_user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Get user's LLM
    llm = await _get_user_llm(current_user, db)

    # Save user message
    user_msg = ChatMessage(
        case_id=case_id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    await db.flush()

    async def event_stream():
        """Generate SSE events from the agent graph."""
        try:
            full_response = ""
            current_agent = "navigator"

            yield f"data: {json.dumps({'type': 'agent_start', 'agent': current_agent})}\n\n"

            # Invoke the graph
            response = await invoke_graph(
                llm=llm,
                case=case,
                user_message=request.message,
                thread_id=case.langgraph_thread_id,
            )

            if response:
                full_response = response.get("response", "")
                current_agent = response.get("agent", "navigator")

                # Stream the response in chunks for a better UX
                chunk_size = 20
                for i in range(0, len(full_response), chunk_size):
                    chunk = full_response[i : i + chunk_size]
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk, 'agent': current_agent})}\n\n"

                # Emit structured outputs
                if response.get("evidence_added"):
                    yield f"data: {json.dumps({'type': 'evidence_added', 'items': response['evidence_added']})}\n\n"
                if response.get("draft_generated"):
                    yield f"data: {json.dumps({'type': 'draft_generated', 'draft': response['draft_generated']})}\n\n"

            yield f"data: {json.dumps({'type': 'agent_end', 'agent': current_agent})}\n\n"

            # Save assistant message and sync graph results to DB
            if response:
                async with db.begin_nested():
                    assistant_msg = ChatMessage(
                        case_id=case_id,
                        role="assistant",
                        agent_name=current_agent,
                        content=full_response,
                        metadata_json=response.get("metadata"),
                    )
                    db.add(assistant_msg)

                    # Sync evidence, timeline, drafts, status back to DB
                    await _sync_graph_results_to_db(case, response, db)

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/messages", response_model=list[ChatMessageResponse])
async def get_messages(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get message history for a case."""
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Case not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.case_id == case_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return result.scalars().all()
