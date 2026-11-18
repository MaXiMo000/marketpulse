import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import BacktestRun


def test_no_backtest_yet_is_a_clear_404(env):
    client, _ = env
    r = client.get("/v1/backtest")
    assert r.status_code == 404
    assert "app.backtest" in r.json()["detail"]  # tells the user how to run one


def test_latest_backtest_is_returned(env):
    client, engine = env
    with Session(engine) as s:
        s.add(BacktestRun(created_at=datetime(2025, 7, 1, tzinfo=timezone.utc), result=json.dumps({"v": 1})))
        s.add(BacktestRun(created_at=datetime(2025, 7, 2, tzinfo=timezone.utc), result=json.dumps({"v": 2})))
        s.commit()
    body = client.get("/v1/backtest").json()
    assert body["result"] == {"v": 2}
    assert body["created_at"].startswith("2025-07-02")
