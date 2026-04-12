"""Chat endpoint — SSE streaming interface to the agent graph."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, APIKeyConfig
from app.models.case import Case
from app.models.message import ChatMessage
from app.api.auth import get_current_user
from app.schemas.chat import ChatRequest, ChatMessageResponse
from app.services.llm_router import create_chat_model
from app.agents.graph import build_case_graph, invoke_graph

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

    # Find config matching the requested tier, or fall back to any active key
    config = next((c for c in configs if c.model_tier == tier), configs[0])

    return create_chat_model(
        provider=config.provider,
        encrypted_key=config.encrypted_key,
        model_tier=config.model_tier,
        preferred_model=config.preferred_model,
    )


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

                # Emit any structured outputs
                if response.get("evidence_added"):
                    yield f"data: {json.dumps({'type': 'evidence_added', 'items': response['evidence_added']})}\n\n"
                if response.get("draft_generated"):
                    yield f"data: {json.dumps({'type': 'draft_generated', 'draft': response['draft_generated']})}\n\n"
                if response.get("next_steps"):
                    yield f"data: {json.dumps({'type': 'next_steps', 'steps': response['next_steps']})}\n\n"

            yield f"data: {json.dumps({'type': 'agent_end', 'agent': current_agent})}\n\n"

            # Save assistant message (after streaming completes)
            # Note: In production, this should be done after the stream is consumed
            # For now we save it here since we have the full response
            async with db.begin_nested():
                assistant_msg = ChatMessage(
                    case_id=case_id,
                    role="assistant",
                    agent_name=current_agent,
                    content=full_response,
                    metadata_json=response.get("metadata") if response else None,
                )
                db.add(assistant_msg)
                await db.flush()

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/messages", response_model=list[ChatMessageResponse])
async def get_messages(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get message history for a case."""
    # Verify case ownership
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
