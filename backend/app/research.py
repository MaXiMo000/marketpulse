"""Cross-sectional factor research with a time split.

Each day, stocks are ranked by a factor and compared with what they did over the next `horizon` days.
The first part of the history is used to judge each factor; the last part is held back to confirm.
Run it with:  python -m app.research
"""
import json
import math
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

from app.backtest import align, scored_history
from app.indicators import ann_vol_pct

HORIZON = 20
MOMENTUM_LOOKBACK = 252   # bars needed for the 12-month momentum factor
MIN_NAMES = 8             # stocks needed on a day for a cross-section to count
T_THRESHOLD = 2.0

CURRENT = ["Composite (current)", "Trend", "Mean-reversion", "Relative strength", "Volatility (low is better)"]
CANDIDATES = ["Momentum 12-1", "Reversal 5d", "Reversal 21d", "Low volatility 60d"]
FACTORS = CURRENT + CANDIDATES

UNIVERSE = (
    "AAPL MSFT NVDA AMZN META GOOGL TSLA JPM XOM JNJ WMT KO "
    "INTC PFE BA DIS T VZ CVX PG HD UNH CSCO IBM MMM GE F GM CAT BAC WFC"
).split()


def build_panel(dates: list[date], closes: dict[str, list[float]], bench: list[float], horizon: int = HORIZON) -> list[dict]:
    """One row per stock per day: every factor as known at that close, and the return over the next `horizon` days."""
    rows = []
    for sym in sorted(closes):
        c = closes[sym]
        hist = scored_history(c, bench)
        for i in range(MOMENTUM_LOOKBACK, len(dates) - horizon):
            s = hist[i - 99]  # scored_history starts at index 99
            rows.append({
                "date": dates[i], "symbol": sym, "fwd": c[i + horizon] / c[i] - 1,
                "factors": {
                    "Composite (current)": s.composite,
                    "Trend": s.trend,
                    "Mean-reversion": s.reversion,
                    "Relative strength": s.rel_strength,
                    "Volatility (low is better)": -s.vol_penalty,
                    "Momentum 12-1": c[i - 21] / c[i - 252] - 1,
                    "Reversal 5d": -(c[i] / c[i - 5] - 1),
                    "Reversal 21d": -(c[i] / c[i - 21] - 1),
                    "Low volatility 60d": -ann_vol_pct(c[i - 60: i + 1], window=60),
                },
            })
    return rows


def _by_date(panel: list[dict]) -> dict[date, list[dict]]:
    out = defaultdict(list)
    for r in panel:
        out[r["date"]].append(r)
    return out


def daily_ics(panel: list[dict], factor: str, min_names: int = MIN_NAMES) -> list[tuple[date, float]]:
    """Rank correlation between the factor and the forward return, one value per day."""
    out = []
    for d, names in sorted(_by_date(panel).items()):
        if len(names) < min_names:
            continue
        try:
            out.append((d, statistics.correlation([n["factors"][factor] for n in names], [n["fwd"] for n in names], method="ranked")))
        except statistics.StatisticsError:  # every stock had the same factor value that day
            continue
    return out


def summarize_ics(ics: list[tuple[date, float]], horizon: int) -> dict:
    """Mean IC over all days. The t-statistic uses every `horizon`-th day, since neighbouring days share most of their window."""
    values = [v for _, v in ics]
    if not values:
        return {"n_dates": 0, "n_independent": 0, "mean_ic": None, "t_stat": None, "hit_rate": None}
    sub = values[::horizon]
    t = None
    if len(sub) >= 3 and statistics.stdev(sub) > 0:
        t = statistics.fmean(sub) / (statistics.stdev(sub) / math.sqrt(len(sub)))
    return {
        "n_dates": len(values), "n_independent": len(sub), "mean_ic": statistics.fmean(values),
        "t_stat": t, "hit_rate": sum(v > 0 for v in values) / len(values),
    }


def quintile_spread(panel: list[dict], factor: str, min_names: int = MIN_NAMES) -> float | None:
    """Average return of the top fifth minus the bottom fifth by the factor, per day: the economic size of the effect."""
    spreads = []
    for names in _by_date(panel).values():
        if len(names) < min_names:
            continue
        ranked = sorted(names, key=lambda n: n["factors"][factor])
        k = max(1, len(ranked) // 5)
        spreads.append(statistics.fmean(n["fwd"] for n in ranked[-k:]) - statistics.fmean(n["fwd"] for n in ranked[:k]))
    return statistics.fmean(spreads) if spreads else None


def cutoff_date(dates: list[date], train_frac: float) -> date:
    ordered = sorted(set(dates))
    return ordered[max(0, int(len(ordered) * train_frac) - 1)]


def evaluate(panel: list[dict], horizon: int = HORIZON, train_frac: float = 0.6) -> dict:
    """Per factor: summary on the training period and on the held-back test period.

    The last `horizon` training days are dropped so no training return window reaches into the test period.
    """
    dates = sorted({r["date"] for r in panel})
    cut = cutoff_date(dates, train_frac)
    train_end = dates[max(0, dates.index(cut) - horizon)]
    train = [r for r in panel if r["date"] <= train_end]
    test = [r for r in panel if r["date"] > cut]
    out = {}
    for f in FACTORS:
        out[f] = {
            period: {**summarize_ics(daily_ics(rows, f), horizon), "spread": quintile_spread(rows, f)}
            for period, rows in (("train", train), ("test", test))
        }
    return out


def verdict(result: dict) -> str:
    """Only a factor that clears the bar in the training period AND the held-back period, with the same sign, counts."""
    tr, te = result["train"]["t_stat"], result["test"]["t_stat"]
    if tr is None or te is None:
        return "not enough data"
    if tr >= T_THRESHOLD and te >= T_THRESHOLD:
        return "WORKS in both periods"
    if tr <= -T_THRESHOLD and te <= -T_THRESHOLD:
        return "works in REVERSE in both periods"
    if abs(tr) >= T_THRESHOLD or abs(te) >= T_THRESHOLD:
        return "unstable (significant in only one period)"
    return "no signal"


# ---------- command line ----------

def _cached_closes(symbol: str, bars: int) -> list[tuple[date, float]]:
    from app.clients.twelvedata import fetch_daily_closes

    cache = Path(__file__).resolve().parents[2] / ".dev" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{symbol}_{bars}.json"
    if path.exists():
        return [(date.fromisoformat(d), c) for d, c in json.loads(path.read_text())]
    rows = fetch_daily_closes(symbol, outputsize=bars)
    path.write_text(json.dumps([(d.isoformat(), c) for d, c in rows]))
    return rows


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Cross-sectional factor research with a held-back test period.")
    parser.add_argument("symbols", nargs="*", default=UNIVERSE)
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--years", type=float, default=10)
    parser.add_argument("--horizon", type=int, default=HORIZON)
    parser.add_argument("--train-frac", type=float, default=0.6)
    args = parser.parse_args(argv)

    bars = int(args.years * 252) + MOMENTUM_LOOKBACK + 60
    series = {}
    for sym in sorted({s.upper() for s in args.symbols}):
        try:
            series[sym] = _cached_closes(sym, bars)
        except Exception as exc:  # a delisted or renamed ticker should not end the run
            print(f"skipping {sym}: {exc}")
    longest = max(len(v) for v in series.values())
    series = {s: v for s, v in series.items() if len(v) >= 0.9 * longest}
    dates, closes = align({**series, args.benchmark.upper(): _cached_closes(args.benchmark.upper(), bars)})
    bench = closes.pop(args.benchmark.upper())
    print(f"{len(closes)} stocks, {dates[0]} to {dates[-1]} ({len(dates)} days), {args.horizon}-day forward returns\n")

    panel = build_panel(dates, closes, bench, args.horizon)
    result = evaluate(panel, args.horizon, args.train_frac)
    cut = cutoff_date(sorted({r["date"] for r in panel}), args.train_frac)
    print(f"judged on data up to {cut}; confirmed on the {len({r['date'] for r in panel if r['date'] > cut})} days after it\n")
    pct = lambda v: "   n/a" if v is None else f"{v * 100:+5.2f}%"
    num = lambda v: "  n/a" if v is None else f"{v:+5.2f}"
    print(f"{'factor':28} | {'TRAIN IC':>8} {'t':>6} {'top-bottom':>10} | {'TEST IC':>8} {'t':>6} {'top-bottom':>10} | verdict")
    for f in FACTORS:
        r = result[f]
        print(
            f"{f:28} | {num(r['train']['mean_ic']):>8} {num(r['train']['t_stat']):>6} {pct(r['train']['spread']):>10} | "
            f"{num(r['test']['mean_ic']):>8} {num(r['test']['t_stat']):>6} {pct(r['test']['spread']):>10} | {verdict(r)}"
        )
    print("\nIC = average daily rank correlation between the factor and the next-period return (+ means higher factor, higher return).")
    print("top-bottom = average return of the top fifth minus the bottom fifth of stocks by the factor.")


if __name__ == "__main__":
    main()
