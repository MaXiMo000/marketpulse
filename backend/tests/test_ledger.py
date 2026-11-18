from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ledger import advance_all, advance_portfolio, cash, position_stats
from app.models import Base, Fill, Portfolio, Position
from helpers import add_ticker, market

MON = date(2025, 7, 7)
TUE, WED, THU, FRI = (MON + timedelta(days=i) for i in (1, 2, 3, 4))


@pytest.fixture
def s():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def pf(s):
    p = Portfolio(total_value=100_000, risk_tier="moderate")
    s.add(p)
    s.commit()
    return p


def ticker(s, symbol="AAA"):
    return add_ticker(s, symbol)


def step(s, pf, t, day, band, price, hour=15):
    advance_portfolio(s, pf, now=market(s, t, day, band, price, hour))
    s.commit()


def only_position(s) -> Position:
    return s.scalars(select(Position)).one()


def fills(s) -> list[Fill]:
    return list(s.scalars(select(Fill).order_by(Fill.id)))


def test_buy_signal_opens_a_sized_plan_and_fills_the_first_tranche(s, pf):
    t = ticker(s)
    step(s, pf, t, MON, "Buy", 100)
    pos = only_position(s)
    # moderate tier: cap 6% of 100k = 60 shares, split 20/20/20
    assert (pos.status, pos.planned_shares) == ("open", 60)
    assert pos.stop == pytest.approx(92) and pos.target == pytest.approx(120)
    [f] = fills(s)
    assert (f.side, f.shares, f.price, f.reason) == ("buy", 20, 100, "tranche")


def test_remaining_tranches_fill_on_their_due_days_only(s, pf):
    t = ticker(s)
    step(s, pf, t, MON, "Buy", 100)
    step(s, pf, t, TUE, "Buy", 102)
    assert len(fills(s)) == 1
    step(s, pf, t, WED, "Buy", 104)   # +2 trading days
    assert len(fills(s)) == 2
    step(s, pf, t, FRI, "Buy", 106)   # +4 trading days
    assert len(fills(s)) == 3
    stats = position_stats(fills(s))
    assert (stats.held, stats.avg_entry) == (60, pytest.approx(310 / 3))


def test_rerunning_the_same_cycle_changes_nothing(s, pf):
    t = ticker(s)
    at = market(s, t, MON, "Buy", 100)
    for _ in range(3):
        advance_portfolio(s, pf, now=at)
        s.commit()
    assert len(fills(s)) == 1
    assert len(s.scalars(select(Position)).all()) == 1


def test_signal_leaving_buy_bands_cancels_remaining_tranches(s, pf):
    t = ticker(s)
    step(s, pf, t, MON, "Buy", 100)
    step(s, pf, t, WED, "Hold", 100)
    step(s, pf, t, FRI, "Hold", 100)
    pos = only_position(s)
    assert (pos.status, pos.plan_cancelled) == ("open", True)
    assert position_stats(fills(s)).held == 20


def test_plan_cancelled_before_any_fill_closes_with_no_trades(s, pf):
    t = ticker(s)
    s.add(Position(portfolio_id=pf.id, ticker_id=t.id, status="planned", plan_date=MON,
                   planned_shares=60, stop=92, target=120, high_water=100))
    s.commit()
    step(s, pf, t, MON, "Hold", 100)
    pos = only_position(s)
    assert (pos.status, pos.close_reason) == ("closed", "cancelled")
    assert fills(s) == []


def test_stop_loss_sells_everything_and_realizes_the_loss(s, pf):
    t = ticker(s)
    step(s, pf, t, MON, "Buy", 100)
    step(s, pf, t, TUE, "Buy", 91)    # at or below the 92 stop
    pos = only_position(s)
    assert (pos.status, pos.close_reason) == ("closed", "stop")
    stats = position_stats(fills(s))
    assert (stats.held, stats.realized) == (0, pytest.approx(-180))
    assert len(fills(s)) == 2          # no tranche is bought into a stopped-out position


def test_signal_dropping_below_hold_sells_the_position(s, pf):
    t = ticker(s)
    step(s, pf, t, MON, "Buy", 100)
    step(s, pf, t, TUE, "Sell", 99)
    pos = only_position(s)
    assert (pos.status, pos.close_reason) == ("closed", "signal")


def test_take_profit_trims_half_cancels_the_rest_then_trailing_stop_exits(s, pf):
    t = ticker(s)
    step(s, pf, t, MON, "Buy", 100)
    step(s, pf, t, TUE, "Buy", 120)   # target
    pos = only_position(s)
    assert (pos.status, pos.trimmed, pos.plan_cancelled) == ("open", True, True)
    assert position_stats(fills(s)).held == 10
    step(s, pf, t, WED, "Buy", 125)   # new high; no further tranche is bought
    assert position_stats(fills(s)).held == 10
    assert pos.stop == pytest.approx(125 * 0.95)
    step(s, pf, t, THU, "Buy", 118)   # below the 118.75 trailing stop
    pos = only_position(s)
    assert (pos.status, pos.close_reason) == ("closed", "stop")
    assert position_stats(fills(s)).realized == pytest.approx(10 * 20 + 10 * 18)


def test_trailing_stop_tightens_after_ten_percent_gain(s, pf):
    t = ticker(s)
    step(s, pf, t, MON, "Buy", 100)
    step(s, pf, t, TUE, "Buy", 111)
    assert only_position(s).stop == pytest.approx(111 * 0.95)
    step(s, pf, t, WED, "Buy", 105)   # below the new stop, above the original 92
    assert only_position(s).close_reason == "stop"


def test_no_immediate_reentry_after_an_exit_then_allowed_after_cooldown(s, pf):
    t = ticker(s)
    step(s, pf, t, MON, "Buy", 100)
    step(s, pf, t, TUE, "Buy", 91)    # stopped out
    step(s, pf, t, TUE, "Buy", 91, hour=16)    # a later cycle, same day, signal still Buy
    step(s, pf, t, date(2025, 7, 14), "Buy", 90)   # 4 trading days after the exit
    assert len(s.scalars(select(Position)).all()) == 1
    step(s, pf, t, date(2025, 7, 15), "Buy", 90)   # 5 trading days after the exit
    assert len(s.scalars(select(Position)).all()) == 2


def test_plan_is_limited_by_free_cash(s):
    pf = Portfolio(total_value=1_000, risk_tier="aggressive")  # tier cap alone would allow 10 shares at $10
    s.add(pf)
    s.commit()
    held = ticker(s, "HELD")
    s.add(Position(portfolio_id=pf.id, ticker_id=held.id, status="open", plan_date=MON,
                   planned_shares=95, stop=9, target=12, high_water=10))
    s.commit()
    s.add(Fill(position_id=1, side="buy", shares=95, price=10, data_date=MON, reason="tranche"))
    s.commit()
    assert cash(s, pf) == pytest.approx(50)

    new = ticker(s, "NEW")
    step(s, pf, new, MON, "Buy", 10)
    pos = s.scalars(select(Position).where(Position.ticker_id == new.id)).one()
    assert pos.planned_shares == 5           # cash-limited, not the 10-share tier cap
    assert cash(s, pf) >= 0


def test_tickers_without_a_score_or_price_are_skipped(s, pf):
    ticker(s, "NOSCORE")
    advance_portfolio(s, pf)
    assert s.scalars(select(Position)).all() == []


def test_advance_all_commits_for_every_portfolio(s, pf):
    t = ticker(s)
    s.add(Portfolio(total_value=50_000, risk_tier="conservative"))
    s.commit()
    market(s, t, MON, "Strong Buy", 100)
    advance_all(s)
    assert len(s.scalars(select(Position)).all()) == 2


# ---------- daily-loss circuit breaker ----------
# 20 positions with their first tranche filled hold $40,000 (40% of equity), so a 6% fall costs 2.4%: past the 2% limit
# for the moderate tier, but above every 92 stop-loss.

def _many(s, n):
    return [ticker(s, f"T{i:02d}") for i in range(n)]


def _day(s, pf, tickers, day, band, price, hour=15):
    at = None
    for t in tickers:
        at = market(s, t, day, band, price, hour)
    advance_portfolio(s, pf, now=at)
    s.commit()


def _buys(s):
    return len([f for f in fills(s) if f.side == "buy"])


def test_breaker_trips_on_a_big_down_day_and_pauses_only_new_buying(s, pf):
    tickers = _many(s, 20)
    _day(s, pf, tickers, MON, "Buy", 100)
    _day(s, pf, tickers, TUE, "Buy", 100)
    assert _buys(s) == 20
    late = ticker(s, "LATE")
    for t in tickers:
        market(s, t, WED, "Buy", 94)                      # -6%: tranche 2 is due today, and LATE is a fresh Buy
    advance_portfolio(s, pf, now=market(s, late, WED, "Buy", 100))
    s.commit()

    s.refresh(pf)
    assert pf.breaker_date == WED
    assert _buys(s) == 20                                 # tranche 2 did not fill
    assert s.scalars(select(Position).where(Position.ticker_id == late.id)).first() is None


def test_exits_still_run_while_the_breaker_is_tripped(s, pf):
    tickers = _many(s, 20)
    _day(s, pf, tickers, MON, "Buy", 100)
    _day(s, pf, tickers, TUE, "Buy", 85)                  # a crash through every stop
    s.refresh(pf)
    assert pf.breaker_date == TUE
    assert [f.reason for f in fills(s) if f.side == "sell"] == ["stop"] * 20


def test_breaker_resets_on_the_next_data_day(s, pf):
    tickers = _many(s, 20)
    _day(s, pf, tickers, MON, "Buy", 100)
    _day(s, pf, tickers, TUE, "Buy", 100)
    late = ticker(s, "LATE")
    for t in tickers:
        market(s, t, WED, "Buy", 94)
    advance_portfolio(s, pf, now=market(s, late, WED, "Buy", 100))
    s.commit()
    assert s.scalars(select(Position).where(Position.ticker_id == late.id)).first() is None

    for t in tickers:
        market(s, t, THU, "Buy", 95)                      # a recovery day: no new breaker
    advance_portfolio(s, pf, now=market(s, late, THU, "Buy", 100))
    s.commit()
    assert s.scalars(select(Position).where(Position.ticker_id == late.id)).first() is not None


def test_small_moves_never_trip_the_breaker(s, pf):
    tickers = _many(s, 20)
    _day(s, pf, tickers, MON, "Buy", 100)
    _day(s, pf, tickers, TUE, "Buy", 99)                  # -1% on 40% of equity = -0.4%
    s.refresh(pf)
    assert pf.breaker_date is None


def test_baseline_is_the_previous_days_equity_and_one_snapshot_is_kept_per_day(s, pf):
    from app.models import EquitySnapshot

    tickers = _many(s, 10)
    _day(s, pf, tickers, MON, "Buy", 100)
    _day(s, pf, tickers, MON, "Buy", 100, hour=16)        # a second cycle on the same day
    snaps = s.scalars(select(EquitySnapshot).order_by(EquitySnapshot.data_date)).all()
    assert len(snaps) == 1 and snaps[0].data_date == MON
    assert snaps[0].equity == pytest.approx(100_000)      # bought at the same close it is valued at

    _day(s, pf, tickers, TUE, "Buy", 110)
    assert [round(x.equity) for x in s.scalars(select(EquitySnapshot).order_by(EquitySnapshot.data_date))] == [100_000, 102_000]


def test_breaker_decision_is_a_pure_comparison_against_the_tier_limit():
    from app.ledger import breaker_tripped

    assert breaker_tripped(equity_now=97_900, prior_equity=100_000, tier="moderate")       # -2.1% vs a 2% limit
    assert not breaker_tripped(equity_now=98_100, prior_equity=100_000, tier="moderate")   # -1.9%
    assert breaker_tripped(equity_now=98_500, prior_equity=100_000, tier="conservative")   # -1.5% vs 1%
    assert not breaker_tripped(equity_now=105_000, prior_equity=100_000, tier="aggressive")
    assert not breaker_tripped(equity_now=0, prior_equity=0, tier="moderate")               # no baseline: never trips
