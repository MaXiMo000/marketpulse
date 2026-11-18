"""Signal cycle: fetch daily closes, compute indicators and the composite score, store both.

Run one cycle by hand:        python -m app.worker
Run from a scheduler (cron):  python -m app.worker --scheduled     (does nothing outside US market hours)
"""
import argparse
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.twelvedata import fetch_daily_closes
from app.db import SessionLocal
from app.indicators import MIN_CLOSES, compute
from app.ledger import advance_all
from app.models import Alert, CompositeScore, PriceSnapshot, Ticker
from app.config import settings
from app.notify import notify_flips
from app.security import validate_database
from app.signal import evaluate

log = logging.getLogger(__name__)
SNAPSHOT_DAYS = 60
_NY = ZoneInfo("America/New_York")


def run_cycle(session: Session, fetch, now: datetime | None = None) -> dict:
    """`fetch(symbol)` returns [(date, close)] oldest first. One bad ticker never stops the cycle."""
    now = now or datetime.now(timezone.utc)
    cache: dict[str, list] = {}

    def series(symbol: str) -> list:
        if symbol not in cache:
            cache[symbol] = fetch(symbol)
        return cache[symbol]

    scored, failed = 0, []
    for ticker in session.scalars(select(Ticker)).all():
        try:
            dates = [d for d, _ in series(ticker.symbol)]
            closes = [c for _, c in series(ticker.symbol)]
            ind, s = evaluate(closes, [c for _, c in series(ticker.benchmark_symbol)])
            snapshots = [
                (i, compute(closes[: i + 1]))
                for i in range(max(MIN_CLOSES - 1, len(closes) - SNAPSHOT_DAYS), len(closes))
            ]
        except Exception:
            log.exception("cycle: %s failed", ticker.symbol)
            failed.append(ticker.symbol)
            continue
        for i, si in snapshots:
            session.merge(PriceSnapshot(
                ticker_id=ticker.id, observed_at=dates[i], close=closes[i],
                ma20=si.ma20, ma100=si.ma100, rsi14=si.rsi14, ret_20d=si.ret_20d, ann_vol=si.ann_vol_pct,
            ))
        previous = session.scalar(
            select(CompositeScore).where(CompositeScore.ticker_id == ticker.id).order_by(CompositeScore.computed_at.desc())
        )
        if previous is not None and previous.band != s.band:
            session.add(Alert(
                ticker_id=ticker.id, computed_at=now, from_band=previous.band, to_band=s.band,
                from_score=previous.composite, to_score=s.composite,
            ))
        session.add(CompositeScore(
            ticker_id=ticker.id, computed_at=now, trend=s.trend, reversion=s.reversion,
            rel_strength=s.rel_strength, vol_penalty=s.vol_penalty, composite=s.composite, band=s.band,
        ))
        scored += 1
    session.commit()
    return {"scored": scored, "failed": failed}


def is_market_hours(now: datetime) -> bool:
    """US cash-equity hours, weekdays only. Exchange holidays are not modelled; a holiday cycle just re-scores the same data."""
    ny = now.astimezone(_NY)
    return ny.weekday() < 5 and time(9, 30) <= ny.time() <= time(16, 0)


def _run_once() -> dict:
    with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        result = run_cycle(session, fetch_daily_closes, now=now)
        advance_all(session)
        notify_flips(session, now)
        return result


def main(argv: list[str] | None = None, now: datetime | None = None, run=_run_once) -> int:
    """Exit status 0 on a clean cycle; 1 if it crashed or any ticker failed, so the scheduler flags the run."""
    parser = argparse.ArgumentParser(description="Run one signal cycle.")
    parser.add_argument("--scheduled", action="store_true", help="run only during US market hours (for cron)")
    args = parser.parse_args(argv)
    try:
        validate_database(settings)
    except RuntimeError as exc:
        print(f"refusing to run: {exc}")
        return 1
    if args.scheduled and not is_market_hours(now or datetime.now(timezone.utc)):
        print("skipped: market closed")
        return 0
    try:
        result = run()
    except Exception as exc:
        log.exception("cycle crashed")
        print(f"cycle failed: {exc}")
        return 1
    print(result)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    raise SystemExit(main())
