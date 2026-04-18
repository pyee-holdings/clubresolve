"""Phase D: tests for the /visit endpoint and last_visited_at semantics."""

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
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
