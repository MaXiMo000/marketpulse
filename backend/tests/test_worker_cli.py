from datetime import datetime, timezone

from app.worker import main

MON_MARKET = datetime(2025, 7, 7, 15, 0, tzinfo=timezone.utc)    # Monday 11:00 New York
SATURDAY = datetime(2025, 7, 5, 15, 0, tzinfo=timezone.utc)
MON_NIGHT = datetime(2025, 7, 7, 23, 0, tzinfo=timezone.utc)     # Monday 19:00 New York, closed


def test_a_scheduled_run_does_nothing_outside_market_hours(capsys):
    calls = []
    assert main(["--scheduled"], now=SATURDAY, run=lambda: calls.append(1)) == 0
    assert main(["--scheduled"], now=MON_NIGHT, run=lambda: calls.append(1)) == 0
    assert calls == []
    assert "market closed" in capsys.readouterr().out


def test_a_scheduled_run_during_market_hours_runs_a_cycle():
    calls = []
    assert main(["--scheduled"], now=MON_MARKET, run=lambda: calls.append(1) or {"scored": 1, "failed": []}) == 0
    assert calls == [1]


def test_a_manual_run_always_runs_whatever_the_time():
    calls = []
    main([], now=SATURDAY, run=lambda: calls.append(1) or {"scored": 1, "failed": []})
    assert calls == [1]


def test_a_cycle_with_failed_tickers_exits_non_zero_so_the_scheduler_flags_it(capsys):
    code = main(["--scheduled"], now=MON_MARKET, run=lambda: {"scored": 3, "failed": ["BAD"]})
    assert code == 1
    assert "BAD" in capsys.readouterr().out


def test_a_crashing_cycle_exits_non_zero_instead_of_hiding_the_error(capsys):
    def boom():
        raise RuntimeError("database unreachable")

    assert main(["--scheduled"], now=MON_MARKET, run=boom) == 1
    assert "database unreachable" in capsys.readouterr().out


def test_the_worker_refuses_to_run_in_production_on_a_throwaway_sqlite_file(monkeypatch, capsys):
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "database_url", "sqlite:///./marketpulse.db")
    calls = []
    assert main(["--scheduled"], now=MON_MARKET, run=lambda: calls.append(1)) == 1
    assert calls == [] and "DATABASE_URL" in capsys.readouterr().out
