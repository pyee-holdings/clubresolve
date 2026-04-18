"""Tests for EvidenceRequest — intake review extension, coercion, and
service-level fulfillment behavior with in-memory SQLite."""

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
from app.services.intake_review import (
    _coerce_evidence_request,
    generate_intake_questions,
)
from app.services.review_status import refresh_review_status


# ── Pure helper tests ───────────────────────────────────


class TestCoerceEvidenceRequest:
    def test_accepts_well_formed(self):
        out = _coerce_evidence_request(
            {
                "title": "Email from coach on March 3",
                "description": "Establishes what was said about playing time.",
                "evidence_type": "email",
                "expected_date": "2026-03-03",
                "priority": "critical",
            }
        )
        assert out is not None
        assert out["evidence_type"] == "email"
        assert out["priority"] == "critical"
        assert out["expected_date"] == "2026-03-03"

    def test_rejects_short_title(self):
        assert _coerce_evidence_request({"title": "x"}) is None

    def test_unknown_evidence_type_becomes_document(self):
        out = _coerce_evidence_request(
            {"title": "Some item", "evidence_type": "voodoo"}
        )
        assert out["evidence_type"] == "document"

    def test_unknown_priority_becomes_important(self):
        out = _coerce_evidence_request(
            {"title": "Some item", "priority": "panic"}
        )
        assert out["priority"] == "important"

    def test_missing_fields_get_defaults(self):
        out = _coerce_evidence_request({"title": "Bylaws section 4.2"})
        assert out["evidence_type"] == "document"
        assert out["priority"] == "important"
        assert out["expected_date"] is None
        assert out["description"] is None

    def test_iso_date_preserved(self):
        out = _coerce_evidence_request(
            {"title": "Thing", "expected_date": "2026-03-03"}
        )
        assert out["expected_date"] == "2026-03-03"

    def test_prose_date_dropped(self):
        """Non-ISO values like 'soon' or 'last week' should not survive."""
        for bad in ["soon", "last week", "march 3rd", "2026", "3/15/2026"]:
            out = _coerce_evidence_request(
                {"title": "Thing", "expected_date": bad}
            )
            assert out["expected_date"] is None, f"didn't drop {bad!r}"


class TestFilenameSanitization:
    """Phase B upload security — filenames from the client must be defanged."""

    def setup_method(self):
        from app.api.evidence_requests import _sanitize_filename

        self._sanitize = _sanitize_filename

    def test_simple_name_passes(self):
        assert self._sanitize("minutes.pdf") == "minutes.pdf"

    def test_strips_path_traversal(self):
        assert "/" not in self._sanitize("../../etc/passwd")
        assert "\\" not in self._sanitize("..\\..\\windows\\system32\\config.sam")

    def test_strips_leading_dots(self):
        assert not self._sanitize(".hidden.txt").startswith(".")

    def test_null_byte_removed(self):
        out = self._sanitize("foo\x00.sh")
        assert "\x00" not in out

    def test_unicode_replaced(self):
        # Division slash and other lookalikes shouldn't survive either.
        out = self._sanitize("foo\u2215bar.txt")
        assert "\u2215" not in out

    def test_empty_falls_back(self):
        assert self._sanitize("") == "upload"
        assert self._sanitize(None) == "upload"

    def test_long_name_trimmed_preserves_extension(self):
        long = ("A" * 200) + ".pdf"
        out = self._sanitize(long)
        assert len(out) <= 100
        assert out.endswith(".pdf")


# ── Fixtures ────────────────────────────────────────────


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


# ── Intake review now produces evidence requests too ────


class TestIntakeReviewProducesEvidenceRequests:
    @pytest.mark.asyncio
    async def test_creates_both_questions_and_requests(self, db_session):
        _, case = await _seed(db_session)

        payload = {
            "questions": [
                {
                    "question": "What reason was given for the cut?",
                    "context": "Due process check.",
                    "category": "policy",
                    "priority": "important",
                }
            ],
            "evidence_requests": [
                {
                    "title": "Written notice of the roster cut",
                    "description": "Establishes whether the club followed its policy.",
                    "evidence_type": "email",
                    "expected_date": "2026-04-01",
                    "priority": "critical",
                },
                {
                    "title": "Club bylaws — section on player removal",
                    "evidence_type": "policy",
                    "priority": "important",
                },
            ],
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(payload)))
        ]

        with patch(
            "app.services.intake_review.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.intake_review.decrypt_api_key", return_value="k"
        ):
            result = await generate_intake_questions(case.id, db_session)

        assert result.questions_created == 1
        assert result.evidence_requests_created == 2

        reqs = (
            await db_session.execute(
                select(EvidenceRequest).where(EvidenceRequest.case_id == case.id)
            )
        ).scalars().all()
        assert len(reqs) == 2
        critical = [r for r in reqs if r.priority == "critical"]
        assert len(critical) == 1 and critical[0].evidence_type == "email"

        await db_session.refresh(case)
        assert case.review_status == "needs_input"

    @pytest.mark.asyncio
    async def test_empty_evidence_requests_is_fine(self, db_session):
        _, case = await _seed(db_session)

        payload = {
            "questions": [
                {
                    "question": "A real long-enough question?",
                    "priority": "important",
                }
            ],
            "evidence_requests": [],
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(payload)))
        ]

        with patch(
            "app.services.intake_review.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.intake_review.decrypt_api_key", return_value="k"
        ):
            result = await generate_intake_questions(case.id, db_session)

        assert result.questions_created == 1
        assert result.evidence_requests_created == 0

    @pytest.mark.asyncio
    async def test_missing_evidence_requests_field_tolerated(self, db_session):
        """Older LLMs may forget to include the evidence_requests array."""
        _, case = await _seed(db_session)

        payload = {
            "questions": [
                {"question": "Long enough question?", "priority": "important"}
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(payload)))
        ]

        with patch(
            "app.services.intake_review.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.intake_review.decrypt_api_key", return_value="k"
        ):
            result = await generate_intake_questions(case.id, db_session)

        assert result.questions_created == 1
        assert result.evidence_requests_created == 0

    @pytest.mark.asyncio
    async def test_already_reviewed_blocks_on_evidence_too(self, db_session):
        """If evidence requests exist but no questions, still considered reviewed."""
        _, case = await _seed(db_session)
        db_session.add(
            EvidenceRequest(case_id=case.id, title="Existing request title")
        )
        await db_session.commit()

        result = await generate_intake_questions(case.id, db_session)
        assert result.skipped_reason == "already_reviewed"


# ── Fulfillment behavior (service-level, no HTTP) ───────


class TestFulfillmentBehavior:
    """Exercises the invariants a fulfillment endpoint guarantees: creates
    an EvidenceItem, links it, flips the status. We do this in SQL directly
    here; the HTTP layer is thin and hits the same objects."""

    @pytest.mark.asyncio
    async def test_fulfill_text_creates_linked_evidence(self, db_session):
        _, case = await _seed(db_session)
        er = EvidenceRequest(
            case_id=case.id,
            title="Coach's email",
            evidence_type="email",
        )
        db_session.add(er)
        await db_session.commit()

        # Simulate the endpoint's work
        from datetime import datetime

        item = EvidenceItem(
            case_id=case.id,
            title=er.title,
            evidence_type=er.evidence_type,
            content="Hi, coach wrote this...",
            collected_by="user",
        )
        db_session.add(item)
        await db_session.flush()

        er.status = EvidenceRequestStatus.FULFILLED
        er.fulfilled_at = datetime.utcnow()
        er.evidence_item_id = item.id
        await db_session.commit()

        await db_session.refresh(er)
        assert er.status == EvidenceRequestStatus.FULFILLED
        assert er.evidence_item_id == item.id

        # The evidence item is retrievable
        fetched = (
            await db_session.execute(
                select(EvidenceItem).where(EvidenceItem.id == item.id)
            )
        ).scalar_one()
        assert fetched.content == "Hi, coach wrote this..."

    @pytest.mark.asyncio
    async def test_claim_request_is_atomic(self, db_session):
        """Two racing fulfillments: first wins, second gets False."""
        _, case = await _seed(db_session)
        er = EvidenceRequest(
            case_id=case.id, title="Race target", evidence_type="email"
        )
        db_session.add(er)
        await db_session.commit()

        from app.api.evidence_requests import _claim_request

        first = await _claim_request(er.id, case.id, db_session)
        second = await _claim_request(er.id, case.id, db_session)
        assert first is True
        assert second is False

        await db_session.refresh(er)
        assert er.status == EvidenceRequestStatus.FULFILLED

    @pytest.mark.asyncio
    async def test_mark_unavailable_preserves_reason(self, db_session):
        _, case = await _seed(db_session)
        er = EvidenceRequest(case_id=case.id, title="Test request")
        db_session.add(er)
        await db_session.commit()

        er.status = EvidenceRequestStatus.UNAVAILABLE
        er.unavailable_reason = "I deleted the email years ago."
        await db_session.commit()

        await db_session.refresh(er)
        assert er.status == EvidenceRequestStatus.UNAVAILABLE
        assert "deleted" in er.unavailable_reason


# ── Cross-domain review_status refresh ──────────────────


class TestReviewStatusRefresh:
    """review_status should flip to 'complete' only when BOTH questions and
    evidence requests are all resolved. Neither domain can complete the
    review on its own."""

    @pytest.mark.asyncio
    async def test_questions_answered_but_evidence_open_stays_needs_input(
        self, db_session
    ):
        _, case = await _seed(db_session)
        case.review_status = "needs_input"

        q = CaseQuestion(
            case_id=case.id,
            question="Who attended the meeting?",
            priority=QuestionPriority.IMPORTANT,
            status=QuestionStatus.ANSWERED,  # already answered
            answer="Coach, board, parents",
        )
        db_session.add(q)
        db_session.add(
            EvidenceRequest(case_id=case.id, title="Meeting minutes")
        )  # still OPEN
        await db_session.commit()

        await refresh_review_status(case, db_session)
        assert case.review_status == "needs_input"

    @pytest.mark.asyncio
    async def test_evidence_fulfilled_but_questions_open_stays_needs_input(
        self, db_session
    ):
        _, case = await _seed(db_session)
        case.review_status = "needs_input"

        db_session.add(
            CaseQuestion(
                case_id=case.id,
                question="Unanswered question?",
                priority=QuestionPriority.IMPORTANT,
                status=QuestionStatus.OPEN,
            )
        )
        db_session.add(
            EvidenceRequest(
                case_id=case.id,
                title="Fulfilled thing",
                status=EvidenceRequestStatus.FULFILLED,
            )
        )
        await db_session.commit()

        await refresh_review_status(case, db_session)
        assert case.review_status == "needs_input"

    @pytest.mark.asyncio
    async def test_both_resolved_flips_to_complete(self, db_session):
        _, case = await _seed(db_session)
        case.review_status = "needs_input"

        db_session.add(
            CaseQuestion(
                case_id=case.id,
                question="Q?",
                status=QuestionStatus.ANSWERED,
                answer="A",
                priority=QuestionPriority.IMPORTANT,
            )
        )
        db_session.add(
            EvidenceRequest(
                case_id=case.id,
                title="E",
                status=EvidenceRequestStatus.FULFILLED,
            )
        )
        await db_session.commit()

        await refresh_review_status(case, db_session)
        assert case.review_status == "complete"

    @pytest.mark.asyncio
    async def test_does_not_clobber_pending_or_reviewing(self, db_session):
        """If the review agent is still working, don't touch the status."""
        _, case = await _seed(db_session)

        for status in ("pending", "reviewing"):
            case.review_status = status
            await db_session.commit()
            await refresh_review_status(case, db_session)
            assert case.review_status == status, (
                f"refresh mutated status {status!r}"
            )
