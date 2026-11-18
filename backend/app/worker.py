"""Signal cycle: fetch daily closes, compute indicators and the composite score, store both.

Run one cycle by hand:   python -m app.worker
Run on a schedule:       arq app.worker.WorkerSettings   (needs Redis)
"""
import asyncio
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.twelvedata import fetch_daily_closes
from app.config import settings
from app.db import SessionLocal
from app.indicators import MIN_CLOSES, compute, ret
from app.ledger import advance_all
from app.models import CompositeScore, PriceSnapshot, Ticker
from app.scoring import score

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
            bench_ret = ret([c for _, c in series(ticker.benchmark_symbol)], 20)
            ind = compute(closes)
            s = score(ind.ma20, ind.ma100, ind.rsi14, ind.ret_20d, bench_ret, ind.ann_vol_pct)
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
        result = run_cycle(session, fetch_daily_closes)
        advance_all(session)
        return result


async def signal_cycle(ctx) -> str | dict:
    if not is_market_hours(datetime.now(timezone.utc)):
        return "skipped: market closed"
    return await asyncio.to_thread(_run_once)


class WorkerSettings:
    functions = [signal_cycle]
    cron_jobs = [cron(signal_cycle, minute={0, 30}, run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(_run_once())
