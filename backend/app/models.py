"""Phase 0 subset of SPEC.md §7.6: tickers, daily price snapshots, composite scores."""
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
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
