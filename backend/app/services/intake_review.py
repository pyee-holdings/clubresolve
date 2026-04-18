"""Intake review service.

Takes a fresh case and produces a prioritized list of clarifying questions
that the user should answer before meaningful planning begins. Questions
land in the ``case_questions`` table as CaseQuestion rows.

Runs as a background task after case creation. Uses the user's BYOK key
via LiteLLM, mirroring the wizard action plan pattern.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.case import Case
from app.models.evidence_request import EvidenceRequest, EvidenceRequestStatus
from app.models.question import CaseQuestion, QuestionPriority, QuestionStatus
from app.models.user import APIKeyConfig
from app.schemas.evidence_request import EVIDENCE_TYPES
from app.services.crypto import decrypt_api_key
from app.services.llm_router import DEFAULT_MODELS, get_litellm_model_name

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 8
MAX_EVIDENCE_REQUESTS = 10
REVIEW_TIMEOUT_SECONDS = 60.0
VALID_CATEGORIES = {"people", "timeline", "evidence", "policy", "outcome", "general"}
VALID_PRIORITIES = {p.value for p in QuestionPriority}
VALID_EVIDENCE_PRIORITIES = {"critical", "important", "nice_to_have"}

# Accept only plausible ISO 8601 dates (YYYY-MM-DD, optionally with time).
# The LLM occasionally returns prose like "soon" or "last week" — we'd rather
# drop those than surface them as a date badge in the UI.
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$")


SYSTEM_PROMPT = """You are an advocacy support assistant helping a parent prepare their dispute with a BC youth sports club. You are NOT a lawyer and must never claim to provide legal advice.

Your job right now is narrow: read the parent's intake and produce TWO lists.

LIST 1: CLARIFYING QUESTIONS — facts only the parent can supply.
LIST 2: EVIDENCE REQUESTS — specific documents, emails, or records the parent should gather or attach.

RULES FOR QUESTIONS:
- 3 to 8 questions total. Fewer is better when the intake is detailed.
- Do NOT re-ask things the parent already told you.
- Be SPECIFIC. Bad: "Tell me more." Good: "You mentioned a board meeting — on what date, and who spoke against your position?"
- Every question gets a one-sentence `context` explaining WHY you're asking.
- `category` MUST be exactly one of: people, timeline, evidence, policy, outcome, general.
- `priority` MUST be exactly one of: critical, important, nice_to_have. At most 1-2 critical. Most should be important.
- If the intake mentions athlete safety, minors, or retaliation, make at least one question about it.

RULES FOR EVIDENCE REQUESTS:
- 2 to 8 evidence requests. Skip this list only if the intake is extremely sparse.
- Each request is a specific thing the parent likely has or can obtain. Good examples:
  - "The coach's email from the March 3 incident"
  - "Club bylaws — specifically the section on disciplinary hearings"
  - "Screenshot of the team chat where the decision was announced"
  - "Receipt or invoice for the registration fees in dispute"
- BAD examples (too vague): "any supporting documents", "other evidence".
- `evidence_type` MUST be exactly one of these strings: email, screenshot, document, receipt, correspondence, policy, note, contract, testimony, other.
- `expected_date` is OPTIONAL. Only include it if you know a specific date from the intake, and format strictly as YYYY-MM-DD. Otherwise set it to null — never include prose like "soon" or "last spring".
- `priority` MUST be exactly one of: critical, important, nice_to_have. Critical means the plan cannot proceed without it.
- If the parent mentioned a document they didn't share, ALWAYS include it here.

You MUST respond with valid JSON matching exactly this shape:
{
  "questions": [
    {
      "question": "string",
      "context": "string",
      "category": "people" | "timeline" | "evidence" | "policy" | "outcome" | "general",
      "priority": "critical" | "important" | "nice_to_have"
    }
  ],
  "evidence_requests": [
    {
      "title": "string — the specific item to gather",
      "description": "string — one sentence on why this matters",
      "evidence_type": "email" | "screenshot" | "document" | "receipt" | "correspondence" | "policy" | "note" | "contract" | "testimony" | "other",
      "expected_date": "YYYY-MM-DD" | null,
      "priority": "critical" | "important" | "nice_to_have"
    }
  ]
}

No prose outside the JSON. No markdown fences."""


USER_PROMPT_TEMPLATE = """A parent has just opened a new case. Here is everything they told us on intake:

Title: {title}
Category: {category}
Club / organization: {club_name}
Sport: {sport}
Urgency (self-reported): {urgency}
Risk flags (self-selected): {risk_flags}
People involved (self-reported): {people_involved}
Desired outcome: {desired_outcome}
What they've already tried: {prior_attempts}
When this started: {timeline_start}

Full description in their own words:
\"\"\"
{description}
\"\"\"

Produce both the clarifying questions AND the evidence requests now, as JSON."""


@dataclass
class ReviewResult:
    """What the service produced for a single case."""

    questions_created: int
    evidence_requests_created: int = 0
    skipped_reason: str | None = None  # non-None means the review was skipped


def _format_value(value) -> str:
    """Human-readable stringification for the user prompt."""
    if value is None or value == "":
        return "(not provided)"
    if isinstance(value, list):
        if not value:
            return "(none)"
        if all(isinstance(v, str) for v in value):
            return ", ".join(value)
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_review_prompt(case: Case) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) from a case."""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=_format_value(case.title),
        category=_format_value(case.category),
        club_name=_format_value(case.club_name),
        sport=_format_value(case.sport),
        urgency=_format_value(case.urgency),
        risk_flags=_format_value(case.risk_flags),
        people_involved=_format_value(case.people_involved),
        desired_outcome=_format_value(case.desired_outcome),
        prior_attempts=_format_value(case.prior_attempts),
        timeline_start=_format_value(case.timeline_start),
        description=_format_value(case.description),
    )
    return SYSTEM_PROMPT, user_prompt


def _coerce_question(raw: dict) -> dict | None:
    """Validate + normalize one question from the LLM. Returns None to drop it."""
    if not isinstance(raw, dict):
        return None
    question = (raw.get("question") or "").strip()
    if len(question) < 3:
        return None
    category = (raw.get("category") or "general").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "general"
    priority = (raw.get("priority") or "important").strip().lower()
    if priority not in VALID_PRIORITIES:
        priority = "important"
    context = raw.get("context")
    if context is not None:
        context = str(context).strip() or None
    return {
        "question": question[:2000],
        "context": (context[:2000] if context else None),
        "category": category,
        "priority": priority,
    }


def _coerce_evidence_request(raw: dict) -> dict | None:
    """Validate + normalize one evidence request from the LLM."""
    if not isinstance(raw, dict):
        return None
    title = (raw.get("title") or "").strip()
    if len(title) < 3:
        return None
    description = raw.get("description")
    if description is not None:
        description = str(description).strip() or None
    evidence_type = (raw.get("evidence_type") or "document").strip().lower()
    if evidence_type not in EVIDENCE_TYPES:
        evidence_type = "document"
    priority = (raw.get("priority") or "important").strip().lower()
    if priority not in VALID_EVIDENCE_PRIORITIES:
        priority = "important"
    expected_date = raw.get("expected_date")
    if expected_date is not None:
        expected_date = str(expected_date).strip() or None
        if expected_date and not _ISO_DATE_RE.match(expected_date):
            # Prose dates like "soon" or "last spring" aren't usable as badges.
            expected_date = None
    return {
        "title": title[:500],
        "description": (description[:2000] if description else None),
        "evidence_type": evidence_type,
        "priority": priority,
        "expected_date": expected_date,
    }


async def _call_llm(
    case: Case, key_config: APIKeyConfig
) -> tuple[list[dict], list[dict]]:
    """Call the LLM and return (raw_questions, raw_evidence_requests).
    Caller handles validation + persistence."""
    api_key = decrypt_api_key(key_config.encrypted_key)
    model_name = key_config.preferred_model or DEFAULT_MODELS.get(
        key_config.provider, {}
    ).get("strong", "")
    if not model_name:
        raise ValueError(f"No default model for provider={key_config.provider}")

    litellm_model = get_litellm_model_name(key_config.provider, model_name)
    system_prompt, user_prompt = build_review_prompt(case)

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
        timeout=REVIEW_TIMEOUT_SECONDS,
    )
    content = response.choices[0].message.content
    parsed = json.loads(content)

    questions = parsed.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError("LLM response missing 'questions' array")

    evidence_requests = parsed.get("evidence_requests", [])
    if not isinstance(evidence_requests, list):
        # Tolerate omission rather than fail — the questions may still be useful.
        evidence_requests = []

    return questions[:MAX_QUESTIONS], evidence_requests[:MAX_EVIDENCE_REQUESTS]


async def generate_intake_questions(
    case_id: str,
    db: AsyncSession,
) -> ReviewResult:
    """Run the intake review for one case, persisting questions and updating
    case.review_status. Idempotent on re-run in the sense that it overwrites
    nothing: if the case already has questions, the review is skipped.

    Exceptions are logged and translated into a failed result, not raised —
    this runs as a background task and must never crash the server.
    """
    # Fetch case
    case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
    if case is None:
        return ReviewResult(questions_created=0, skipped_reason="case_not_found")

    # If intake review already produced questions or evidence requests, skip.
    existing_q = (
        await db.execute(select(CaseQuestion).where(CaseQuestion.case_id == case_id))
    ).scalars().first()
    existing_e = (
        await db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case_id))
    ).scalars().first()
    if existing_q is not None or existing_e is not None:
        return ReviewResult(questions_created=0, skipped_reason="already_reviewed")

    # Fetch user's API key
    key_config = (
        await db.execute(
            select(APIKeyConfig).where(
                APIKeyConfig.user_id == case.user_id,
                APIKeyConfig.is_active == True,
            )
        )
    ).scalar_one_or_none()
    if key_config is None:
        case.review_status = "pending"  # user needs to add a key; leave pending
        await db.commit()
        return ReviewResult(questions_created=0, skipped_reason="no_api_key")

    # Mark reviewing
    case.review_status = "reviewing"
    await db.commit()

    try:
        raw_questions, raw_evidence = await _call_llm(case, key_config)
    except asyncio.TimeoutError:
        logger.warning("Intake review timed out for case %s", case_id)
        case.review_status = "pending"
        await db.commit()
        return ReviewResult(questions_created=0, skipped_reason="llm_timeout")
    except Exception as e:  # bubble to a sane state; don't crash the worker
        logger.exception("Intake review failed for case %s: %s", case_id, e)
        case.review_status = "pending"
        await db.commit()
        return ReviewResult(questions_created=0, skipped_reason=f"llm_error:{type(e).__name__}")

    # Persist questions
    q_created = 0
    for raw in raw_questions:
        norm = _coerce_question(raw)
        if norm is None:
            continue
        q = CaseQuestion(
            case_id=case_id,
            question=norm["question"],
            context=norm["context"],
            category=norm["category"],
            priority=QuestionPriority(norm["priority"]),
            generated_by="intake_review_agent",
            status=QuestionStatus.OPEN,
        )
        db.add(q)
        q_created += 1

    # Persist evidence requests
    e_created = 0
    for raw in raw_evidence:
        norm = _coerce_evidence_request(raw)
        if norm is None:
            continue
        er = EvidenceRequest(
            case_id=case_id,
            title=norm["title"],
            description=norm["description"],
            evidence_type=norm["evidence_type"],
            expected_date=norm["expected_date"],
            priority=norm["priority"],
            generated_by="intake_review_agent",
            status=EvidenceRequestStatus.OPEN,
        )
        db.add(er)
        e_created += 1

    if q_created > 0 or e_created > 0:
        case.review_status = "needs_input"
    else:
        # Model returned nothing we could parse; don't block the user.
        case.review_status = "complete"
    await db.commit()
    return ReviewResult(
        questions_created=q_created, evidence_requests_created=e_created
    )


async def run_intake_review_background(case_id: str) -> None:
    """Entry point for FastAPI BackgroundTasks. Opens its own DB session so
    it's safe to run after the request that triggered it has returned."""
    async with async_session() as session:
        try:
            await generate_intake_questions(case_id, session)
        except Exception:
            logger.exception("Unhandled error in background intake review for %s", case_id)
