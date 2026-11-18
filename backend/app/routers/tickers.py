from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CompositeScore, PriceSnapshot, Ticker
from app.schemas import History, HistoryPoint, ScoreOut, TickerIn, TickerOut, WatchlistRow

router = APIRouter(prefix="/v1")


@router.post("/watchlist/tickers", response_model=TickerOut, status_code=201)
def add_ticker(body: TickerIn, db: Session = Depends(get_db)):
    ticker = Ticker(symbol=body.symbol, benchmark_symbol=body.benchmark_symbol)
    db.add(ticker)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"{body.symbol} is already on the watchlist")
    return ticker


@router.get("/watchlist", response_model=list[WatchlistRow])
def watchlist(db: Session = Depends(get_db)):
    latest = (
        select(CompositeScore.ticker_id, func.max(CompositeScore.computed_at).label("at"))
        .group_by(CompositeScore.ticker_id)
        .subquery()
    )
    rows = db.execute(
        select(Ticker, CompositeScore)
        .outerjoin(latest, latest.c.ticker_id == Ticker.id)
        .outerjoin(
            CompositeScore,
            and_(CompositeScore.ticker_id == Ticker.id, CompositeScore.computed_at == latest.c.at),
        )
        .order_by(Ticker.symbol)
    ).all()
    return [
        WatchlistRow(
            symbol=t.symbol,
            benchmark_symbol=t.benchmark_symbol,
            score=ScoreOut(
                as_of=s.computed_at, trend=s.trend, reversion=s.reversion,
                rel_strength=s.rel_strength, vol_penalty=s.vol_penalty,
                composite=s.composite, band=s.band,
            ) if s else None,
        )
        for t, s in rows
    ]


@router.get("/tickers/{symbol}/history", response_model=History)
def history(symbol: str, days: int = Query(60, ge=1, le=365), db: Session = Depends(get_db)):
    symbol = symbol.upper()
    ticker = db.scalar(select(Ticker).where(Ticker.symbol == symbol))
    if ticker is None:
        raise HTTPException(404, f"{symbol} is not on the watchlist")
    snaps = db.scalars(
        select(PriceSnapshot)
        .where(PriceSnapshot.ticker_id == ticker.id)
        .order_by(PriceSnapshot.observed_at.desc())
        .limit(days)
    ).all()
    points = [HistoryPoint(date=p.observed_at, close=p.close, ma20=p.ma20, ma100=p.ma100) for p in reversed(snaps)]
    return History(symbol=symbol, points=points)
