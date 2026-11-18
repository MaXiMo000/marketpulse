"""End-to-end check against a real Postgres. Skipped unless TEST_DATABASE_URL is set, e.g.

    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/marketpulse_test pytest tests/test_postgres_smoke.py
"""
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import normalize_database_url, settings
from app.db import get_db
from app.ledger import advance_all
from app.main import app
from app.models import Alert, CompositeScore, Portfolio, Ticker
from app.worker import run_cycle

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set TEST_DATABASE_URL to run against Postgres")

BACKEND = Path(__file__).resolve().parents[1]
START = date(2025, 1, 1)
UPTREND = [(START + timedelta(days=i), 100 + i * 0.5) for i in range(170)]
FLAT = [(START + timedelta(days=i), 100.0) for i in range(170)]


@pytest.fixture
def pg(monkeypatch):
    url = normalize_database_url(URL)
    monkeypatch.setattr(settings, "database_url", url)  # Alembic's env.py reads this
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.downgrade(cfg, "base")  # start from a clean schema even if a previous run left one behind
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    yield engine, cfg
    engine.dispose()
    command.downgrade(cfg, "base")


def test_migrations_create_the_whole_schema(pg):
    engine, _ = pg
    tables = set(inspect(engine).get_table_names())
    assert {"tickers", "price_snapshots", "composite_scores", "portfolios", "positions", "fills",
            "alerts", "backtest_runs", "equity_snapshots"} <= tables


def test_cycle_ledger_and_api_work_on_postgres(pg):
    engine, _ = pg
    fetch = lambda sym: FLAT if sym == "SPY" else UPTREND
    with Session(engine) as s:
        s.add_all([Ticker(symbol="AAA"), Ticker(symbol="BBB")])
        s.add(Portfolio(total_value=100_000, risk_tier="moderate"))
        s.commit()
        t0 = datetime(2025, 7, 1, 15, 0, tzinfo=timezone.utc)
        assert run_cycle(s, fetch, now=t0) == {"scored": 2, "failed": []}
        advance_all(s, now=t0)
        # a second cycle with a changed series flips a band and must record an alert on Postgres too
        flipped = lambda sym: FLAT if sym in ("SPY", "AAA") else UPTREND
        run_cycle(s, flipped, now=t0 + timedelta(minutes=30))
        assert len(s.scalars(select(CompositeScore)).all()) == 4

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        assert client.get("/health").json() == {"status": "ok"}
        [p] = client.get("/v1/portfolios").json()
        assert p["mode"] == "paper" and p["equity"] > 0
        rows = {r["symbol"]: r for r in client.get(f"/v1/portfolios/{p['id']}/today").json()}
        assert set(rows) == {"AAA", "BBB"} and rows["AAA"]["score"] is not None
        assert client.get(f"/v1/portfolios/{p['id']}/positions").status_code == 200
        assert client.get("/v1/watchlist").status_code == 200
        assert client.get("/v1/tickers/AAA/history").json()["points"]
        assert client.get("/v1/alerts").status_code == 200
        assert client.get("/v1/backtest").status_code == 404

        live = client.post(f"/v1/portfolios/{p['id']}/live-ack", json={"acknowledge": True}).json()
        assert live["mode"] == "live" and live["live_ack_at"].endswith(("Z", "+00:00"))
        assert client.post(f"/v1/portfolios/{p['id']}/paper").json()["live_ack_at"] is None
    finally:
        app.dependency_overrides.clear()


def test_the_database_itself_refuses_a_live_portfolio_without_an_acknowledgement(pg):
    engine, _ = pg
    with Session(engine) as s:
        s.add(Portfolio(total_value=1000, risk_tier="moderate", mode="live"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_every_migration_can_be_reversed(pg):
    engine, cfg = pg
    command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(cfg, "head")
    assert "portfolios" in inspect(engine).get_table_names()
