"""Tests for the intake review service — prompt building, coercion, and
end-to-end generation with a mocked LLM and in-memory SQLite."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.case import Case
from app.models.question import CaseQuestion, QuestionPriority, QuestionStatus
from app.models.user import APIKeyConfig, User
from app.services.intake_review import (
    _coerce_question,
    build_review_prompt,
    generate_intake_questions,
)


# ── Pure helper tests ───────────────────────────────────


class TestCoerceQuestion:
    def test_accepts_well_formed(self):
        out = _coerce_question(
            {
                "question": "Who attended the board meeting on March 3?",
                "context": "Establishes witnesses.",
                "category": "people",
                "priority": "critical",
            }
        )
        assert out is not None
        assert out["category"] == "people"
        assert out["priority"] == "critical"
        assert out["context"] == "Establishes witnesses."

    def test_rejects_too_short(self):
        assert _coerce_question({"question": "X"}) is None

    def test_rejects_non_dict(self):
        assert _coerce_question("not a dict") is None
        assert _coerce_question(None) is None

    def test_unknown_category_becomes_general(self):
        out = _coerce_question(
            {"question": "Some long enough question?", "category": "weird_thing"}
        )
        assert out["category"] == "general"

    def test_unknown_priority_becomes_important(self):
        out = _coerce_question(
            {"question": "Some long enough question?", "priority": "panic"}
        )
        assert out["priority"] == "important"

    def test_missing_context_is_none(self):
        out = _coerce_question({"question": "Long enough?"})
        assert out["context"] is None


class TestBuildReviewPrompt:
    def test_includes_all_intake_fields(self):
        case = Case(
            user_id="u1",
            title="Coach benched my child",
            category="coaching",
            club_name="Sunset FC",
            sport="Soccer",
            description="He hasn't played in 4 games.",
            desired_outcome="Equal playing time",
            urgency="medium",
            risk_flags=["retaliation"],
            people_involved=[{"name": "Coach A", "role": "coach"}],
            prior_attempts="Spoke to the coach.",
            timeline_start="2026-02-01",
        )
        system, user = build_review_prompt(case)
        assert "advocacy support assistant" in system
        assert "3 to 8 questions" in system
        assert "evidence_requests" in system  # Phase B: LLM must emit this list too
        # User prompt should contain the concrete intake
        for fragment in [
            "Coach benched my child",
            "Sunset FC",
            "Soccer",
            "2026-02-01",
            "retaliation",
            "He hasn't played in 4 games.",
        ]:
            assert fragment in user, f"user prompt missing {fragment!r}"

    def test_handles_missing_optional_fields(self):
        case = Case(user_id="u1", title="Something happened")
        system, user = build_review_prompt(case)
        assert "Something happened" in user
        # Unprovided fields should render as a placeholder, not "None"
        assert "(not provided)" in user


# ── Service-level tests with in-memory DB ───────────────


@pytest.fixture
async def db_session():
    """Fresh in-memory SQLite with tables created for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _seed_user_case_key(session: AsyncSession) -> tuple[User, Case]:
    user = User(
        id="u-1",
        email="parent@example.com",
        name="Parent",
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    case = Case(
        user_id=user.id,
        title="My child was removed from the roster",
        category="eligibility",
        club_name="North Shore Hockey",
        sport="Hockey",
        description="Roster cut with no notice.",
        desired_outcome="Reinstatement",
        urgency="high",
    )
    session.add(case)
    session.add(
        APIKeyConfig(
            user_id=user.id,
            provider="anthropic",
            encrypted_key=b"encrypted",
            is_active=True,
        )
    )
    await session.commit()
    return user, case


class TestGenerateIntakeQuestions:
    @pytest.mark.asyncio
    async def test_happy_path_creates_questions_and_updates_status(self, db_session):
        _, case = await _seed_user_case_key(db_session)

        llm_payload = {
            "questions": [
                {
                    "question": "What specific reason was given for removing your child?",
                    "context": "Determines whether due process applies.",
                    "category": "policy",
                    "priority": "critical",
                },
                {
                    "question": "Do you have any written communications about the roster?",
                    "context": "Evidence is key.",
                    "category": "evidence",
                    "priority": "important",
                },
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(llm_payload)))
        ]

        with patch(
            "app.services.intake_review.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.intake_review.decrypt_api_key", return_value="test-key"
        ):
            result = await generate_intake_questions(case.id, db_session)

        assert result.questions_created == 2
        assert result.skipped_reason is None

        await db_session.refresh(case)
        assert case.review_status == "needs_input"

        # Questions persisted with correct attributes
        from sqlalchemy import select

        rows = (
            await db_session.execute(
                select(CaseQuestion).where(CaseQuestion.case_id == case.id)
            )
        ).scalars().all()
        assert len(rows) == 2
        critical = [q for q in rows if q.priority == QuestionPriority.CRITICAL]
        assert len(critical) == 1
        assert all(q.status == QuestionStatus.OPEN for q in rows)

    @pytest.mark.asyncio
    async def test_no_api_key_skips_cleanly(self, db_session):
        user = User(id="u-1", email="x@y.com", name="x", hashed_password="x")
        db_session.add(user)
        await db_session.flush()
        case = Case(user_id=user.id, title="No key case")
        db_session.add(case)
        await db_session.commit()

        result = await generate_intake_questions(case.id, db_session)
        assert result.questions_created == 0
        assert result.skipped_reason == "no_api_key"
        await db_session.refresh(case)
        assert case.review_status == "pending"

    @pytest.mark.asyncio
    async def test_already_reviewed_is_noop(self, db_session):
        _, case = await _seed_user_case_key(db_session)
        db_session.add(
            CaseQuestion(case_id=case.id, question="Prior question text here?")
        )
        await db_session.commit()

        result = await generate_intake_questions(case.id, db_session)
        assert result.questions_created == 0
        assert result.skipped_reason == "already_reviewed"

    @pytest.mark.asyncio
    async def test_llm_failure_leaves_case_pending(self, db_session):
        _, case = await _seed_user_case_key(db_session)

        with patch(
            "app.services.intake_review.litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ), patch(
            "app.services.intake_review.decrypt_api_key", return_value="test-key"
        ):
            result = await generate_intake_questions(case.id, db_session)

        assert result.questions_created == 0
        assert result.skipped_reason and result.skipped_reason.startswith("llm_error:")
        await db_session.refresh(case)
        assert case.review_status == "pending"

    @pytest.mark.asyncio
    async def test_malformed_questions_are_dropped(self, db_session):
        _, case = await _seed_user_case_key(db_session)

        llm_payload = {
            "questions": [
                {"question": "Valid long enough question?", "priority": "important"},
                {"question": "X"},  # too short
                "not a dict",
                {"question": "Another valid question", "category": "evidence"},
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(llm_payload)))
        ]

        with patch(
            "app.services.intake_review.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.intake_review.decrypt_api_key", return_value="test-key"
        ):
            result = await generate_intake_questions(case.id, db_session)

        assert result.questions_created == 2

    @pytest.mark.asyncio
    async def test_llm_returns_empty_list_marks_complete(self, db_session):
        _, case = await _seed_user_case_key(db_session)

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"questions": []})))
        ]

        with patch(
            "app.services.intake_review.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.intake_review.decrypt_api_key", return_value="test-key"
        ):
            result = await generate_intake_questions(case.id, db_session)

        assert result.questions_created == 0
        assert result.skipped_reason is None
        await db_session.refresh(case)
        # Nothing actionable came back, don't trap the user in needs_input
        assert case.review_status == "complete"
