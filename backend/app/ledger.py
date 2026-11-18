"""Paper ledger: turns each Buy-band signal into a sized plan and walks it to a realized outcome (SPEC.md §7.4).

Every fill is recorded in `fills`; shares held, average entry and realized P&L are derived from them.
Fills use the latest daily close, with no slippage or fees.
"""
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import CompositeScore, Fill, Portfolio, Position, PriceSnapshot, Ticker
from app.sizing import TRANCHE_OFFSETS, TRIM_FRACTION, add_trading_days, plan_entry, split_tranches, trail_stop

BUY_BANDS = {"Strong Buy", "Buy"}
SELL_BANDS = {"Sell", "Strong Sell"}  # composite below the Hold threshold
REENTRY_COOLDOWN_DAYS = 5  # trading days before a ticker can be re-entered after an exit


@dataclass(frozen=True)
class Stats:
    bought: int
    sold: int
    held: int
    avg_entry: float
    realized: float


def position_stats(fills: list[Fill]) -> Stats:
    buys = [f for f in fills if f.side == "buy"]
    sells = [f for f in fills if f.side == "sell"]
    bought = sum(f.shares for f in buys)
    avg_entry = sum(f.shares * f.price for f in buys) / bought if bought else 0.0
    sold = sum(f.shares for f in sells)
    realized = sum((f.price - avg_entry) * f.shares for f in sells)
    return Stats(bought, sold, bought - sold, avg_entry, realized)


def fills_for(session: Session, position_id: int) -> list[Fill]:
    return list(session.scalars(select(Fill).where(Fill.position_id == position_id).order_by(Fill.id)))


def cash(session: Session, portfolio: Portfolio) -> float:
    rows = session.execute(
        select(Fill.side, Fill.shares, Fill.price).join(Position).where(Position.portfolio_id == portfolio.id)
    ).all()
    return portfolio.total_value + sum((1 if side == "sell" else -1) * n * p for side, n, p in rows)


def latest_scores(session: Session) -> dict[int, CompositeScore]:
    newest = (
        select(CompositeScore.ticker_id, func.max(CompositeScore.computed_at).label("at"))
        .group_by(CompositeScore.ticker_id)
        .subquery()
    )
    rows = session.scalars(
        select(CompositeScore).join(
            newest, and_(CompositeScore.ticker_id == newest.c.ticker_id, CompositeScore.computed_at == newest.c.at)
        )
    )
    return {s.ticker_id: s for s in rows}


def latest_prices(session: Session) -> dict[int, tuple[date, float]]:
    newest = (
        select(PriceSnapshot.ticker_id, func.max(PriceSnapshot.observed_at).label("d"))
        .group_by(PriceSnapshot.ticker_id)
        .subquery()
    )
    rows = session.execute(
        select(PriceSnapshot.ticker_id, PriceSnapshot.observed_at, PriceSnapshot.close).join(
            newest, and_(PriceSnapshot.ticker_id == newest.c.ticker_id, PriceSnapshot.observed_at == newest.c.d)
        )
    )
    return {tid: (d, close) for tid, d, close in rows}


def in_cooldown(session: Session, portfolio_id: int, ticker_id: int, data_date: date) -> bool:
    last_exit = session.scalar(
        select(func.max(Fill.data_date))
        .join(Position)
        .where(Position.portfolio_id == portfolio_id, Position.ticker_id == ticker_id, Fill.side == "sell")
    )
    return last_exit is not None and data_date < add_trading_days(last_exit, REENTRY_COOLDOWN_DAYS)


def _step(session: Session, portfolio: Portfolio, pos: Position, band: str, data_date: date, price: float, now: datetime) -> None:
    stats = position_stats(fills_for(session, pos.id))

    if stats.held > 0:
        pos.high_water = max(pos.high_water, price)
        pos.stop = trail_stop(pos.stop, stats.avg_entry, pos.high_water)
        if price <= pos.stop:
            reason, qty = "stop", stats.held
        elif band in SELL_BANDS:
            reason, qty = "signal", stats.held
        elif price >= pos.target and not pos.trimmed:
            reason, qty = "target", max(1, math.floor(stats.held * TRIM_FRACTION))
        else:
            reason = qty = None
        if qty:
            session.add(Fill(position_id=pos.id, side="sell", shares=qty, price=price,
                             data_date=data_date, reason=reason, filled_at=now))
            if reason == "target":
                pos.trimmed = True
                pos.plan_cancelled = True
            if qty >= stats.held:
                pos.status, pos.closed_at, pos.close_reason = "closed", now, reason
            return

    sizes = split_tranches(pos.planned_shares)
    filled_tranches = len([f for f in fills_for(session, pos.id) if f.side == "buy"])
    if pos.plan_cancelled or filled_tranches >= len(sizes):
        return
    if band not in BUY_BANDS:  # the signal flipped before the plan finished: cancel it, don't complete it
        pos.plan_cancelled = True
        if stats.bought == 0:
            pos.status, pos.closed_at, pos.close_reason = "closed", now, "cancelled"
        return

    free = cash(session, portfolio)
    while filled_tranches < len(sizes) and data_date >= add_trading_days(pos.plan_date, TRANCHE_OFFSETS[filled_tranches]):
        qty = min(sizes[filled_tranches], math.floor(free / price))
        if qty < 1:
            break
        session.add(Fill(position_id=pos.id, side="buy", shares=qty, price=price,
                         data_date=data_date, reason="tranche", filled_at=now))
        free -= qty * price
        filled_tranches += 1
        pos.status = "open"


def advance_portfolio(session: Session, portfolio: Portfolio, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    scores, prices = latest_scores(session), latest_prices(session)
    for ticker in session.scalars(select(Ticker)).all():
        score, px = scores.get(ticker.id), prices.get(ticker.id)
        if score is None or px is None:
            continue
        data_date, price = px
        pos = session.scalar(
            select(Position).where(
                Position.portfolio_id == portfolio.id, Position.ticker_id == ticker.id, Position.status != "closed"
            )
        )
        if pos is None and score.band in BUY_BANDS and not in_cooldown(session, portfolio.id, ticker.id, data_date):
            plan = plan_entry(portfolio.total_value, portfolio.risk_tier, price, cash(session, portfolio))
            if plan:
                pos = Position(
                    portfolio_id=portfolio.id, ticker_id=ticker.id, status="planned", plan_date=data_date,
                    planned_shares=plan.shares, stop=plan.stop, target=plan.target, high_water=price,
                )
                session.add(pos)
                session.flush()
        if pos is not None:
            _step(session, portfolio, pos, score.band, data_date, price, now)


def advance_all(session: Session, now: datetime | None = None) -> None:
    # Only paper portfolios are simulated; a live portfolio must never get invented fills.
    for portfolio in session.scalars(select(Portfolio).where(Portfolio.mode == "paper")).all():
        advance_portfolio(session, portfolio, now)
    session.commit()
