"""SPEC.md §7.6 data model. Positions hold the plan; shares and entry price are derived from fills."""
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Ticker(Base):
    __tablename__ = "tickers"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True)
    benchmark_symbol: Mapped[str] = mapped_column(String(16), default="SPY")


class PriceSnapshot(Base):
    """One row per ticker per trading day; upserted every cycle."""

    __tablename__ = "price_snapshots"

    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), primary_key=True)
    observed_at: Mapped[date] = mapped_column(primary_key=True)
    close: Mapped[float]
    ma20: Mapped[float]
    ma100: Mapped[float]
    rsi14: Mapped[float]
    ret_20d: Mapped[float]
    ann_vol: Mapped[float]


class CompositeScore(Base):
    """One row per ticker per worker cycle; `computed_at` is shared by every ticker in a cycle."""

    __tablename__ = "composite_scores"
    __table_args__ = (UniqueConstraint("ticker_id", "computed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trend: Mapped[float]
    reversion: Mapped[float]
    rel_strength: Mapped[float]
    vol_penalty: Mapped[float]
    composite: Mapped[float]
    band: Mapped[str] = mapped_column(String(16))


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        CheckConstraint("mode = 'paper' OR live_ack_at IS NOT NULL", name="live_requires_ack"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    total_value: Mapped[float]
    risk_tier: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(8), default="paper")
    live_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Position(Base):
    """status: 'planned' (no tranche filled yet) | 'open' | 'closed'. At most one active position per ticker per portfolio."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"))
    status: Mapped[str] = mapped_column(String(8), default="planned")
    plan_date: Mapped[date]  # data date of the close the plan was sized on; tranche due dates count from here
    planned_shares: Mapped[int]  # total sized quantity; never changes after the plan is made
    stop: Mapped[float]
    target: Mapped[float]
    high_water: Mapped[float]
    trimmed: Mapped[bool] = mapped_column(default=False)
    plan_cancelled: Mapped[bool] = mapped_column(default=False)  # no further tranches will be bought
    close_reason: Mapped[str | None] = mapped_column(String(16), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Fill(Base):
    """One buy or sell at a price. `reason`: tranche | stop | target | signal | cancelled."""

    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    side: Mapped[str] = mapped_column(String(4))
    shares: Mapped[int]
    price: Mapped[float]
    data_date: Mapped[date]
    reason: Mapped[str] = mapped_column(String(16))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Alert(Base):
    """A ticker's band changed between two consecutive cycles. Written by the worker, read by the UI."""

    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("ticker_id", "computed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # the cycle that flipped the band
    from_band: Mapped[str] = mapped_column(String(16))
    to_band: Mapped[str] = mapped_column(String(16))
    from_score: Mapped[float]
    to_score: Mapped[float]
