from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.worker import SNAPSHOT_DAYS, run_cycle

START = date(2025, 1, 1)
UPTREND = [(START + timedelta(days=i), 100 + i * 0.5) for i in range(170)]
FLAT = [(START + timedelta(days=i), 100.0) for i in range(170)]


def test_add_ticker_normalizes_and_rejects_duplicates(env):
    client, _ = env
    r = client.post("/v1/watchlist/tickers", json={"symbol": "nvda"})
    assert r.status_code == 201
    assert r.json() == {"symbol": "NVDA", "benchmark_symbol": "SPY"}
    assert client.post("/v1/watchlist/tickers", json={"symbol": "NVDA"}).status_code == 409


@pytest.mark.parametrize("symbol", ["", "TOO-LONG-SYMBOL-X", "BAD SYM", "A;DROP", "../x"])
def test_add_ticker_rejects_bad_symbols(env, symbol):
    client, _ = env
    assert client.post("/v1/watchlist/tickers", json={"symbol": symbol}).status_code == 422


def test_watchlist_has_null_score_until_a_cycle_runs_then_latest_score(env):
    client, engine = env
    client.post("/v1/watchlist/tickers", json={"symbol": "AAA"})
    assert client.get("/v1/watchlist").json() == [
        {"symbol": "AAA", "benchmark_symbol": "SPY", "score": None}
    ]

    with Session(engine) as s:
        fetch = lambda sym: FLAT if sym == "SPY" else UPTREND
        run_cycle(s, fetch, now=datetime(2025, 7, 1, 15, 0, tzinfo=timezone.utc))
        run_cycle(s, fetch, now=datetime(2025, 7, 1, 15, 30, tzinfo=timezone.utc))

    [row] = client.get("/v1/watchlist").json()
    score = row["score"]
    assert score["as_of"].startswith("2025-07-01T15:30")  # latest cycle wins
    assert set(score) == {"as_of", "trend", "reversion", "rel_strength", "vol_penalty", "composite", "band"}


def test_history_returns_oldest_first_with_moving_averages(env):
    client, engine = env
    client.post("/v1/watchlist/tickers", json={"symbol": "AAA"})
    with Session(engine) as s:
        run_cycle(s, lambda sym: FLAT if sym == "SPY" else UPTREND)

    body = client.get("/v1/tickers/aaa/history?days=10").json()
    assert body["symbol"] == "AAA"
    points = body["points"]
    assert len(points) == 10
    assert [p["date"] for p in points] == sorted(p["date"] for p in points)
    assert set(points[0]) == {"date", "close", "ma20", "ma100"}
    assert points[-1]["close"] == UPTREND[-1][1]
    assert len(client.get("/v1/tickers/AAA/history").json()["points"]) == SNAPSHOT_DAYS


def test_history_unknown_ticker_404_and_days_bounded(env):
    client, _ = env
    assert client.get("/v1/tickers/ZZZ/history").status_code == 404
    assert client.get("/v1/tickers/ZZZ/history?days=0").status_code == 422
    assert client.get("/v1/tickers/ZZZ/history?days=9999").status_code == 422
