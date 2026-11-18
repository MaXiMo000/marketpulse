from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.ledger import (
    BUY_BANDS, SELL_BANDS, cash, equity, fills_for, in_cooldown, latest_prices, latest_scores, position_stats, prior_equity,
)
from app.models import Portfolio, Position, Ticker
from app.security import PROTECTED
from app.schemas import (
    FillOut, HoldingOut, LiveAck, PlanOut, PortfolioIn, PortfolioOut, PositionOut, PositionsOut,
    ScoreOut, Summary, TodayRow, TrancheOut,
)
from app.sizing import TIERS, plan_entry

router = APIRouter(prefix="/v1/portfolios", dependencies=PROTECTED)


def _portfolio(db: Session, portfolio_id: int) -> Portfolio:
    pf = db.get(Portfolio, portfolio_id)
    if pf is None:
        raise HTTPException(404, f"portfolio {portfolio_id} not found")
    return pf


def _breaker_tripped(pf: Portfolio, today) -> bool:
    return today is not None and pf.breaker_date == today


def _out(db: Session, pf: Portfolio) -> PortfolioOut:
    prices = latest_prices(db)
    today = max((d for d, _ in prices.values()), default=None)
    eq = equity(db, pf, prices)
    prior = prior_equity(db, pf, today) if today else pf.total_value
    return PortfolioOut(
        id=pf.id, total_value=pf.total_value, risk_tier=pf.risk_tier, mode=pf.mode, live_ack_at=pf.live_ack_at,
        cash=cash(db, pf), equity=eq, day_change=eq / prior - 1 if prior > 0 else 0.0,
        daily_loss_limit=TIERS[pf.risk_tier].daily_loss_limit_pct, breaker_tripped=_breaker_tripped(pf, today),
    )


@router.post("", response_model=PortfolioOut, status_code=201)
def create_portfolio(body: PortfolioIn, db: Session = Depends(get_db)):
    pf = Portfolio(total_value=body.total_value, risk_tier=body.risk_tier)  # mode defaults to paper
    db.add(pf)
    db.commit()
    return _out(db, pf)


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(db: Session = Depends(get_db)):
    return [_out(db, pf) for pf in db.scalars(select(Portfolio).order_by(Portfolio.id))]


@router.get("/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    return _out(db, _portfolio(db, portfolio_id))


@router.post("/{portfolio_id}/live-ack", response_model=PortfolioOut)
def live_ack(portfolio_id: int, _: LiveAck, db: Session = Depends(get_db)):
    pf = _portfolio(db, portfolio_id)
    if pf.live_ack_at is None:
        pf.live_ack_at = datetime.now(timezone.utc)
    pf.mode = "live"
    db.commit()
    return _out(db, pf)


@router.post("/{portfolio_id}/paper", response_model=PortfolioOut)
def back_to_paper(portfolio_id: int, db: Session = Depends(get_db)):
    pf = _portfolio(db, portfolio_id)
    pf.mode, pf.live_ack_at = "paper", None  # a later switch to live needs a fresh acknowledgement
    db.commit()
    return _out(db, pf)


@router.get("/{portfolio_id}/today", response_model=list[TodayRow])
def today(portfolio_id: int, db: Session = Depends(get_db)):
    pf = _portfolio(db, portfolio_id)
    scores, prices = latest_scores(db), latest_prices(db)
    free = cash(db, pf)
    tripped = _breaker_tripped(pf, max((d for d, _ in prices.values()), default=None))
    active = {
        p.ticker_id: p
        for p in db.scalars(select(Position).where(Position.portfolio_id == pf.id, Position.status != "closed"))
    }
    rows = []
    for t in db.scalars(select(Ticker).order_by(Ticker.symbol)):
        score, px, pos = scores.get(t.id), prices.get(t.id), active.get(t.id)
        price_date, price = px if px else (None, None)
        holding = plan = note = None
        stats = position_stats(fills_for(db, pos.id)) if pos else None
        if pos and stats.held > 0 and price is not None:
            holding = HoldingOut(shares=stats.held, avg_entry=stats.avg_entry, stop=pos.stop, target=pos.target,
                                 unrealized_pnl=stats.held * (price - stats.avg_entry))
        if score and price is not None:
            if score.band in BUY_BANDS and pos is None:
                if tripped:
                    note = "circuit breaker tripped: new buying is paused for today"
                elif in_cooldown(db, pf.id, t.id, price_date):
                    note = "cooling down after a recent exit"
                elif ep := plan_entry(pf.total_value, pf.risk_tier, price, free):
                    plan = PlanOut(
                        kind="entry", shares=ep.shares, price=price, notional=ep.shares * price, stop=ep.stop,
                        target=ep.target, risk_amount=ep.risk_amount, binding=ep.binding,
                        tranches=[TrancheOut(label="now" if tr.offset_days == 0 else f"+{tr.offset_days}d",
                                             offset_days=tr.offset_days, shares=tr.shares) for tr in ep.tranches],
                    )
                else:
                    note = "too small to size under this portfolio's limits"
            elif score.band in SELL_BANDS:
                if holding:
                    plan = PlanOut(kind="exit", shares=holding.shares, price=price, notional=holding.shares * price)
                else:
                    note = "no position to sell"
        rows.append(TodayRow(
            symbol=t.symbol, price=price, price_date=price_date, holding=holding, plan=plan, note=note,
            score=ScoreOut(as_of=score.computed_at, trend=score.trend, reversion=score.reversion,
                           rel_strength=score.rel_strength, vol_penalty=score.vol_penalty,
                           composite=score.composite, band=score.band) if score else None,
        ))
    return rows


@router.get("/{portfolio_id}/positions", response_model=PositionsOut)
def positions(portfolio_id: int, db: Session = Depends(get_db)):
    pf = _portfolio(db, portfolio_id)
    prices = latest_prices(db)
    symbols = {t.id: t.symbol for t in db.scalars(select(Ticker))}
    out = []
    for pos in db.scalars(select(Position).where(Position.portfolio_id == pf.id).order_by(Position.id.desc())):
        fills = fills_for(db, pos.id)
        st = position_stats(fills)
        px = prices.get(pos.ticker_id)
        out.append(PositionOut(
            id=pos.id, symbol=symbols[pos.ticker_id], status=pos.status, plan_date=pos.plan_date,
            planned_shares=pos.planned_shares, shares=st.held, avg_entry=st.avg_entry, stop=pos.stop,
            target=pos.target, trimmed=pos.trimmed, plan_cancelled=pos.plan_cancelled,
            close_reason=pos.close_reason, realized_pnl=st.realized,
            unrealized_pnl=st.held * (px[1] - st.avg_entry) if st.held and px else None,
            fills=[FillOut(side=f.side, shares=f.shares, price=f.price, data_date=f.data_date, reason=f.reason)
                   for f in fills],
        ))
    closed = [p for p in out if p.status == "closed"]
    return PositionsOut(
        summary=Summary(
            open=len(out) - len(closed), closed=len(closed),
            wins=sum(p.realized_pnl > 0 for p in closed), losses=sum(p.realized_pnl < 0 for p in closed),
            realized_pnl=sum(p.realized_pnl for p in out),
        ),
        positions=out,
    )
