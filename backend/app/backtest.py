"""Backtest: replays the real paper ledger over historical closes and measures the score and the strategy.

Two separate questions are answered:
  1. Do the bands predict anything? (forward returns by band, relative to the benchmark)
  2. Does the whole strategy (sizing, tranches, stops) beat holding the benchmark?

The replay uses the production signal and ledger code unchanged, one simulated cycle per trading day,
and only data up to that day is ever visible.
"""
import math
import statistics
from collections import Counter
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.indicators import MIN_CLOSES
from app.ledger import advance_portfolio, cash, fills_for, position_stats
from app.models import Base, CompositeScore, Portfolio, Position, PriceSnapshot, Ticker
from app.scoring import Score
from app.signal import evaluate

BANDS = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
HORIZONS = (5, 20)
PRIMARY_HORIZON = 20
MIN_EFFECTIVE_N = 10      # independent observations needed on each side before a verdict is given
T_THRESHOLD = 2.0
TRADING_DAYS = 252
MAX_CURVE_POINTS = 250

CAVEATS = [
    "The universe is the tickers you chose today. Companies that did well tend to be the ones people pick, which flatters any strategy (survivorship bias).",
    "Signals and fills use the same day's close. Real execution would see slippage and delay.",
    "No commissions, spreads or taxes are included.",
    "The formula and all rule constants were fixed before this test and were not tuned on this data, but the test period is one market regime.",
    "Forward-return windows overlap, so the verdict counts independent observations as days divided by the horizon, not days.",
    "Past results describe the past. A transparent formula is not a proven edge.",
]


# ---------- data preparation ----------

def align(series: dict[str, list[tuple[date, float]]]) -> tuple[list[date], dict[str, list[float]]]:
    """Restrict every series to the dates they all share."""
    common = set.intersection(*(set(d for d, _ in rows) for rows in series.values()))
    dates = sorted(common)
    by_date = {sym: dict(rows) for sym, rows in series.items()}
    return dates, {sym: [by_date[sym][d] for d in dates] for sym in series}


LOOKBACK = 300  # bars of history a score can depend on; RSI smoothing has fully converged well before this


def scored_history(closes: list[float], bench: list[float]) -> list[Score]:
    """Score for each day from the first with enough history. Entry k is for index MIN_CLOSES-1+k, using data up to it only."""
    out = []
    for i in range(MIN_CLOSES - 1, len(closes)):
        lo = max(0, i - LOOKBACK + 1)
        out.append(evaluate(closes[lo: i + 1], bench[lo: i + 1])[1])
    return out


# ---------- statistics ----------

def calibrate(rows: list[tuple[str, float]]) -> list[dict]:
    """Per band: observations, mean and median excess return, and the share of observations that beat the benchmark."""
    out = []
    for band in BANDS:
        xs = [x for b, x in rows if b == band]
        out.append({
            "band": band,
            "n": len(xs),
            "mean": statistics.fmean(xs) if xs else None,
            "median": statistics.median(xs) if xs else None,
            "hit_rate": sum(x > 0 for x in xs) / len(xs) if xs else None,
        })
    return out


def edge_verdict(rows: list[tuple[str, float]], horizon: int) -> dict:
    """Do Buy-band observations out-return Sell-band ones? Welch t-test on an effective sample of days / horizon."""
    buy = [x for b, x in rows if b in ("Strong Buy", "Buy")]
    sell = [x for b, x in rows if b in ("Sell", "Strong Sell")]
    eff_buy, eff_sell = len(buy) / horizon, len(sell) / horizon
    result = {
        "horizon": horizon, "n_buy": len(buy), "n_sell": len(sell),
        "effective_n_buy": eff_buy, "effective_n_sell": eff_sell,
        "buy_mean": statistics.fmean(buy) if buy else None,
        "sell_mean": statistics.fmean(sell) if sell else None,
        "spread": None, "t_stat": None, "verdict": "inconclusive",
        "reason": "not enough independent observations in the Buy and Sell bands",
    }
    if eff_buy < MIN_EFFECTIVE_N or eff_sell < MIN_EFFECTIVE_N:
        return result
    spread = result["buy_mean"] - result["sell_mean"]
    se = math.sqrt(statistics.variance(buy) / eff_buy + statistics.variance(sell) / eff_sell)
    t = spread / se if se > 0 else 0.0
    result.update(spread=spread, t_stat=t)
    if t >= T_THRESHOLD:
        result.update(verdict="supported", reason="Buy-band days out-returned Sell-band days beyond what chance explains")
    elif t <= -T_THRESHOLD:
        result.update(verdict="inverted", reason="Sell-band days out-returned Buy-band days: the score pointed the wrong way")
    else:
        result.update(reason="the difference between Buy and Sell bands is within what chance can produce")
    return result


def equity_metrics(dates: list[date], equity: list[float]) -> dict:
    rets = [b / a - 1 for a, b in zip(equity, equity[1:]) if a > 0]
    years = (dates[-1] - dates[0]).days / 365.25
    peak, worst = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    sd = statistics.stdev(rets) if len(rets) > 1 else 0.0
    return {
        "total_return": equity[-1] / equity[0] - 1,
        "cagr": (equity[-1] / equity[0]) ** (1 / years) - 1 if years > 0 and equity[0] > 0 and equity[-1] > 0 else None,
        "max_drawdown": worst,
        "volatility": sd * math.sqrt(TRADING_DAYS),
        "sharpe": statistics.fmean(rets) / sd * math.sqrt(TRADING_DAYS) if sd > 0 else None,  # risk-free rate taken as 0
    }


FACTORS = [
    ("Trend", lambda s: s.trend),
    ("Mean-reversion", lambda s: s.reversion),
    ("Relative strength", lambda s: s.rel_strength),
    ("Volatility (low is better)", lambda s: -s.vol_penalty),
    ("Composite", lambda s: s.composite),
]


def factor_ic(obs: list[tuple[Score, float]], horizon: int) -> list[dict]:
    """Rank correlation (information coefficient) of each factor with the forward excess return.

    Positive means the factor pointed the right way. The t-statistic counts days / horizon observations,
    because forward windows overlap.
    """
    out = []
    n_eff = len(obs) / horizon
    for name, pick in FACTORS:
        xs, ys = [pick(s) for s, _ in obs], [y for _, y in obs]
        try:
            ic = statistics.correlation(xs, ys, method="ranked")
        except statistics.StatisticsError:  # a constant column has no rank correlation
            ic = None
        t = None
        if ic is not None and n_eff > 2:
            r = max(-0.999999, min(0.999999, ic))
            t = r * math.sqrt((n_eff - 2) / (1 - r * r))
        out.append({"factor": name, "ic": ic, "t_stat": t, "n": len(obs)})
    return out


def exposure_matched(capital: float, bench: list[float], exposure: list[float]) -> list[float]:
    """The benchmark held at the strategy's own daily exposure, the rest in cash: a like-for-like comparison."""
    out = [capital]
    for t in range(1, len(bench)):
        out.append(out[-1] * (1 + exposure[t - 1] * (bench[t] / bench[t - 1] - 1)))
    return out


def trade_stats(trades: list[dict]) -> dict:
    """`trades`: closed positions as {pnl, cost, days, reason}."""
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    gross_loss = abs(sum(t["pnl"] for t in losses))
    return {
        "closed": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / len(trades) if trades else None,
        "avg_win_pct": statistics.fmean(t["pnl"] / t["cost"] for t in wins) if wins else None,
        "avg_loss_pct": statistics.fmean(t["pnl"] / t["cost"] for t in losses) if losses else None,
        "profit_factor": sum(t["pnl"] for t in wins) / gross_loss if gross_loss > 0 else None,
        "avg_days_held": statistics.fmean(t["days"] for t in trades) if trades else None,
        "exit_reasons": dict(Counter(t["reason"] for t in trades)),
    }


# ---------- the replay ----------

def _simulate(dates, closes, bench, hist, tier, capital):
    """Runs the production ledger once per day. Returns equity per day plus accounting and trade data."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    symbols = sorted(closes)
    with Session(engine) as session:
        tickers = {sym: Ticker(symbol=sym, benchmark_symbol="BENCH") for sym in symbols}
        session.add_all(tickers.values())
        pf = Portfolio(total_value=capital, risk_tier=tier)
        session.add(pf)
        session.commit()
        sym_of = {t.id: sym for sym, t in tickers.items()}

        equity, exposure, min_cash = [], [], capital
        for k, i in enumerate(range(MIN_CLOSES - 1, len(dates))):
            d = dates[i]
            at = datetime(d.year, d.month, d.day, 21, 0, tzinfo=timezone.utc)
            for sym in symbols:
                s, price = hist[sym][k], closes[sym][i]
                session.add(CompositeScore(
                    ticker_id=tickers[sym].id, computed_at=at, trend=s.trend, reversion=s.reversion,
                    rel_strength=s.rel_strength, vol_penalty=s.vol_penalty, composite=s.composite, band=s.band,
                ))
                # the ledger reads only the close from a snapshot; the other columns are placeholders
                session.merge(PriceSnapshot(ticker_id=tickers[sym].id, observed_at=d, close=price, ma20=price,
                                            ma100=price, rsi14=50.0, ret_20d=0.0, ann_vol=0.0))
            advance_portfolio(session, pf, now=at)
            session.commit()

            free = cash(session, pf)
            held_value = 0.0
            for pos in session.scalars(select(Position).where(Position.status != "closed")):
                held_value += position_stats(fills_for(session, pos.id)).held * closes[sym_of[pos.ticker_id]][i]
            equity.append(free + held_value)
            exposure.append(held_value / (free + held_value) if free + held_value > 0 else 0.0)
            min_cash = min(min_cash, free)

        trades, realized_total, unrealized_end, positions_value_end = [], 0.0, 0.0, 0.0
        for pos in session.scalars(select(Position)):
            fills = fills_for(session, pos.id)
            if not fills:
                continue
            st = position_stats(fills)
            realized_total += st.realized
            if pos.status == "closed":
                trades.append({
                    "pnl": st.realized, "cost": st.avg_entry * st.bought, "reason": pos.close_reason,
                    "days": (max(f.data_date for f in fills) - min(f.data_date for f in fills)).days,
                })
            else:
                price = closes[sym_of[pos.ticker_id]][-1]
                unrealized_end += st.held * (price - st.avg_entry)
                positions_value_end += st.held * price
        open_positions = len(list(session.scalars(select(Position).where(Position.status != "closed"))))

    accounting = {
        "capital": capital, "final_equity": equity[-1], "cash_end": equity[-1] - positions_value_end,
        "positions_value_end": positions_value_end, "realized_total": realized_total,
        "unrealized_end": unrealized_end, "min_cash": min_cash, "open_positions": open_positions,
    }
    return equity, exposure, trades, accounting


def _downsample(values: list, step: int) -> list:
    picked = values[::step]
    return picked if (len(values) - 1) % step == 0 else picked + [values[-1]]


def run_backtest(
    series: dict[str, list[tuple[date, float]]],
    benchmark: list[tuple[date, float]],
    *,
    tier: str = "moderate",
    capital: float = 100_000.0,
    benchmark_symbol: str = "SPY",
) -> dict:
    dates, closes = align({**series, benchmark_symbol: benchmark})
    bench = closes.pop(benchmark_symbol)
    if len(dates) < MIN_CLOSES + 60:
        raise ValueError(f"need at least {MIN_CLOSES + 60} overlapping days of history, got {len(dates)}")
    symbols = sorted(closes)
    hist = {sym: scored_history(closes[sym], bench) for sym in symbols}

    calibration, edge, ic = {}, None, None
    for h in HORIZONS:
        obs = []
        for sym in symbols:
            for k, s in enumerate(hist[sym]):
                i = MIN_CLOSES - 1 + k
                if i + h < len(dates):
                    obs.append((s, (closes[sym][i + h] / closes[sym][i] - 1) - (bench[i + h] / bench[i] - 1)))
        rows = [(s.band, x) for s, x in obs]
        calibration[str(h)] = calibrate(rows)
        if h == PRIMARY_HORIZON:
            edge, ic = edge_verdict(rows, h), factor_ic(obs, h)

    equity, exposure, trades, accounting = _simulate(dates, closes, bench, hist, tier, capital)

    run_dates = dates[MIN_CLOSES - 1:]
    spy = [capital * bench[i] / bench[MIN_CLOSES - 1] for i in range(MIN_CLOSES - 1, len(dates))]
    equal = [
        sum(capital / len(symbols) * closes[sym][i] / closes[sym][MIN_CLOSES - 1] for sym in symbols)
        for i in range(MIN_CLOSES - 1, len(dates))
    ]
    matched = exposure_matched(capital, [bench[i] for i in range(MIN_CLOSES - 1, len(dates))], exposure)
    equal_matched = exposure_matched(capital, equal, exposure)
    step = max(1, math.ceil(len(run_dates) / MAX_CURVE_POINTS))

    return {
        "params": {
            "symbols": symbols, "benchmark": benchmark_symbol, "tier": tier, "capital": capital,
            "start_date": run_dates[0].isoformat(), "end_date": run_dates[-1].isoformat(), "trading_days": len(run_dates),
        },
        "calibration": calibration,
        "edge": edge,
        "factor_ic": ic,
        "metrics": {
            "strategy": {**equity_metrics(run_dates, equity), "avg_exposure": statistics.fmean(exposure)},
            "benchmark": equity_metrics(run_dates, spy),
            "benchmark_matched": equity_metrics(run_dates, matched),
            "equal_weight_matched": equity_metrics(run_dates, equal_matched),
            "equal_weight": equity_metrics(run_dates, equal),
        },
        "trades": trade_stats(trades),
        "accounting": accounting,
        "equity_curve": {
            "dates": [d.isoformat() for d in _downsample(run_dates, step)],
            "strategy": [round(v, 2) for v in _downsample(equity, step)],
            "benchmark": [round(v, 2) for v in _downsample(spy, step)],
            "benchmark_matched": [round(v, 2) for v in _downsample(matched, step)],
            "equal_weight_matched": [round(v, 2) for v in _downsample(equal_matched, step)],
            "equal_weight": [round(v, 2) for v in _downsample(equal, step)],
        },
        "caveats": CAVEATS,
    }


def _summary(r: dict) -> str:
    m, e, t = r["metrics"], r["edge"], r["trades"]
    pct = lambda v: "n/a" if v is None else f"{v * 100:+.1f}%"
    lines = [
        f"{', '.join(r['params']['symbols'])} vs {r['params']['benchmark']}, {r['params']['start_date']} to {r['params']['end_date']}",
        f"verdict ({e['horizon']}d, Buy vs Sell bands): {e['verdict']}  [{e['reason']}]",
        f"strategy {pct(m['strategy']['total_return'])}  max drawdown {pct(m['strategy']['max_drawdown'])}  exposure {m['strategy']['avg_exposure'] * 100:.0f}%",
        f"{r['params']['benchmark']} {pct(m['benchmark']['total_return'])}  max drawdown {pct(m['benchmark']['max_drawdown'])}",
        f"{r['params']['benchmark']} at the strategy's exposure {pct(m['benchmark_matched']['total_return'])}",
        f"the same stocks, equal weight, at the strategy's exposure {pct(m['equal_weight_matched']['total_return'])}",
        f"trades: {t['closed']} closed, win rate {pct(t['win_rate'])}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    from app.clients.twelvedata import fetch_daily_closes
    from app.db import SessionLocal
    from app.models import BacktestRun
    from app.sizing import TIERS

    parser = argparse.ArgumentParser(description="Backtest the score and paper-trading rules on real history and store the result.")
    parser.add_argument("symbols", nargs="+", help="tickers to include, e.g. NVDA AAPL MSFT")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--years", type=float, default=5)
    parser.add_argument("--tier", choices=list(TIERS), default="moderate")
    parser.add_argument("--capital", type=float, default=100_000)
    args = parser.parse_args(argv)

    bars = int(args.years * TRADING_DAYS) + MIN_CLOSES + 30
    symbols = sorted({s.upper() for s in args.symbols} - {args.benchmark.upper()})
    series = {sym: fetch_daily_closes(sym, outputsize=bars) for sym in symbols}
    benchmark = fetch_daily_closes(args.benchmark.upper(), outputsize=bars)
    result = run_backtest(series, benchmark, tier=args.tier, capital=args.capital, benchmark_symbol=args.benchmark.upper())
    with SessionLocal() as session:
        session.add(BacktestRun(result=json.dumps(result)))
        session.commit()
    print(_summary(result))


if __name__ == "__main__":
    main()
