from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import Base, CompositeScore, PriceSnapshot, Ticker
from app.scoring import band_for
from app.worker import SNAPSHOT_DAYS, run_cycle

START = date(2025, 1, 1)
UPTREND = [(START + timedelta(days=i), 100 + i * 0.5) for i in range(170)]
FLAT = [(START + timedelta(days=i), 100.0) for i in range(170)]
T0 = datetime(2025, 7, 1, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Ticker(symbol="AAA", benchmark_symbol="SPY"), Ticker(symbol="BBB", benchmark_symbol="SPY")])
        s.commit()
        yield s


def fetch_ok(symbol):
    return FLAT if symbol == "SPY" else UPTREND


def test_cycle_scores_every_ticker_and_writes_daily_snapshots(session):
    result = run_cycle(session, fetch_ok, now=T0)
    assert result == {"scored": 2, "failed": []}
    scores = session.scalars(select(CompositeScore)).all()
    assert len(scores) == 2
    for s in scores:
        assert s.computed_at.replace(tzinfo=timezone.utc) == T0
        assert s.trend > 0  # MA20 above MA100 on a steady uptrend
        assert s.band == band_for(s.composite)
    assert session.scalar(select(func.count()).select_from(PriceSnapshot)) == 2 * SNAPSHOT_DAYS


def test_rerun_adds_a_score_row_but_does_not_duplicate_snapshots(session):
    run_cycle(session, fetch_ok, now=T0)
    run_cycle(session, fetch_ok, now=T0 + timedelta(minutes=30))
    assert session.scalar(select(func.count()).select_from(CompositeScore)) == 4
    assert session.scalar(select(func.count()).select_from(PriceSnapshot)) == 2 * SNAPSHOT_DAYS


def test_one_failing_ticker_does_not_stop_the_cycle(session):
    def fetch(symbol):
        if symbol == "BBB":
            raise RuntimeError("provider error")
        return fetch_ok(symbol)

    result = run_cycle(session, fetch, now=T0)
    assert result == {"scored": 1, "failed": ["BBB"]}
    assert session.scalar(select(func.count()).select_from(CompositeScore)) == 1


def test_benchmark_is_fetched_once_per_cycle(session):
    calls = []

    def fetch(symbol):
        calls.append(symbol)
        return fetch_ok(symbol)

    run_cycle(session, fetch, now=T0)
    assert sorted(calls) == ["AAA", "BBB", "SPY"]


@pytest.mark.parametrize(
    "when,expected",
    [
        (datetime(2025, 7, 7, 15, 0, tzinfo=timezone.utc), True),    # Mon 11:00 EDT
        (datetime(2025, 7, 7, 21, 0, tzinfo=timezone.utc), False),   # Mon 17:00 EDT, closed
        (datetime(2025, 7, 5, 15, 0, tzinfo=timezone.utc), False),   # Saturday
        (datetime(2025, 12, 8, 14, 30, tzinfo=timezone.utc), True),  # Mon 09:30 EST (winter offset)
        (datetime(2025, 12, 8, 14, 29, tzinfo=timezone.utc), False), # one minute before the open
    ],
)
def test_market_hours_respects_new_york_dst(when, expected):
    from app.worker import is_market_hours

    assert is_market_hours(when) is expected
