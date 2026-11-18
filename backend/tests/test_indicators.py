import pytest

from app.indicators import ann_vol_pct, compute, moving_average, ret, rsi


def test_moving_average_uses_last_n():
    assert moving_average([1, 2, 3, 4, 5], 3) == pytest.approx(4)


def test_ret_is_fraction_over_n_days():
    closes = [100.0] + [0.0] * 19 + [110.0]  # 20 steps apart
    assert ret(closes, 20) == pytest.approx(0.10)


def test_rsi_extremes():
    assert rsi([float(i) for i in range(1, 30)]) == 100
    assert rsi([float(i) for i in range(30, 1, -1)]) == 0
    assert rsi([100.0] * 20) == 50


def test_rsi_equal_gains_and_losses_is_50():
    # 14 changes: seven +1 and seven -1 -> avg gain == avg loss
    closes = [100.0 + (i % 2) for i in range(15)]
    assert rsi(closes) == pytest.approx(50)


def test_ann_vol_hand_computed():
    # log returns are +a and -a with a = ln(1.1); sample stdev = a*sqrt(2)
    # annualized: a * sqrt(2) * sqrt(252) * 100 = 213.97
    assert ann_vol_pct([100.0, 110.0, 100.0], window=2) == pytest.approx(213.97, abs=0.01)


def test_ann_vol_zero_for_constant_growth():
    closes = [100 * 1.01**i for i in range(30)]
    assert ann_vol_pct(closes) == pytest.approx(0, abs=1e-9)


def test_compute_needs_100_closes():
    with pytest.raises(ValueError):
        compute([100.0] * 99)


def test_compute_flat_series():
    i = compute([100.0] * 120)
    assert (i.ma20, i.ma100, i.rsi14, i.ret_20d, i.ann_vol_pct) == (100, 100, 50, 0, 0)
