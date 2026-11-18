from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SYMBOL_PATTERN = r"^[A-Z0-9.\-]{1,16}$"


class TickerIn(BaseModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    benchmark_symbol: str = Field(default="SPY", pattern=SYMBOL_PATTERN)

    @field_validator("symbol", "benchmark_symbol", mode="before")
    @classmethod
    def _normalize(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class TickerOut(BaseModel):
    symbol: str
    benchmark_symbol: str


class ScoreOut(BaseModel):
    as_of: datetime
    trend: float
    reversion: float
    rel_strength: float
    vol_penalty: float
    composite: float
    band: str


class WatchlistRow(TickerOut):
    score: ScoreOut | None


class HistoryPoint(BaseModel):
    date: date
    close: float
    ma20: float
    ma100: float


class History(BaseModel):
    symbol: str
    points: list[HistoryPoint]


class PortfolioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # `mode` is not settable: every portfolio starts in paper

    total_value: float = Field(gt=0, le=1e9)
    risk_tier: Literal["conservative", "moderate", "aggressive"]


class LiveAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledge: Literal[True]  # must be the literal true: the user accepts the disclosure shown in the app


class PortfolioOut(BaseModel):
    id: int
    total_value: float
    risk_tier: str
    mode: str
    live_ack_at: datetime | None
    cash: float
    equity: float
    day_change: float          # equity vs the previous day's close, as a fraction
    daily_loss_limit: float    # the fall that trips the circuit breaker, as a fraction
    breaker_tripped: bool      # new buying is paused for the current data day


class TrancheOut(BaseModel):
    label: str
    offset_days: int
    shares: int


class PlanOut(BaseModel):
    kind: Literal["entry", "exit"]
    shares: int
    price: float
    notional: float
    stop: float | None = None
    target: float | None = None
    risk_amount: float | None = None
    binding: str | None = None  # which limit set the size: tier | risk | cash
    tranches: list[TrancheOut] = []


class HoldingOut(BaseModel):
    shares: int
    avg_entry: float
    unrealized_pnl: float
    stop: float
    target: float


class TodayRow(BaseModel):
    symbol: str
    score: ScoreOut | None
    price: float | None
    price_date: date | None
    holding: HoldingOut | None
    plan: PlanOut | None
    note: str | None


class FillOut(BaseModel):
    side: str
    shares: int
    price: float
    data_date: date
    reason: str


class PositionOut(BaseModel):
    id: int
    symbol: str
    status: str
    plan_date: date
    planned_shares: int
    shares: int
    avg_entry: float
    stop: float
    target: float
    trimmed: bool
    plan_cancelled: bool
    close_reason: str | None
    realized_pnl: float
    unrealized_pnl: float | None
    fills: list[FillOut]


class Summary(BaseModel):
    open: int
    closed: int
    wins: int
    losses: int
    realized_pnl: float


class PositionsOut(BaseModel):
    summary: Summary
    positions: list[PositionOut]


class AlertOut(BaseModel):
    symbol: str
    computed_at: datetime
    from_band: str
    to_band: str
    from_score: float
    to_score: float
    direction: Literal["up", "down"]


class BacktestOut(BaseModel):
    created_at: datetime
    result: dict[str, Any]
