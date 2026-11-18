from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

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
