"""Tests for the strategic planner — prompt building, plan coercion, and
service-level behavior with a mocked LLM + in-memory SQLite."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.case import Case
from app.models.evidence import EvidenceItem
from app.models.evidence_request import EvidenceRequest, EvidenceRequestStatus
from app.models.question import CaseQuestion, QuestionPriority, QuestionStatus
from app.models.user import APIKeyConfig, User
from app.services.strategic_planner import (
    _coerce_plan,
    _coerce_step,
    build_planner_prompt,
    generate_plan,
)


# ── Pure helper tests ───────────────────────────────────


class TestCoerceStep:
    def test_rejects_short_step(self):
        assert _coerce_step({"step": "X"}) is None

    def test_priority_defaults_to_important(self):
        out = _coerce_step({"step": "Send the letter to the coach"})
        assert out["priority"] == "important"

    def test_unknown_priority_becomes_important(self):
        out = _coerce_step(
            {"step": "Do the thing", "priority": "panic"}
        )
        assert out["priority"] == "important"

    def test_preserves_why_and_due(self):
        out = _coerce_step(
            {
                "step": "Send the letter",
                "why": "Establishes a paper trail",
                "due": "This week",
                "priority": "critical",
            }
        )
        assert out["why"] == "Establishes a paper trail"
        assert out["due"] == "This week"
        assert out["priority"] == "critical"


class TestCoercePlan:
    def test_clamps_escalation_level(self):
        assert _coerce_plan({"escalation_level": 7})["escalation_level"] == 3
        assert _coerce_plan({"escalation_level": -4})["escalation_level"] == 0
        assert _coerce_plan({"escalation_level": "nope"})["escalation_level"] == 0

    def test_empty_input_produces_safe_plan(self):
        plan = _coerce_plan({})
        assert plan["strategy_plan"] is None
        assert plan["next_steps"] == []
        assert plan["escalation_level"] == 0
        assert plan["missing_info"] == []

    def test_drops_bad_steps_keeps_good_ones(self):
        plan = _coerce_plan(
            {
                "next_steps": [
                    {"step": "valid enough step"},
                    {"step": "X"},
                    "not a dict",
                    {"step": "another valid step", "priority": "critical"},
                ]
            }
        )
        assert len(plan["next_steps"]) == 2

    def test_caps_next_steps_to_max(self):
        plan = _coerce_plan(
            {"next_steps": [{"step": f"step number {i}"} for i in range(20)]}
        )
        assert len(plan["next_steps"]) <= 6

    def test_drops_empty_missing_info_items(self):
        plan = _coerce_plan(
            {"missing_info": ["real gap", "", "  ", 123, None, "another gap"]}
        )
        assert plan["missing_info"] == ["real gap", "another gap"]

    def test_missing_info_capped(self):
        plan = _coerce_plan(
            {"missing_info": [f"item {i}" for i in range(20)]}
        )
        assert len(plan["missing_info"]) <= 5

    def test_due_defaults_to_soon(self):
        out = _coerce_step({"step": "Do the thing"})
        assert out["due"] == "Soon"


class TestBuildPlannerPrompt:
    def test_includes_case_intake(self):
        case = Case(
            user_id="u1",
            title="Coach yelled at my child",
            category="safety",
            club_name="Sunset FC",
            sport="Soccer",
            description="Happened at practice.",
            urgency="high",
        )
        system, user = build_planner_prompt(case, [], [], [])
        assert "advocacy support" in system
        assert "Sunset FC" in user
        assert "Coach yelled at my child" in user

    def test_labels_open_and_answered_questions(self):
        case = Case(user_id="u1", title="Case")
        answered = CaseQuestion(
            case_id="x",
            question="Who saw it?",
            priority=QuestionPriority.IMPORTANT,
            status=QuestionStatus.ANSWERED,
            answer="Me and another parent",
            category="people",
        )
        unanswered = CaseQuestion(
            case_id="x",
            question="Was there a report filed?",
            priority=QuestionPriority.IMPORTANT,
            status=QuestionStatus.OPEN,
            category="policy",
        )
        _, user = build_planner_prompt(case, [answered, unanswered], [], [])
        assert "-- Answered --" in user
        assert "Me and another parent" in user
        assert "-- Still open" in user
        assert "Was there a report filed?" in user

    def test_surfaces_unavailable_evidence(self):
        case = Case(user_id="u1", title="Case")
        unavailable = EvidenceRequest(
            case_id="x",
            title="Email from coach",
            status=EvidenceRequestStatus.UNAVAILABLE,
            unavailable_reason="Deleted by coach",
            priority="critical",
        )
        _, user = build_planner_prompt(case, [], [], [unavailable])
        assert "UNAVAILABLE" in user
        assert "Deleted by coach" in user

    def test_no_content_leakage_beyond_truncation(self):
        """Huge evidence content should be truncated, not dumped wholesale."""
        case = Case(user_id="u1", title="Case")
        huge = EvidenceItem(
            case_id="x",
            title="Minutes",
            evidence_type="document",
            content="x" * 10_000,
        )
        _, user = build_planner_prompt(case, [], [huge], [])
        assert "...(truncated)" in user
        # The full 10k chars should NOT be in the prompt
        assert len([c for c in user if c == "x"]) < 10_000


# ── Service-level tests with in-memory DB ───────────────


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _seed(session: AsyncSession) -> tuple[User, Case]:
    user = User(id="u-1", email="p@x.com", name="p", hashed_password="x")
    session.add(user)
    await session.flush()
    case = Case(
        user_id=user.id,
        title="Roster cut",
        category="eligibility",
        description="Child removed without notice.",
    )
    session.add(case)
    session.add(
        APIKeyConfig(
            user_id=user.id,
            provider="anthropic",
            encrypted_key=b"enc",
            is_active=True,
        )
    )
    await session.commit()
    return user, case


class TestGeneratePlan:
    @pytest.mark.asyncio
    async def test_happy_path_populates_case(self, db_session):
        _, case = await _seed(db_session)

        llm_payload = {
            "summary": "You have several records-access routes.",
            "strategy_plan": "Start by requesting the records. Escalate if refused.",
            "next_steps": [
                {
                    "step": "Email the registrar",
                    "why": "Establishes the paper trail",
                    "due": "This week",
                    "priority": "critical",
                },
                {
                    "step": "Copy the board president",
                    "why": "Raises visibility",
                    "due": "Same email",
                    "priority": "important",
                },
            ],
            "escalation_level": 0,
            "escalation_ladder": [
                {
                    "level": 1,
                    "action": "Contact the PSO",
                    "trigger": "No response in 14 days",
                }
            ],
            "missing_info": ["Club bylaws section 4"],
            "confidence": "medium",
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(llm_payload)))
        ]

        with patch(
            "app.services.strategic_planner.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.strategic_planner.decrypt_api_key", return_value="k"
        ):
            result = await generate_plan(case.id, db_session)

        assert result.updated is True
        assert result.skipped_reason is None

        await db_session.refresh(case)
        assert case.plan_status == "ready"
        assert case.plan_generated_at is not None
        assert "Start by requesting" in case.strategy_plan
        assert case.next_steps and len(case.next_steps) == 2
        assert case.escalation_level == 0
        assert case.missing_info == ["Club bylaws section 4"]

    @pytest.mark.asyncio
    async def test_no_api_key_skips(self, db_session):
        user = User(id="u-1", email="x@y.com", name="x", hashed_password="x")
        db_session.add(user)
        await db_session.flush()
        case = Case(user_id=user.id, title="Keyless case")
        db_session.add(case)
        await db_session.commit()

        result = await generate_plan(case.id, db_session)
        assert result.updated is False
        assert result.skipped_reason == "no_api_key"
        await db_session.refresh(case)
        # Shouldn't have mutated the plan fields.
        assert case.plan_status == "idle"

    @pytest.mark.asyncio
    async def test_no_api_key_resets_planning_status(self, db_session):
        """If the endpoint set plan_status=planning but the user has no key,
        we must flip it back to idle so the UI doesn't spin forever."""
        user = User(id="u-1", email="x@y.com", name="x", hashed_password="x")
        db_session.add(user)
        await db_session.flush()
        case = Case(user_id=user.id, title="Keyless case", plan_status="planning")
        db_session.add(case)
        await db_session.commit()

        await generate_plan(case.id, db_session)
        await db_session.refresh(case)
        assert case.plan_status == "idle"

    @pytest.mark.asyncio
    async def test_llm_failure_sets_error_status(self, db_session):
        _, case = await _seed(db_session)

        with patch(
            "app.services.strategic_planner.litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ), patch(
            "app.services.strategic_planner.decrypt_api_key", return_value="k"
        ):
            result = await generate_plan(case.id, db_session)

        assert result.updated is False
        assert result.skipped_reason and result.skipped_reason.startswith("llm_error:")
        await db_session.refresh(case)
        assert case.plan_status == "error"

    @pytest.mark.asyncio
    async def test_preserves_existing_strategy_when_llm_returns_empty(
        self, db_session
    ):
        """If the LLM returns no strategy_plan and no steps, keep the
        previous plan narrative rather than wiping it."""
        _, case = await _seed(db_session)
        case.strategy_plan = "previous plan"
        await db_session.commit()

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({"next_steps": []})
                )
            )
        ]
        with patch(
            "app.services.strategic_planner.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.strategic_planner.decrypt_api_key", return_value="k"
        ):
            await generate_plan(case.id, db_session)

        await db_session.refresh(case)
        assert case.strategy_plan == "previous plan"
        assert case.next_steps is None
