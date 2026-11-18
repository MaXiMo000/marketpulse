from datetime import date, datetime, timezone

from app.models import CompositeScore, PriceSnapshot, Ticker

COMPOSITE = {"Strong Buy": 85, "Buy": 70, "Hold": 55, "Sell": 35, "Strong Sell": 15}


def add_ticker(session, symbol: str = "AAA") -> Ticker:
    t = Ticker(symbol=symbol, benchmark_symbol="SPY")
    session.add(t)
    session.commit()
    return t


def market(session, ticker: Ticker, day: date, band: str, price: float, hour: int = 15) -> datetime:
    """Record one cycle: a score in `band` and the day's close. Returns the cycle timestamp."""
    at = datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc)
    session.add(CompositeScore(ticker_id=ticker.id, computed_at=at, trend=0, reversion=0, rel_strength=0,
                               vol_penalty=0, composite=COMPOSITE[band], band=band))
    session.merge(PriceSnapshot(ticker_id=ticker.id, observed_at=day, close=price, ma20=price, ma100=price,
                                rsi14=50, ret_20d=0, ann_vol=20))
    session.commit()
    return at
