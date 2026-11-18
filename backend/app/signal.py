"""The single path from a price history to a composite score. The worker and the backtest both call this."""
from app.indicators import Indicators, compute, ret
from app.scoring import Score, score


def evaluate(closes: list[float], bench_closes: list[float]) -> tuple[Indicators, Score]:
    """Indicators and score using only the data given (oldest first). Raises ValueError on too little history."""
    ind = compute(closes)
    s = score(ind.ma20, ind.ma100, ind.rsi14, ind.ret_20d, ret(bench_closes, 20), ind.ann_vol_pct)
    return ind, s
