from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Alert
from helpers import add_ticker


def _alert(session, ticker, hour, frm, to, from_score, to_score):
    session.add(Alert(ticker_id=ticker.id, computed_at=datetime(2025, 7, 7, hour, 0, tzinfo=timezone.utc),
                      from_band=frm, to_band=to, from_score=from_score, to_score=to_score))
    session.commit()


def test_alerts_are_newest_first_with_direction(env):
    client, engine = env
    with Session(engine) as s:
        t = add_ticker(s, "AAA")
        _alert(s, t, 14, "Hold", "Buy", 58, 68)
        _alert(s, t, 15, "Buy", "Sell", 68, 40)

    body = client.get("/v1/alerts").json()
    assert [(a["symbol"], a["from_band"], a["to_band"], a["direction"]) for a in body] == [
        ("AAA", "Buy", "Sell", "down"),
        ("AAA", "Hold", "Buy", "up"),
    ]
    assert body[0]["from_score"] == 68 and body[0]["to_score"] == 40


def test_alerts_limit_is_bounded(env):
    client, _ = env
    assert client.get("/v1/alerts?limit=0").status_code == 422
    assert client.get("/v1/alerts?limit=1000").status_code == 422
    assert client.get("/v1/alerts").json() == []
