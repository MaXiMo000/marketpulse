import random
from datetime import date, timedelta

import pytest

from app.backtest import scored_history
from app.research import (
    build_panel, cutoff_date, daily_ics, quintile_spread, summarize_ics,
)
from app.signal import evaluate

D0 = date(2015, 1, 1)


def walk(n, drift, vol, seed, start=100.0):
    rng = random.Random(seed)
    price, out = start, []
    for _ in range(n):
        price *= 1 + drift + rng.gauss(0, vol)
        out.append(price)
    return out


def rows(day, factor_values, fwd_values, symbols=None):
    symbols = symbols or [f"S{i}" for i in range(len(factor_values))]
    return [{"date": day, "symbol": s, "factors": {"f": f}, "fwd": r} for s, f, r in zip(symbols, factor_values, fwd_values)]


# ---------- cross-sectional correlation ----------

def test_daily_ic_is_plus_one_when_ranking_matches_outcome_and_minus_one_when_reversed():
    d = D0
    good = rows(d, [1, 2, 3, 4, 5], [0.01, 0.02, 0.03, 0.04, 0.05])
    bad = rows(d + timedelta(days=1), [1, 2, 3, 4, 5], [0.05, 0.04, 0.03, 0.02, 0.01])
    ics = dict(daily_ics(good + bad, "f", min_names=5))
    assert ics[d] == pytest.approx(1.0) and ics[d + timedelta(days=1)] == pytest.approx(-1.0)


def test_days_with_too_few_names_or_a_constant_factor_are_skipped():
    few = rows(D0, [1, 2, 3], [0.1, 0.2, 0.3])
    flat = rows(D0 + timedelta(days=1), [7, 7, 7, 7, 7], [0.1, 0.2, 0.3, 0.4, 0.5])
    assert daily_ics(few + flat, "f", min_names=5) == []


def test_summary_counts_independent_observations_not_overlapping_days():
    rng = random.Random(3)
    ics = [(D0 + timedelta(days=i), 0.05 + rng.gauss(0, 0.2)) for i in range(100)]
    s = summarize_ics(ics, horizon=20)
    assert s["n_dates"] == 100 and s["n_independent"] == 5
    assert s["mean_ic"] == pytest.approx(sum(v for _, v in ics) / 100)
    assert 0 <= s["hit_rate"] <= 1


def test_summary_of_nothing_is_empty_not_an_error():
    s = summarize_ics([], horizon=20)
    assert s["n_dates"] == 0 and s["mean_ic"] is None and s["t_stat"] is None


def test_quintile_spread_hand_computed():
    # factor 1..10, outcome = factor/100: top 2 average 9.5%, bottom 2 average 1.5%
    data = rows(D0, list(range(1, 11)), [i / 100 for i in range(1, 11)])
    assert quintile_spread(data, "f", min_names=10) == pytest.approx(0.08)


def test_cutoff_date_splits_by_time():
    dates = [D0 + timedelta(days=i) for i in range(100)]
    cut = cutoff_date(dates, 0.6)
    assert sum(d <= cut for d in dates) == 60


# ---------- the panel ----------

def test_panel_factor_definitions_by_hand():
    closes = [100.0 + j for j in range(400)]      # a straight line, close[j] = 100 + j
    dates = [D0 + timedelta(days=j) for j in range(400)]
    panel = build_panel(dates, {"A": closes, "B": closes}, closes)
    row = next(r for r in panel if r["symbol"] == "A" and r["date"] == dates[300])
    assert row["factors"]["Momentum 12-1"] == pytest.approx(closes[279] / closes[48] - 1)
    assert row["factors"]["Reversal 5d"] == pytest.approx(-(closes[300] / closes[295] - 1))
    assert row["factors"]["Reversal 21d"] == pytest.approx(-(closes[300] / closes[279] - 1))
    assert row["fwd"] == pytest.approx(closes[320] / closes[300] - 1)


def test_panel_never_uses_future_data_in_a_factor():
    closes = {s: walk(500, 0.0005, 0.012, seed=i) for i, s in enumerate("ABC")}
    bench = walk(500, 0.0003, 0.008, seed=9)
    dates = [D0 + timedelta(days=j) for j in range(500)]
    full = build_panel(dates, closes, bench)
    short = build_panel(dates[:420], {s: c[:420] for s, c in closes.items()}, bench[:420])
    by_key = {(r["date"], r["symbol"]): r["factors"] for r in full}
    assert short
    for r in short:
        assert r["factors"] == pytest.approx(by_key[(r["date"], r["symbol"])])


def test_windowed_score_matches_the_full_history_score():
    """scored_history looks back a bounded window for speed; that must not change the answer."""
    closes = walk(800, 0.0004, 0.013, seed=5)
    bench = walk(800, 0.0003, 0.009, seed=6)
    hist = scored_history(closes, bench)
    for i in (300, 550, 799):
        full = evaluate(closes[: i + 1], bench[: i + 1])[1]
        assert hist[i - 99].composite == pytest.approx(full.composite, abs=1e-3)
