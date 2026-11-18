import random
from datetime import date, timedelta

import pytest

from app.backtest import (
    align, calibrate, edge_verdict, equity_metrics, run_backtest, scored_history, trade_stats,
)

D0 = date(2023, 1, 2)


def walk(n, drift, vol, seed, start=100.0):
    rng = random.Random(seed)
    price, out = start, []
    for i in range(n):
        price *= 1 + drift + rng.gauss(0, vol)
        out.append((D0 + timedelta(days=i), price))
    return out


# ---------- alignment and lookahead ----------

def test_align_keeps_only_dates_every_series_has():
    a = [(date(2024, 1, d), float(d)) for d in (1, 2, 3, 4)]
    b = [(date(2024, 1, d), float(d) * 10) for d in (2, 3, 4, 5)]
    dates, closes = align({"A": a, "B": b})
    assert dates == [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    assert closes["A"] == [2.0, 3.0, 4.0] and closes["B"] == [20.0, 30.0, 40.0]


def test_a_days_score_never_depends_on_future_data():
    closes = [c for _, c in walk(260, 0.0006, 0.012, seed=1)]
    bench = [c for _, c in walk(260, 0.0004, 0.008, seed=2)]
    full = scored_history(closes, bench)
    short = scored_history(closes[:180], bench[:180])
    assert len(short) < len(full)
    for i, s in enumerate(short):
        assert s.composite == full[i].composite and s.band == full[i].band


# ---------- calibration and verdict ----------

def test_calibration_hand_computed():
    rows = [("Buy", 0.02), ("Buy", 0.04), ("Buy", -0.01), ("Sell", -0.03)]
    table = {r["band"]: r for r in calibrate(rows)}
    assert table["Buy"]["n"] == 3
    assert table["Buy"]["mean"] == pytest.approx((0.02 + 0.04 - 0.01) / 3)
    assert table["Buy"]["median"] == pytest.approx(0.02)
    assert table["Buy"]["hit_rate"] == pytest.approx(2 / 3)
    assert table["Sell"]["hit_rate"] == 0
    assert table["Strong Buy"]["n"] == 0 and table["Strong Buy"]["mean"] is None


def noisy(mean, n, seed):
    rng = random.Random(seed)
    return [rng.gauss(mean, 0.05) for _ in range(n)]


def test_verdict_supported_when_buy_bands_clearly_beat_sell_bands():
    rows = [("Buy", x) for x in noisy(0.03, 400, 1)] + [("Sell", x) for x in noisy(-0.03, 400, 2)]
    assert edge_verdict(rows, horizon=20)["verdict"] == "supported"


def test_verdict_inverted_when_sell_bands_do_better():
    rows = [("Buy", x) for x in noisy(-0.03, 400, 3)] + [("Sell", x) for x in noisy(0.03, 400, 4)]
    assert edge_verdict(rows, horizon=20)["verdict"] == "inverted"


def test_verdict_inconclusive_for_noise_and_for_too_little_data():
    rows = [("Buy", x) for x in noisy(0.0, 400, 5)] + [("Sell", x) for x in noisy(0.0, 400, 6)]
    assert edge_verdict(rows, horizon=20)["verdict"] == "inconclusive"
    tiny = [("Buy", 0.5)] * 5 + [("Sell", -0.5)] * 5
    assert edge_verdict(tiny, horizon=20)["verdict"] == "inconclusive"


def test_overlapping_windows_shrink_the_effective_sample():
    rows = [("Buy", x) for x in noisy(0.01, 400, 7)] + [("Sell", x) for x in noisy(-0.01, 400, 8)]
    one = edge_verdict(rows, horizon=1)
    twenty = edge_verdict(rows, horizon=20)
    assert abs(twenty["t_stat"]) < abs(one["t_stat"])


# ---------- metrics ----------

def test_equity_metrics_hand_computed():
    dates = [D0 + timedelta(days=i) for i in range(4)]
    m = equity_metrics(dates, [100, 120, 90, 110])
    assert m["total_return"] == pytest.approx(0.10)
    assert m["max_drawdown"] == pytest.approx(-0.25)   # 120 -> 90


def test_equity_metrics_flat_curve_has_no_risk_and_no_sharpe():
    dates = [D0 + timedelta(days=i) for i in range(30)]
    m = equity_metrics(dates, [100.0] * 30)
    assert (m["total_return"], m["max_drawdown"], m["volatility"]) == (0, 0, 0)
    assert m["sharpe"] is None


def test_trade_stats_hand_computed():
    trades = [
        {"pnl": 200.0, "cost": 1000.0, "days": 10, "reason": "target"},
        {"pnl": 100.0, "cost": 1000.0, "days": 30, "reason": "signal"},
        {"pnl": -80.0, "cost": 1000.0, "days": 5, "reason": "stop"},
    ]
    s = trade_stats(trades)
    assert (s["closed"], s["wins"], s["losses"]) == (3, 2, 1)
    assert s["win_rate"] == pytest.approx(2 / 3)
    assert s["profit_factor"] == pytest.approx(300 / 80)
    assert s["avg_win_pct"] == pytest.approx(0.15) and s["avg_loss_pct"] == pytest.approx(-0.08)
    assert s["avg_days_held"] == pytest.approx(15)
    assert s["exit_reasons"] == {"target": 1, "signal": 1, "stop": 1}


def test_trade_stats_with_no_trades_or_no_losses():
    assert trade_stats([])["closed"] == 0 and trade_stats([])["win_rate"] is None
    only_wins = trade_stats([{"pnl": 10.0, "cost": 100.0, "days": 3, "reason": "target"}])
    assert only_wins["profit_factor"] is None  # undefined, not infinity


# ---------- full replay ----------

@pytest.fixture(scope="module")
def result():
    series = {
        "UP": walk(420, 0.0012, 0.012, seed=11),
        "DOWN": walk(420, -0.0010, 0.014, seed=12),
        "FLAT": walk(420, 0.0, 0.010, seed=13),
    }
    bench = walk(420, 0.0004, 0.008, seed=14)
    return run_backtest(series, bench, tier="moderate", capital=100_000, benchmark_symbol="SPY")


def test_result_describes_the_run(result):
    p = result["params"]
    assert p["symbols"] == ["DOWN", "FLAT", "UP"] and p["benchmark"] == "SPY" and p["tier"] == "moderate"
    assert p["trading_days"] == 420 - 99
    assert len(result["equity_curve"]["dates"]) <= 260
    assert result["calibration"]["20"] and result["calibration"]["5"]
    assert result["edge"]["verdict"] in {"supported", "inverted", "inconclusive"}
    assert {"strategy", "benchmark", "equal_weight"} <= set(result["metrics"])
    assert result["caveats"]


def test_accounting_identity_holds_so_no_money_is_created_or_lost(result):
    a = result["accounting"]
    assert a["final_equity"] == pytest.approx(a["cash_end"] + a["positions_value_end"])
    assert a["final_equity"] - a["capital"] == pytest.approx(a["realized_total"] + a["unrealized_end"])


def test_the_portfolio_never_spends_money_it_does_not_have(result):
    assert result["accounting"]["min_cash"] >= -1e-6


def test_same_inputs_give_the_same_result():
    series = {"UP": walk(300, 0.001, 0.012, seed=21), "DOWN": walk(300, -0.001, 0.012, seed=22)}
    bench = walk(300, 0.0004, 0.008, seed=23)
    a = run_backtest(series, bench)
    b = run_backtest(series, bench)
    assert a["accounting"] == b["accounting"] and a["calibration"] == b["calibration"]


def test_too_little_history_is_refused():
    series = {"A": walk(150, 0.0, 0.01, seed=31)}
    with pytest.raises(ValueError, match="history"):
        run_backtest(series, walk(150, 0.0, 0.01, seed=32))


def test_exposure_matched_benchmark_hand_computed():
    from app.backtest import exposure_matched

    # half invested in a benchmark rising 10% a day: +5% a day on the whole account
    assert exposure_matched(100.0, [100, 110, 121], [0.5, 0.5, 0.5]) == pytest.approx([100, 105, 110.25])
    # not invested at all: the account does not move
    assert exposure_matched(100.0, [100, 110, 121], [0, 0, 0]) == pytest.approx([100, 100, 100])


def test_matched_benchmark_is_reported(result):
    assert "benchmark_matched" in result["metrics"]


# ---------- factor diagnostics ----------

def _score(trend=0.0, reversion=0.0, rel=0.0, vol=0.0, composite=50.0):
    from app.scoring import Score

    return Score(trend, reversion, rel, vol, composite, "Hold")


def test_factor_ic_is_plus_one_for_a_perfect_predictor_and_minus_one_for_a_perfect_contrarian():
    from app.backtest import factor_ic

    xs = [i / 100 for i in range(60)]
    obs = [(_score(trend=x, rel=-x, vol=0.0, composite=50 + x), x) for x in xs]
    by_name = {f["factor"]: f for f in factor_ic(obs, horizon=20)}
    assert by_name["Trend"]["ic"] == pytest.approx(1.0)
    assert by_name["Relative strength"]["ic"] == pytest.approx(-1.0)
    assert by_name["Composite"]["ic"] == pytest.approx(1.0)


def test_factor_ic_handles_a_constant_factor_and_flips_volatility_so_low_is_better():
    from app.backtest import factor_ic

    xs = [i / 100 for i in range(60)]
    obs = [(_score(vol=-x), x) for x in xs]          # penalty falls as the outcome rises
    by_name = {f["factor"]: f for f in factor_ic(obs, horizon=20)}
    assert by_name["Mean-reversion"]["ic"] is None    # constant column has no correlation
    assert by_name["Volatility (low is better)"]["ic"] == pytest.approx(1.0)


def test_factor_ic_t_stat_uses_the_effective_sample():
    from app.backtest import factor_ic

    rng = random.Random(9)
    obs = [(_score(trend=rng.random()), rng.gauss(0, 0.05)) for _ in range(600)]
    ic1 = factor_ic(obs, horizon=1)[0]
    ic20 = factor_ic(obs, horizon=20)[0]
    assert ic1["ic"] == pytest.approx(ic20["ic"])
    assert abs(ic20["t_stat"]) < abs(ic1["t_stat"])


def test_same_stocks_at_same_exposure_benchmark_is_reported(result):
    assert "equal_weight_matched" in result["metrics"]
    assert len(result["factor_ic"]) == 5
