"""Strategic planner service.

Reads the full state of a case — intake, answered questions, dismissed
questions, vault evidence items, open/unavailable evidence requests — and
produces a current action plan. Persists to existing Case fields
(strategy_plan, next_steps, escalation_level, missing_info) so the
Strategy sidebar and the chat agents see the same picture.

Two invocation paths:
  - Automatic: fired after intake review completes successfully.
  - Manual: POST /api/cases/:id/plan/regenerate.

Both go through ``run_planner_background`` so the HTTP path returns fast.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime

import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.case import Case
from app.models.evidence import EvidenceItem
from app.models.evidence_request import EvidenceRequest, EvidenceRequestStatus
from app.models.question import CaseQuestion, QuestionStatus
from app.models.user import APIKeyConfig
from app.services.crypto import decrypt_api_key
from app.services.llm_router import DEFAULT_MODELS, get_litellm_model_name

logger = logging.getLogger(__name__)

PLANNER_TIMEOUT_SECONDS = 60.0
MAX_NEXT_STEPS = 6
VALID_STEP_PRIORITIES = {"critical", "important", "nice_to_have"}


SYSTEM_PROMPT = """You are an advocacy support assistant helping a parent navigate a dispute with a BC youth sports club. You are NOT a lawyer and must never claim to provide legal advice.

Your job now is to read everything we know about this case and produce a **current, concrete action plan**. The parent will see this plan as their guidance for what to do next.

CONTEXT QUALITY VARIES:
- Some questions have been answered by the parent; others are still open or were dismissed.
- Some evidence has been uploaded; some was requested but is unavailable; some requests are still open.
- The plan must work for this *actual* state of knowledge — do not assume facts not in evidence.
- If the intake is extremely sparse (no description, no answered questions, no evidence), it is acceptable to return as few as 1-2 next steps — focus them on gathering the minimum needed to plan properly, and fill `missing_info` with what you need.

OUTPUT RULES:
- `strategy_plan`: 1-2 paragraphs explaining the recommended strategy, written to the parent in second person ("You have...", "Your next step is..."). Reference the specific facts we know. Acknowledge what's still unknown if it matters.
- `next_steps`: 1-6 concrete, specific actions the parent should take in order. Prefer 3-6 when you have enough context; 1-2 is acceptable only when the intake is very sparse. Each step must have:
  - `step`: What to do (one sentence, imperative).
  - `why`: Why this step matters to the strategy (one sentence).
  - `due`: When to do it (e.g. "This week", "Before the Oct 15 meeting", or a specific date YYYY-MM-DD when known). Never null — always give a concrete timeframe.
  - `priority`: critical | important | nice_to_have. Use "critical" only when skipping it jeopardizes the case (e.g., a deadline).
- `escalation_level`: integer 0-3.
  - 0 = internal (talk to coach/staff/board)
  - 1 = governing body (sport's provincial organization)
  - 2 = formal complaint (registrar, safe sport, regulator)
  - 3 = legal
  Pick the LOWEST level still useful. Most cases start at 0.
- `missing_info`: up to 5 items, each a short phrase naming a specific gap that would strengthen the plan if filled. Null/empty if nothing material is missing.

IMPORTANT:
- Use specific references to the parent's facts ("the March 3 email", "the missed registration deadline", etc.) — NOT generic advice.
- If critical evidence is unavailable, shape the plan around workarounds rather than pretending the evidence exists.
- If the parent mentioned athlete safety, retaliation, or a minor at risk, weight safety higher than procedure in the plan.

You MUST respond with valid JSON matching exactly this shape:
{
  "strategy_plan": "string",
  "next_steps": [
    {
      "step": "string",
      "why": "string",
      "due": "string",
      "priority": "critical" | "important" | "nice_to_have"
    }
  ],
  "escalation_level": 0,
  "missing_info": ["string"]
}

No prose outside the JSON. No markdown fences."""


@dataclass
class PlannerResult:
    updated: bool
    skipped_reason: str | None = None


def _fmt_list(value) -> str:
    if not value:
        return "(none)"
    if isinstance(value, list):
        if all(isinstance(v, str) for v in value):
            return "\n  - " + "\n  - ".join(value)
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _fmt_question(q: CaseQuestion) -> str:
    label = q.category.upper()
    prio = q.priority.value.upper() if hasattr(q.priority, "value") else str(q.priority).upper()
    if q.status == QuestionStatus.ANSWERED:
        return f"[{label}/{prio}] Q: {q.question}\n    A: {q.answer or '(empty)'}"
    if q.status == QuestionStatus.DISMISSED:
        note = q.answer or "(dismissed, no reason given)"
        return f"[{label}/{prio}] Q: {q.question}\n    DISMISSED: {note}"
    return f"[{label}/{prio}] Q: {q.question}\n    (unanswered)"


def _fmt_evidence_item(e: EvidenceItem) -> str:
    parts = [f"[{e.evidence_type.upper()}] {e.title}"]
    if e.event_date:
        parts.append(f"({e.event_date})")
    line = " ".join(parts)
    snippet = ""
    if e.content:
        body = e.content.strip()
        snippet = body if len(body) <= 400 else body[:400] + "...(truncated)"
    elif e.file_path:
        snippet = f"(file attached: {e.file_path.rsplit('/', 1)[-1]})"
    if snippet:
        return f"{line}\n    {snippet}"
    return line


def _fmt_request(r: EvidenceRequest) -> str:
    label = r.priority.upper()
    if r.status == EvidenceRequestStatus.UNAVAILABLE:
        reason = r.unavailable_reason or "(no reason)"
        return f"[{label}/UNAVAILABLE] {r.title} — {reason}"
    return f"[{label}/OPEN] {r.title}"


def build_planner_prompt(
    case: Case,
    questions: list[CaseQuestion],
    evidence_items: list[EvidenceItem],
    evidence_requests: list[EvidenceRequest],
) -> tuple[str, str]:
    answered = [q for q in questions if q.status == QuestionStatus.ANSWERED]
    dismissed = [q for q in questions if q.status == QuestionStatus.DISMISSED]
    open_q = [q for q in questions if q.status == QuestionStatus.OPEN]

    open_requests = [
        r for r in evidence_requests if r.status == EvidenceRequestStatus.OPEN
    ]
    unavailable_requests = [
        r for r in evidence_requests if r.status == EvidenceRequestStatus.UNAVAILABLE
    ]

    parts = [
        "CASE INTAKE",
        f"Title: {case.title}",
        f"Category: {case.category or '(not set)'}",
        f"Club: {case.club_name or '(not set)'}",
        f"Sport: {case.sport or '(not set)'}",
        f"Urgency (self-reported): {case.urgency}",
        f"Desired outcome: {case.desired_outcome or '(not set)'}",
        f"Risk flags: {_fmt_list(case.risk_flags)}",
        f"People involved: {_fmt_list(case.people_involved)}",
        f"Prior attempts: {case.prior_attempts or '(none listed)'}",
        f"Timeline start: {case.timeline_start or '(not set)'}",
        "",
        "Description (parent's own words):",
        case.description or "(not provided)",
        "",
    ]

    parts.append("CLARIFYING QUESTIONS")
    if answered:
        parts.append("-- Answered --")
        for q in answered:
            parts.append(_fmt_question(q))
    if dismissed:
        parts.append("-- Dismissed --")
        for q in dismissed:
            parts.append(_fmt_question(q))
    if open_q:
        parts.append("-- Still open (not yet answered) --")
        for q in open_q:
            parts.append(_fmt_question(q))
    if not (answered or dismissed or open_q):
        parts.append("(no intake review has run yet)")
    parts.append("")

    parts.append("EVIDENCE IN THE VAULT")
    if evidence_items:
        for e in evidence_items:
            parts.append(_fmt_evidence_item(e))
    else:
        parts.append("(nothing yet)")
    parts.append("")

    parts.append("EVIDENCE REQUESTS STILL OUTSTANDING OR KNOWN UNAVAILABLE")
    if open_requests or unavailable_requests:
        for r in open_requests + unavailable_requests:
            parts.append(_fmt_request(r))
    else:
        parts.append("(no outstanding or unavailable requests)")
    parts.append("")

    parts.append(
        "Produce the action plan now, as JSON. Shape the plan around what we actually know — "
        "don't invent facts. If key evidence is missing or unavailable, say so in "
        "`missing_info` and shape the next steps around it."
    )

    user_prompt = "\n".join(parts)
    return SYSTEM_PROMPT, user_prompt


async def _call_llm(
    system_prompt: str, user_prompt: str, key_config: APIKeyConfig
) -> dict:
    api_key = decrypt_api_key(key_config.encrypted_key)
    model_name = key_config.preferred_model or DEFAULT_MODELS.get(
        key_config.provider, {}
    ).get("strong", "")
    if not model_name:
        raise ValueError(f"No default model for provider={key_config.provider}")
    litellm_model = get_litellm_model_name(key_config.provider, model_name)

    response = await asyncio.wait_for(
        litellm.acompletion(
            model=litellm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=3072,
            temperature=0.3,
            api_key=api_key,
            response_format={"type": "json_object"},
        ),
        timeout=PLANNER_TIMEOUT_SECONDS,
    )
    return json.loads(response.choices[0].message.content)


def _coerce_step(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    step = (raw.get("step") or "").strip()
    if len(step) < 3:
        return None
    why = (raw.get("why") or "").strip() or None
    due = (raw.get("due") or "").strip() or None
    priority = (raw.get("priority") or "important").strip().lower()
    if priority not in VALID_STEP_PRIORITIES:
        priority = "important"
    # The prompt requires a concrete timeframe; if the LLM slips and returns
    # nothing, show "Soon" rather than leaving the UI badge blank.
    return {
        "step": step[:500],
        "why": (why[:500] if why else None),
        "due": (due[:100] if due else "Soon"),
        "priority": priority,
    }


def _coerce_plan(raw: dict) -> dict:
    """Trim + validate the LLM's plan payload into stored shape."""
    strategy_plan = (raw.get("strategy_plan") or "").strip() or None

    steps_raw = raw.get("next_steps") or []
    steps: list[dict] = []
    if isinstance(steps_raw, list):
        for s in steps_raw[:MAX_NEXT_STEPS]:
            norm = _coerce_step(s)
            if norm:
                steps.append(norm)

    try:
        level = int(raw.get("escalation_level", 0))
    except (TypeError, ValueError):
        level = 0
    level = max(0, min(3, level))

    missing_raw = raw.get("missing_info") or []
    missing: list[str] = []
    if isinstance(missing_raw, list):
        # Filter valid strings first, then cap — so invalid entries at the
        # start don't cause valid later entries to be dropped.
        for item in missing_raw:
            if isinstance(item, str) and item.strip():
                missing.append(item.strip()[:300])
            if len(missing) >= 5:
                break

    return {
        "strategy_plan": strategy_plan,
        "next_steps": steps,
        "escalation_level": level,
        "missing_info": missing,
    }


async def generate_plan(case_id: str, db: AsyncSession) -> PlannerResult:
    """Re-run the strategic planner for one case, persisting results to
    the existing Case fields. Never raises — background-task safe."""
    case = (
        await db.execute(select(Case).where(Case.id == case_id))
    ).scalar_one_or_none()
    if case is None:
        return PlannerResult(updated=False, skipped_reason="case_not_found")

    key_config = (
        await db.execute(
            select(APIKeyConfig).where(
                APIKeyConfig.user_id == case.user_id,
                APIKeyConfig.is_active == True,
            )
        )
    ).scalar_one_or_none()
    if key_config is None:
        # Reset plan_status so the UI doesn't get stuck showing "planning".
        if case.plan_status == "planning":
            case.plan_status = "idle"
            await db.commit()
        return PlannerResult(updated=False, skipped_reason="no_api_key")

    questions = (
        await db.execute(
            select(CaseQuestion).where(CaseQuestion.case_id == case_id)
        )
    ).scalars().all()
    evidence_items = (
        await db.execute(
            select(EvidenceItem).where(EvidenceItem.case_id == case_id)
        )
    ).scalars().all()
    evidence_requests = (
        await db.execute(
            select(EvidenceRequest).where(EvidenceRequest.case_id == case_id)
        )
    ).scalars().all()

    case.plan_status = "planning"
    await db.commit()

    system_prompt, user_prompt = build_planner_prompt(
        case, list(questions), list(evidence_items), list(evidence_requests)
    )

    try:
        raw = await _call_llm(system_prompt, user_prompt, key_config)
    except asyncio.TimeoutError:
        logger.warning("Strategic planner timed out for case %s", case_id)
        case.plan_status = "error"
        await db.commit()
        return PlannerResult(updated=False, skipped_reason="llm_timeout")
    except Exception as e:
        logger.exception("Strategic planner failed for case %s: %s", case_id, e)
        case.plan_status = "error"
        await db.commit()
        return PlannerResult(updated=False, skipped_reason=f"llm_error:{type(e).__name__}")

    plan = _coerce_plan(raw)

    # Persist into canonical Case fields so the chat agents and sidebar
    # share one source of truth for the plan.
    case.strategy_plan = plan["strategy_plan"] or case.strategy_plan
    case.next_steps = plan["next_steps"] or None
    case.escalation_level = plan["escalation_level"]
    case.missing_info = plan["missing_info"] or None
    case.plan_generated_at = datetime.utcnow()
    case.plan_status = "ready"
    await db.commit()
    return PlannerResult(updated=True)


async def run_planner_background(case_id: str) -> None:
    """FastAPI BackgroundTasks entry point."""
    async with async_session() as session:
        try:
            await generate_plan(case_id, session)
        except Exception:
            logger.exception("Unhandled error in background planner for %s", case_id)
