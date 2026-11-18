"""Position sizing and entry/exit plan rules (SPEC.md §7.3–7.4). Pure functions, no I/O."""
import math
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Tier:
    risk_per_trade_pct: float
    max_position_pct: float
    daily_loss_limit_pct: float  # circuit breaker: new buying pauses for the day beyond this fall in equity


TIERS = {
    "conservative": Tier(0.005, 0.03, 0.01),
    "moderate": Tier(0.01, 0.06, 0.02),
    "aggressive": Tier(0.02, 0.10, 0.03),
}

STOP_PCT = 0.08            # initial stop-loss distance below entry
TARGET_PCT = 0.20          # take-profit level above entry
TRAIL_TRIGGER_PCT = 0.10   # trailing stop starts once the high is this far above entry
TRAIL_PCT = 0.05           # ...and then follows the high at this distance (tighter than the initial stop)
TRIM_FRACTION = 0.5        # share of the position sold at the take-profit level
TRANCHE_OFFSETS = (0, 2, 4)  # trading days after the plan date


@dataclass(frozen=True)
class Tranche:
    offset_days: int
    shares: int


@dataclass(frozen=True)
class EntryPlan:
    shares: int
    entry_price: float
    stop: float
    target: float
    risk_amount: float   # money lost if the full position is stopped out
    binding: str         # which limit set the size: 'tier' | 'risk' | 'cash'
    tranches: list[Tranche]


def size_position(portfolio_value: float, tier: str, entry_price: float, stop_pct: float = STOP_PCT) -> tuple[int, str]:
    """Two independent caps; the smaller wins. The tier cap is a hard rail, conviction never raises it."""
    t = TIERS[tier]
    risk_based = portfolio_value * t.risk_per_trade_pct / (entry_price * stop_pct)
    cap_based = portfolio_value * t.max_position_pct / entry_price
    return math.floor(min(risk_based, cap_based)), ("risk" if risk_based < cap_based else "tier")


def split_tranches(shares: int) -> list[int]:
    """Three near-equal tranches, remainder in the first; empty tranches are dropped."""
    base = shares // 3
    return [n for n in (shares - 2 * base, base, base) if n > 0]


def plan_entry(portfolio_value: float, tier: str, entry_price: float, cash: float | None = None) -> EntryPlan | None:
    shares, binding = size_position(portfolio_value, tier, entry_price)
    if cash is not None and math.floor(cash / entry_price) < shares:
        shares, binding = math.floor(cash / entry_price), "cash"
    if shares < 1:
        return None
    return EntryPlan(
        shares=shares,
        entry_price=entry_price,
        stop=entry_price * (1 - STOP_PCT),
        target=entry_price * (1 + TARGET_PCT),
        risk_amount=shares * entry_price * STOP_PCT,
        binding=binding,
        tranches=[Tranche(off, n) for off, n in zip(TRANCHE_OFFSETS, split_tranches(shares))],
    )


def trail_stop(current_stop: float, avg_entry: float, high_water: float) -> float:
    """Tightens the stop once the profit threshold is reached; never loosens it."""
    # tolerance absorbs float error in avg_entry * 1.10
    if high_water - avg_entry * (1 + TRAIL_TRIGGER_PCT) >= -1e-9:
        return max(current_stop, high_water * (1 - TRAIL_PCT))
    return current_stop


def add_trading_days(start: date, n: int) -> date:
    """Weekdays only; exchange holidays are not modelled."""
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d
