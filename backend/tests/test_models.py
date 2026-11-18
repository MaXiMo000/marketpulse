from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Portfolio


@pytest.fixture
def s():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_portfolio_cannot_be_live_without_a_dated_acknowledgement(s):
    s.add(Portfolio(total_value=1000, risk_tier="moderate", mode="live"))
    with pytest.raises(IntegrityError):
        s.commit()


def test_live_portfolio_with_acknowledgement_is_allowed_and_paper_is_default(s):
    s.add(Portfolio(total_value=1000, risk_tier="moderate", mode="live", live_ack_at=datetime.now(timezone.utc)))
    s.add(Portfolio(total_value=1000, risk_tier="moderate"))
    s.commit()
    assert [p.mode for p in s.query(Portfolio).order_by(Portfolio.id)] == ["live", "paper"]
