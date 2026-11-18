"""Composite score and bands. Formula is SPEC.md §7.2; every factor is bounded and named."""
from dataclasses import dataclass


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class Score:
    trend: float
    reversion: float
    rel_strength: float
    vol_penalty: float
    composite: float
    band: str


def band_for(composite: float) -> str:
    if composite >= 80:
        return "Strong Buy"
    if composite >= 65:
        return "Buy"
    if composite >= 45:
        return "Hold"
    if composite >= 25:
        return "Sell"
    return "Strong Sell"


def score(
    ma20: float,
    ma100: float,
    rsi: float,
    ret_stock: float,
    ret_bench: float,
    ann_vol_pct: float,
) -> Score:
    """Returns are fractions (0.05 = 5%); ann_vol_pct is in percent (35 = 35%)."""
    trend = _clip((ma20 / ma100 - 1) * 300, -20, 20)
    if rsi <= 40:
        reversion = (40 - rsi) * 0.4
    elif rsi >= 70:
        reversion = -(rsi - 70) * 0.5
    else:
        reversion = 0.0
    rel_strength = _clip((ret_stock - ret_bench) * 200, -15, 15)
    vol_penalty = _clip((ann_vol_pct - 25) * 0.3, 0, 15)
    composite = _clip(50 + trend + reversion + rel_strength - vol_penalty, 0, 100)
    return Score(trend, reversion, rel_strength, vol_penalty, composite, band_for(composite))
