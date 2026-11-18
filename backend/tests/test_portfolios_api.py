from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.ledger import advance_all
from helpers import add_ticker, market

MON = date(2025, 7, 7)
TUE = MON + timedelta(days=1)


def make_portfolio(client, value=100_000, tier="moderate"):
    r = client.post("/v1/portfolios", json={"total_value": value, "risk_tier": tier})
    assert r.status_code == 201
    return r.json()["id"]


def test_create_portfolio_defaults_to_paper_with_full_cash(env):
    client, _ = env
    r = client.post("/v1/portfolios", json={"total_value": 50_000, "risk_tier": "conservative"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "total_value": 50_000, "risk_tier": "conservative",
                        "mode": "paper", "live_ack_at": None, "cash": 50_000}
    assert [p["id"] for p in client.get("/v1/portfolios").json()] == [1]


@pytest.mark.parametrize(
    "body",
    [
        {"total_value": 1000, "risk_tier": "moderate", "mode": "live"},   # live is never settable on create
        {"total_value": 1000, "risk_tier": "yolo"},
        {"total_value": 0, "risk_tier": "moderate"},
        {"total_value": -5, "risk_tier": "moderate"},
        {"total_value": 1e12, "risk_tier": "moderate"},
        {"risk_tier": "moderate"},
    ],
)
def test_create_portfolio_rejects_bad_input(env, body):
    client, _ = env
    assert client.post("/v1/portfolios", json=body).status_code == 422


def test_unknown_portfolio_is_404(env):
    client, _ = env
    assert client.get("/v1/portfolios/99/today").status_code == 404
    assert client.get("/v1/portfolios/99/positions").status_code == 404


def test_today_sizes_an_entry_plan_for_buy_and_nothing_for_hold(env):
    client, engine = env
    pid = make_portfolio(client)
    with Session(engine) as s:
        buy, hold, nosignal = add_ticker(s, "BUY"), add_ticker(s, "HOLD"), add_ticker(s, "NEW")
        market(s, buy, MON, "Buy", 100)
        market(s, hold, MON, "Hold", 50)

    rows = {r["symbol"]: r for r in client.get(f"/v1/portfolios/{pid}/today").json()}
    plan = rows["BUY"]["plan"]
    assert plan["kind"] == "entry" and plan["shares"] == 60 and plan["binding"] == "tier"
    assert plan["stop"] == pytest.approx(92) and plan["target"] == pytest.approx(120)
    assert plan["risk_amount"] == pytest.approx(480)
    assert [(t["label"], t["shares"]) for t in plan["tranches"]] == [("now", 20), ("+2d", 20), ("+4d", 20)]
    assert rows["BUY"]["price"] == 100 and rows["BUY"]["score"]["band"] == "Buy"
    assert rows["HOLD"]["plan"] is None and rows["HOLD"]["note"] is None
    assert rows["NEW"]["score"] is None and rows["NEW"]["plan"] is None


def test_today_shows_holding_instead_of_a_new_plan_once_position_exists(env):
    client, engine = env
    pid = make_portfolio(client)
    with Session(engine) as s:
        t = add_ticker(s, "AAA")
        market(s, t, MON, "Buy", 100)
        advance_all(s)
        market(s, t, TUE, "Buy", 105)

    [row] = client.get(f"/v1/portfolios/{pid}/today").json()
    assert row["plan"] is None
    assert row["holding"]["shares"] == 20 and row["holding"]["avg_entry"] == 100
    assert row["holding"]["unrealized_pnl"] == pytest.approx(20 * 5)
    assert client.get(f"/v1/portfolios/{pid}").json()["cash"] == pytest.approx(100_000 - 20 * 100)


def test_today_sell_band_gives_exit_plan_only_when_held(env):
    client, engine = env
    pid = make_portfolio(client)
    with Session(engine) as s:
        held, flat = add_ticker(s, "HELD"), add_ticker(s, "FLAT")
        market(s, held, MON, "Buy", 100)
        advance_all(s)
        market(s, held, TUE, "Sell", 98)
        market(s, flat, TUE, "Sell", 50)

    rows = {r["symbol"]: r for r in client.get(f"/v1/portfolios/{pid}/today").json()}
    assert rows["HELD"]["plan"]["kind"] == "exit" and rows["HELD"]["plan"]["shares"] == 20
    assert rows["FLAT"]["plan"] is None and "no position" in rows["FLAT"]["note"]


def test_today_respects_reentry_cooldown(env):
    client, engine = env
    pid = make_portfolio(client)
    with Session(engine) as s:
        t = add_ticker(s, "AAA")
        market(s, t, MON, "Buy", 100)
        advance_all(s)
        market(s, t, TUE, "Buy", 91)   # stopped out
        advance_all(s)

    [row] = client.get(f"/v1/portfolios/{pid}/today").json()
    assert row["plan"] is None and "cooling down" in row["note"]


def test_positions_list_shows_realized_outcome_fills_and_the_miss_rate(env):
    client, engine = env
    pid = make_portfolio(client)
    with Session(engine) as s:
        loser, winner = add_ticker(s, "LOSE"), add_ticker(s, "WIN")
        market(s, loser, MON, "Buy", 100)
        market(s, winner, MON, "Buy", 100)
        advance_all(s)
        market(s, loser, TUE, "Buy", 91)    # stop
        market(s, winner, TUE, "Sell", 110)  # signal exit at a gain
        advance_all(s)

    body = client.get(f"/v1/portfolios/{pid}/positions").json()
    by_symbol = {p["symbol"]: p for p in body["positions"]}
    assert by_symbol["LOSE"]["status"] == "closed" and by_symbol["LOSE"]["close_reason"] == "stop"
    assert by_symbol["LOSE"]["realized_pnl"] == pytest.approx(-180)
    assert by_symbol["WIN"]["realized_pnl"] == pytest.approx(200)
    assert [f["side"] for f in by_symbol["WIN"]["fills"]] == ["buy", "sell"]
    assert body["summary"] == {"open": 0, "closed": 2, "wins": 1, "losses": 1, "realized_pnl": pytest.approx(20)}


@pytest.mark.parametrize("body", [{}, {"acknowledge": False}, {"acknowledge": "yes"}, {"acknowledge": True, "mode": "x"}])
def test_live_ack_requires_an_explicit_true(env, body):
    client, _ = env
    pid = make_portfolio(client)
    assert client.post(f"/v1/portfolios/{pid}/live-ack", json=body).status_code == 422
    assert client.get(f"/v1/portfolios/{pid}").json()["mode"] == "paper"


def test_live_ack_switches_to_live_with_a_date_and_is_idempotent(env):
    client, _ = env
    pid = make_portfolio(client)
    first = client.post(f"/v1/portfolios/{pid}/live-ack", json={"acknowledge": True}).json()
    assert first["mode"] == "live" and first["live_ack_at"] is not None
    again = client.post(f"/v1/portfolios/{pid}/live-ack", json={"acknowledge": True}).json()
    assert again["live_ack_at"] == first["live_ack_at"]
    assert client.post("/v1/portfolios/99/live-ack", json={"acknowledge": True}).status_code == 404


def test_back_to_paper_clears_the_acknowledgement(env):
    client, _ = env
    pid = make_portfolio(client)
    client.post(f"/v1/portfolios/{pid}/live-ack", json={"acknowledge": True})
    back = client.post(f"/v1/portfolios/{pid}/paper").json()
    assert back["mode"] == "paper" and back["live_ack_at"] is None
    # going live again needs a fresh acknowledgement
    assert client.post(f"/v1/portfolios/{pid}/live-ack", json={"acknowledge": True}).json()["mode"] == "live"


def test_paper_simulation_never_touches_a_live_portfolio(env):
    client, engine = env
    paper_id = make_portfolio(client)
    live_id = make_portfolio(client)
    client.post(f"/v1/portfolios/{live_id}/live-ack", json={"acknowledge": True})
    with Session(engine) as s:
        t = add_ticker(s, "AAA")
        market(s, t, MON, "Buy", 100)
        advance_all(s)

    assert len(client.get(f"/v1/portfolios/{paper_id}/positions").json()["positions"]) == 1
    assert client.get(f"/v1/portfolios/{live_id}/positions").json()["positions"] == []
    # the live portfolio still gets today's sized plan to act on
    [row] = client.get(f"/v1/portfolios/{live_id}/today").json()
    assert row["plan"]["kind"] == "entry"
