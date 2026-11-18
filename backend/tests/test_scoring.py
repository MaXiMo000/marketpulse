import pytest

from app.scoring import band_for, score


def test_bullish_case_hand_computed():
    # trend: (110/100 - 1) * 300 = 30 -> clipped to 20
    # reversion: RSI 35 -> (40 - 35) * 0.4 = 2.0
    # rel_strength: (0.05 - 0.02) * 200 = 6.0
    # vol_penalty: (35 - 25) * 0.3 = 3.0
    # composite: 50 + 20 + 2 + 6 - 3 = 75
    s = score(ma20=110, ma100=100, rsi=35, ret_stock=0.05, ret_bench=0.02, ann_vol_pct=35)
    assert s.trend == pytest.approx(20)
    assert s.reversion == pytest.approx(2.0)
    assert s.rel_strength == pytest.approx(6.0)
    assert s.vol_penalty == pytest.approx(3.0)
    assert s.composite == pytest.approx(75)
    assert s.band == "Buy"


def test_neutral_inputs_score_fifty_and_hold():
    s = score(ma20=100, ma100=100, rsi=55, ret_stock=0.01, ret_bench=0.01, ann_vol_pct=20)
    assert s.composite == pytest.approx(50)
    assert s.band == "Hold"


def test_overbought_reversion_is_negative():
    # RSI 80 -> -(80 - 70) * 0.5 = -5
    assert score(100, 100, 80, 0, 0, 20).reversion == pytest.approx(-5)


def test_mid_rsi_has_no_reversion_effect():
    assert score(100, 100, 55, 0, 0, 20).reversion == 0


def test_composite_clamps_to_0_and_100():
    worst = score(ma20=80, ma100=100, rsi=90, ret_stock=-0.5, ret_bench=0.5, ann_vol_pct=100)
    assert worst.composite == 0
    assert worst.band == "Strong Sell"
    best = score(ma20=120, ma100=100, rsi=0, ret_stock=0.5, ret_bench=-0.5, ann_vol_pct=0)
    assert best.composite == 100
    assert best.band == "Strong Buy"


@pytest.mark.parametrize(
    "value,expected",
    [
        (100, "Strong Buy"), (80, "Strong Buy"), (79.99, "Buy"), (65, "Buy"),
        (64.99, "Hold"), (45, "Hold"), (44.99, "Sell"), (25, "Sell"),
        (24.99, "Strong Sell"), (0, "Strong Sell"),
    ],
)
def test_band_boundaries(value, expected):
    assert band_for(value) == expected
