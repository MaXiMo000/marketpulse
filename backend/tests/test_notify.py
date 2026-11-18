from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alert, Base, Ticker
from app.notify import notify_flips

CYCLE = datetime(2025, 7, 7, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Ticker(symbol="AAA"), Ticker(symbol="BBB")])
        s.commit()
        yield s


@pytest.fixture(autouse=True)
def smtp_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "alert_email_to", "me@example.test")
    monkeypatch.setattr(settings, "alert_email_from", "marketpulse@example.test")


def flip(session, ticker_id, at, frm, to, f, t):
    session.add(Alert(ticker_id=ticker_id, computed_at=at, from_band=frm, to_band=to, from_score=f, to_score=t))
    session.commit()


def test_one_email_lists_this_cycles_flips_with_the_disclaimer(session):
    flip(session, 1, CYCLE, "Hold", "Buy", 58, 68)
    flip(session, 2, CYCLE, "Buy", "Sell", 66, 40)
    sent = []
    assert notify_flips(session, CYCLE, send=sent.append) == 2
    [msg] = sent
    assert msg["To"] == "me@example.test" and msg["From"] == "marketpulse@example.test"
    assert msg["Subject"] == "MarketPulse: 2 signal flips"
    body = msg.get_content()
    assert "AAA: Hold -> Buy (58 -> 68)" in body and "BBB: Buy -> Sell (66 -> 40)" in body
    assert "not personalized financial advice" in body


def test_single_flip_subject_names_the_ticker(session):
    flip(session, 1, CYCLE, "Hold", "Buy", 58, 68)
    sent = []
    notify_flips(session, CYCLE, send=sent.append)
    assert sent[0]["Subject"] == "MarketPulse: AAA Hold -> Buy"


def test_flips_from_other_cycles_are_not_resent(session):
    flip(session, 1, CYCLE - timedelta(minutes=30), "Hold", "Buy", 58, 68)
    sent = []
    assert notify_flips(session, CYCLE, send=sent.append) == 0
    assert sent == []


def test_nothing_is_sent_when_email_is_not_configured(session, monkeypatch):
    flip(session, 1, CYCLE, "Hold", "Buy", 58, 68)
    monkeypatch.setattr(settings, "smtp_host", "")
    sent = []
    assert notify_flips(session, CYCLE, send=sent.append) == 0
    assert sent == []


def test_a_failing_mail_server_never_breaks_the_cycle(session):
    flip(session, 1, CYCLE, "Hold", "Buy", 58, 68)

    def boom(_msg):
        raise OSError("connection refused")

    assert notify_flips(session, CYCLE, send=boom) == 0
