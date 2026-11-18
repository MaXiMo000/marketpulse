"""Technical indicators from a list of daily closes, oldest first."""
import math
import statistics
from dataclasses import dataclass

MIN_CLOSES = 100  # MA100 is the longest window


@dataclass(frozen=True)
class Indicators:
    ma20: float
    ma100: float
    rsi14: float
    ret_20d: float
    ann_vol_pct: float


def moving_average(closes: list[float], n: int) -> float:
    return sum(closes[-n:]) / n


def ret(closes: list[float], n: int) -> float:
    return closes[-1] / closes[-1 - n] - 1


def rsi(closes: list[float], period: int = 14) -> float:
    """Wilder's RSI: seed with a simple average, then smooth."""
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def ann_vol_pct(closes: list[float], window: int = 20) -> float:
    """Sample stdev of the last `window` daily log returns, annualized (252 days), in percent."""
    tail = closes[-(window + 1):]
    log_returns = [math.log(b / a) for a, b in zip(tail, tail[1:])]
    return statistics.stdev(log_returns) * math.sqrt(252) * 100


def compute(closes: list[float]) -> Indicators:
    if len(closes) < MIN_CLOSES:
        raise ValueError(f"need at least {MIN_CLOSES} closes, got {len(closes)}")
    return Indicators(
        ma20=moving_average(closes, 20),
        ma100=moving_average(closes, 100),
        rsi14=rsi(closes),
        ret_20d=ret(closes, 20),
        ann_vol_pct=ann_vol_pct(closes),
    )
