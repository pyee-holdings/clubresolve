"""Phase D: tests for the /visit endpoint and last_visited_at semantics.

We cover two layers:
  1. `last_visited_at` column semantics via direct mutation.
  2. `/api/cases/:id/visit` endpoint behavior via FastAPI TestClient with
     an in-memory SQLite override. The latter proves the capture-then-
     update ordering, owner enforcement, and the debounce.
"""

import asyncio
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.case import Case
from app.models.user import User


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
    case = Case(user_id=user.id, title="A case")
    session.add(case)
    await session.commit()
    return user, case


class TestLastVisitedAtSemantics:
    """The /visit endpoint's contract is that each call captures the PREVIOUS
    value before overwriting. We exercise that via direct model mutation
    rather than HTTP since the app doesn't ship an HTTP test client setup."""

    @pytest.mark.asyncio
    async def test_first_visit_has_no_previous(self, db_session):
        _, case = await _seed(db_session)

        # Simulate the endpoint's logic
        previous = case.last_visited_at
        current = datetime.utcnow()
        case.last_visited_at = current
        await db_session.commit()

        assert previous is None
        assert case.last_visited_at == current

    @pytest.mark.asyncio
    async def test_second_visit_returns_first_visit_time(self, db_session):
        _, case = await _seed(db_session)
        first_time = datetime.utcnow() - timedelta(hours=2)
        case.last_visited_at = first_time
        await db_session.commit()

        # Second visit
        previous = case.last_visited_at
        current = datetime.utcnow()
        case.last_visited_at = current
        await db_session.commit()

        assert previous == first_time
        assert case.last_visited_at == current
        assert case.last_visited_at > first_time

    @pytest.mark.asyncio
    async def test_visit_does_not_touch_other_fields(self, db_session):
        _, case = await _seed(db_session)
        case.review_status = "needs_input"
        case.plan_status = "ready"
        case.strategy_plan = "pre-existing plan"
        await db_session.commit()

        case.last_visited_at = datetime.utcnow()
        await db_session.commit()
        await db_session.refresh(case)

        assert case.review_status == "needs_input"
        assert case.plan_status == "ready"
        assert case.strategy_plan == "pre-existing plan"

    @pytest.mark.asyncio
    async def test_repeat_visits_monotonically_advance(self, db_session):
        _, case = await _seed(db_session)
        times = []
        for _ in range(3):
            case.last_visited_at = datetime.utcnow()
            times.append(case.last_visited_at)
            await db_session.commit()
            await asyncio.sleep(0.01)
        assert times[0] <= times[1] <= times[2]


# ── HTTP-level tests via FastAPI TestClient ────────────


@pytest_asyncio.fixture
async def http_db():
    """Per-test in-memory SQLite, overriding the get_db dependency for the
    whole FastAPI app. Each test gets a fresh schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override():
        async with Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override
    yield Session
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


def _register_and_login(client: TestClient, email: str) -> str:
    client.post(
        "/api/auth/register",
        json={"email": email, "name": "t", "password": "password123"},
    )
    r = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    return r.json()["access_token"]


class TestVisitEndpoint:
    def test_first_visit_returns_null_previous(self, http_db):
        with TestClient(app) as client:
            token = _register_and_login(client, "a@x.com")
            headers = {"Authorization": f"Bearer {token}"}
            case = client.post(
                "/api/cases", headers=headers, json={"title": "x"}
            ).json()
            r = client.post(
                f"/api/cases/{case['id']}/visit", headers=headers
            )
            assert r.status_code == 200
            body = r.json()
            assert body["previous_visited_at"] is None
            assert body["current_visited_at"] is not None

    def test_second_visit_returns_first_visit_time(self, http_db):
        """Outside the debounce window, second visit advances the stored
        timestamp and returns the first visit's time as previous."""
        import app.api.cases as cases_mod

        with TestClient(app) as client:
            token = _register_and_login(client, "b@x.com")
            headers = {"Authorization": f"Bearer {token}"}
            case = client.post(
                "/api/cases", headers=headers, json={"title": "x"}
            ).json()
            original_debounce = cases_mod._VISIT_DEBOUNCE
            cases_mod._VISIT_DEBOUNCE = timedelta(0)
            try:
                first = client.post(
                    f"/api/cases/{case['id']}/visit", headers=headers
                ).json()
                second = client.post(
                    f"/api/cases/{case['id']}/visit", headers=headers
                ).json()
            finally:
                cases_mod._VISIT_DEBOUNCE = original_debounce
            assert second["previous_visited_at"] == first["current_visited_at"]
            assert second["current_visited_at"] >= first["current_visited_at"]

    def test_debounce_returns_stable_timestamp(self, http_db):
        """Two calls within the debounce window return the same current
        timestamp — the stored last_visited_at did not advance. This
        prevents React StrictMode / double-mount from burning through
        the real previous-visit anchor."""
        with TestClient(app) as client:
            token = _register_and_login(client, "c@x.com")
            headers = {"Authorization": f"Bearer {token}"}
            case = client.post(
                "/api/cases", headers=headers, json={"title": "x"}
            ).json()
            first = client.post(
                f"/api/cases/{case['id']}/visit", headers=headers
            ).json()
            second = client.post(
                f"/api/cases/{case['id']}/visit", headers=headers
            ).json()
            # First visit establishes the anchor.
            assert first["previous_visited_at"] is None
            # Within debounce: no-op. previous == current == the first visit.
            assert second["previous_visited_at"] == first["current_visited_at"]
            assert second["current_visited_at"] == first["current_visited_at"]

    def test_cross_user_visit_is_404(self, http_db):
        with TestClient(app) as client:
            owner_token = _register_and_login(client, "owner@x.com")
            case = client.post(
                "/api/cases",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"title": "x"},
            ).json()
            other_token = _register_and_login(client, "other@x.com")
            r = client.post(
                f"/api/cases/{case['id']}/visit",
                headers={"Authorization": f"Bearer {other_token}"},
            )
            assert r.status_code == 404

    def test_unauthenticated_is_401(self, http_db):
        with TestClient(app) as client:
            token = _register_and_login(client, "d@x.com")
            case = client.post(
                "/api/cases",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": "x"},
            ).json()
            r = client.post(f"/api/cases/{case['id']}/visit")
            assert r.status_code == 401
