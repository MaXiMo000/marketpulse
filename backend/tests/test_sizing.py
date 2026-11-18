from datetime import date

import pytest

from app.sizing import TIERS, add_trading_days, plan_entry, size_position, split_tranches, trail_stop


def test_hand_computed_plan_moderate_tier():
    # risk-based: 100000 * 0.01 / (100 * 0.08) = 125 shares; cap-based: 100000 * 0.06 / 100 = 60 shares
    plan = plan_entry(portfolio_value=100_000, tier="moderate", entry_price=100)
    assert plan.shares == 60
    assert plan.binding == "tier"
    assert plan.stop == pytest.approx(92)
    assert plan.target == pytest.approx(120)
    assert plan.risk_amount == pytest.approx(60 * 100 * 0.08)
    assert [t.shares for t in plan.tranches] == [20, 20, 20]
    assert [t.offset_days for t in plan.tranches] == [0, 2, 4]


def test_tier_cap_wins_when_risk_based_would_allow_more():
    # tight 2% stop: risk-based = 100000 * 0.01 / (100 * 0.02) = 500 shares, cap = 60
    shares, binding = size_position(100_000, "moderate", 100, stop_pct=0.02)
    assert (shares, binding) == (60, "tier")


def test_risk_binds_when_stop_is_wide():
    # conservative, 50% stop: risk-based = 100000 * 0.005 / (100 * 0.5) = 10 shares, cap = 30
    assert size_position(100_000, "conservative", 100, stop_pct=0.5) == (10, "risk")


@pytest.mark.parametrize("tier", list(TIERS))
@pytest.mark.parametrize("stop_pct", [0.005, 0.01, 0.02, 0.05, 0.08, 0.15, 0.3, 0.5])
@pytest.mark.parametrize("price", [3.5, 100, 512.1, 4000])
def test_invariant_position_value_never_exceeds_tier_cap(tier, stop_pct, price):
    value = 250_000
    shares, _ = size_position(value, tier, price, stop_pct=stop_pct)
    assert shares * price <= value * TIERS[tier].max_position_pct + 1e-9


def test_cash_limits_the_position_when_it_binds():
    # cap would allow 60 shares ($6,000) but only $2,500 of cash is free -> 25 shares
    plan = plan_entry(100_000, "moderate", 100, cash=2_500)
    assert plan.shares == 25
    assert plan.binding == "cash"


def test_unaffordable_plan_is_none():
    assert plan_entry(100_000, "moderate", 100, cash=50) is None
    assert plan_entry(1_000, "conservative", 500) is None  # cap allows 0.06 of a share


@pytest.mark.parametrize(
    "shares,expected",
    [(60, [20, 20, 20]), (10, [4, 3, 3]), (7, [3, 2, 2]), (2, [2]), (0, [])],
)
def test_split_tranches_covers_every_share_without_empty_tranches(shares, expected):
    assert split_tranches(shares) == expected
    assert sum(expected) == shares


@pytest.mark.parametrize(
    "high,expected",
    [(105, 92), (109.9, 92), (110, 104.5), (130, 123.5)],
)
def test_trailing_stop_tightens_only_after_profit_threshold(high, expected):
    assert trail_stop(current_stop=92, avg_entry=100, high_water=high) == pytest.approx(expected)


def test_trailing_stop_never_loosens():
    assert trail_stop(current_stop=123.5, avg_entry=100, high_water=112) == pytest.approx(123.5)


def test_add_trading_days_skips_weekends():
    assert add_trading_days(date(2025, 7, 4), 2) == date(2025, 7, 8)   # Fri + 2 -> Tue
    assert add_trading_days(date(2025, 7, 7), 4) == date(2025, 7, 11)  # Mon + 4 -> Fri
    assert add_trading_days(date(2025, 7, 9), 0) == date(2025, 7, 9)
