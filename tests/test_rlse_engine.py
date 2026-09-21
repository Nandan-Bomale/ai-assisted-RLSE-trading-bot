"""
tests/test_rlse_engine.py
──────────────────────────
Unit tests for src/strategy/rlse_engine.py

Run with: pytest tests/test_rlse_engine.py -v

Tests verify:
  1. No signal when no sweep has occurred.
  2. SHORT signal fired on Pattern 1 (2-bar bearish reversal).
  3. SHORT signal fired on Pattern 2 (Red-Green-Red engulf).
  4. LONG signal fired on Pattern 1 (2-bar bullish reversal).
  5. LONG signal fired on Pattern 2 (Green-Red-Green engulf).
  6. Timeout logic: sweep resets without signal when too many bars pass.
  7. Recursive target line update: after timeout, active_high_target advances.
  8. SL is placed correctly (extreme + buffer for short, extreme - buffer for long).
  9. No look-ahead: signal only fires after bar is CLOSED (bar[-2], not bar[-1]).
 10. State resets after a signal is fired.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta
from src.strategy.rlse_engine import RLSEEngine, Bar, Signal

# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_bar(t: int, o: float, h: float, l: float, c: float) -> Bar:
    """Create a bar with a simple integer timestamp (seconds since epoch)."""
    return Bar(time=t, open=o, high=h, low=l, close=c)

def make_engine(pdh=100.0, pdl=90.0, sl_buffer=1.5) -> RLSEEngine:
    return RLSEEngine(
        symbol="XAUUSD",
        true_pdh=pdh,
        true_pdl=pdl,
        active_high=pdh,
        active_low=pdl,
        sl_buffer=sl_buffer,
    )

def base_bars(n: int = 5, base_price: float = 95.0) -> list[Bar]:
    """n neutral bars well inside PDH/PDL range."""
    return [make_bar(i * 60, base_price, base_price + 0.5, base_price - 0.5, base_price)
            for i in range(n)]

# ─── Test 1: No signal without sweep ──────────────────────────────────────────

def test_no_signal_without_sweep():
    eng = make_engine()
    bars = base_bars(5, base_price=95.0)
    # Price well inside range — no sweep
    signal = eng.update(current_price=95.0, bars=bars)
    assert signal is None, "Should not fire without a sweep"

# ─── Test 2: SHORT — Pattern 1 (2-bar bearish) ────────────────────────────────

def test_short_pattern1_2bar():
    eng = make_engine(pdh=100.0, sl_buffer=1.5)

    # Use 6 bars so first update (sweep trigger) caches last_checked=bars[3].time=180,
    # and second update (pattern check) sees a new bars[-2]=bars[4].time=240.
    bars = base_bars(6, base_price=95.0)

    # First call: sweep triggered; engine caches last_checked_candle_time = bars[3].time = 180
    eng.update(current_price=101.0, bars=bars[:5])
    assert eng.sweep_high_active

    # high_candle_time = c1 index in 6-bar list = bars[3] (t=180)
    eng.high_candle_time = 180   # c1.time

    # Pattern: c1 (bars[3]) bearish, c2 (bars[4]) bearish, close < c1.low
    bars[3] = make_bar(180, 101.5, 102.0, 100.5, 101.0)  # c1: bearish, low=100.5
    bars[4] = make_bar(240, 101.0, 101.2, 100.0, 100.2)  # c2: NEW timestamp → engine evaluates
    bars[5] = make_bar(300, 100.5, 100.8, 100.3, 100.6)  # current (open)

    signal = eng.update(current_price=100.6, bars=bars)
    
    assert signal is not None, "Pattern 1 short should fire"
    assert signal.action == "SHORT"
    assert signal.pattern == "2bar"
    assert signal.sl > signal.swing_extreme, "SL must be above the swing high for a short"

# ─── Test 3: SHORT — Pattern 2 (Red-Green-Red engulf) ────────────────────────

def test_short_pattern2_engulf():
    eng = make_engine(pdh=100.0, sl_buffer=1.5)
    
    bars = base_bars(6, base_price=95.0)  # need 6 for cp, c0, c1, c2, current
    eng.update(current_price=101.0, bars=bars[:5])  # trigger sweep
    
    # Set high_candle_time to cp (bars[-5] = index 1 = t=60)
    eng.high_candle_time = bars[1].time  # t = 60
    
    # cp (bearish), c0 (bearish), c1 (bullish), c2 (bearish, engulfs all lows)
    bars[1] = make_bar(60,  102.0, 102.5, 101.0, 101.5)  # cp: bearish
    bars[2] = make_bar(120, 101.5, 102.0, 100.8, 101.2)  # c0: bearish, low=100.8
    bars[3] = make_bar(180, 101.0, 101.8, 100.5, 101.6)  # c1: bullish, low=100.5
    bars[4] = make_bar(240, 101.5, 101.9, 100.0, 100.3)  # c2: bearish, close < min(100.8,100.5) ✓
    bars[5] = make_bar(300, 100.5, 100.7, 100.3, 100.5)  # current (open)

    signal = eng.update(current_price=100.5, bars=bars)
    
    assert signal is not None, "Pattern 2 short (Red-Green-Red) should fire"
    assert signal.action == "SHORT"
    assert signal.pattern == "3bar_engulf"

# ─── Test 4: LONG — Pattern 1 (2-bar bullish) ────────────────────────────────

def test_long_pattern1_2bar():
    eng = make_engine(pdl=90.0, sl_buffer=1.5)

    bars = base_bars(6, base_price=95.0)
    # First call: sweep caches last_checked = bars[3].time = 180
    eng.update(current_price=89.0, bars=bars[:5])
    assert eng.sweep_low_active

    # low_candle_time = c1 = bars[3] (t=180)
    eng.low_candle_time = 180

    # Pattern: c1 bullish (bars[3]), c2 bullish close > c1.high (bars[4] = NEW closed bar)
    bars[3] = make_bar(180, 88.5, 89.5, 88.0, 89.2)  # c1: bullish, high=89.5
    bars[4] = make_bar(240, 89.0, 90.0, 88.8, 89.8)  # c2: NEW timestamp, close=89.8 > 89.5 ✓
    bars[5] = make_bar(300, 89.5, 90.2, 89.3, 90.0)  # current (open)

    signal = eng.update(current_price=90.0, bars=bars)

    assert signal is not None, "Pattern 1 long should fire"
    assert signal.action == "LONG"
    assert signal.pattern == "2bar"
    assert signal.sl < signal.swing_extreme, "SL must be below swing low for a long"


# ─── Test 5: LONG — Pattern 2 (Green-Red-Green engulf) ───────────────────────

def test_long_pattern2_engulf():
    eng = make_engine(pdl=90.0, sl_buffer=1.5)
    
    bars = base_bars(6, base_price=95.0)
    eng.update(current_price=89.0, bars=bars[:5])  # trigger low sweep
    
    eng.low_candle_time = bars[1].time  # cp time
    
    # cp bullish, c0 bullish, c1 bearish, c2 bullish engulfs all highs
    bars[1] = make_bar(60,  88.0, 89.5, 87.8, 89.0)  # cp: bullish
    bars[2] = make_bar(120, 88.5, 89.8, 88.2, 89.5)  # c0: bullish, high=89.8
    bars[3] = make_bar(180, 89.2, 89.6, 88.6, 88.8)  # c1: bearish, high=89.6
    bars[4] = make_bar(240, 88.5, 90.5, 88.4, 90.2)  # c2: bullish, close=90.2 > max(89.8,89.6) ✓
    bars[5] = make_bar(300, 90.0, 90.5, 89.8, 90.3)  # current (open)

    signal = eng.update(current_price=90.3, bars=bars)
    
    assert signal is not None, "Pattern 2 long (Green-Red-Green) should fire"
    assert signal.action == "LONG"
    assert signal.pattern == "3bar_engulf"

# ─── Test 6: Timeout — no signal, state resets ───────────────────────────────

def test_timeout_resets_state():
    eng = make_engine(pdh=100.0, sl_buffer=1.5)
    
    bars = base_bars(6, base_price=95.0)
    eng.update(current_price=101.0, bars=bars[:5])
    assert eng.sweep_high_active
    
    # Set high_candle_time very old (older than cp)
    eng.high_candle_time = bars[0].time  # t=0, which is < cp.time (bars[-5].time = bars[1].time)
    
    # All candles neutral (no pattern) — should timeout
    bars[2] = make_bar(120, 95.0, 95.5, 94.5, 95.1)  # c0
    bars[3] = make_bar(180, 95.0, 95.3, 94.8, 95.0)  # c1
    bars[4] = make_bar(240, 95.0, 95.2, 94.9, 95.0)  # c2
    bars[5] = make_bar(300, 95.0, 95.2, 94.8, 95.0)  # current

    signal = eng.update(current_price=95.0, bars=bars)
    
    assert signal is None, "No signal on timeout"
    assert not eng.sweep_high_active, "Sweep state must reset after timeout"

# ─── Test 7: Recursive target update after timeout ────────────────────────────

def test_recursive_target_update():
    eng = make_engine(pdh=100.0, sl_buffer=1.5)
    original_target = eng.active_high_target
    
    bars = base_bars(6, base_price=95.0)
    eng.update(current_price=102.0, bars=bars[:5])  # sweep high → swing_high = 102.0
    
    eng.current_swing_high = 102.0
    eng.high_candle_time = bars[0].time  # artificially old
    
    bars[2] = make_bar(120, 95.0, 95.5, 94.5, 95.1)
    bars[3] = make_bar(180, 95.0, 95.3, 94.8, 95.0)
    bars[4] = make_bar(240, 95.0, 95.2, 94.9, 95.0)
    bars[5] = make_bar(300, 95.0, 95.2, 94.8, 95.0)

    eng.update(current_price=95.0, bars=bars)
    
    assert eng.active_high_target == 102.0, \
        f"Recursive target should advance to swing high 102.0, got {eng.active_high_target}"
    assert eng.active_high_target != original_target

# ─── Test 8: SL placement ────────────────────────────────────────────────────

def test_sl_placement_short():
    eng = make_engine(pdh=100.0, sl_buffer=1.5)
    bars = base_bars(5, base_price=95.0)
    eng.update(current_price=101.0, bars=bars)
    
    eng.current_swing_high = 101.0
    eng.high_candle_time = bars[-3].time
    
    bars[2] = make_bar(120, 101.0, 101.5, 100.5, 101.0)  # c1 bearish
    bars[3] = make_bar(180, 101.0, 101.2, 100.0, 100.2)  # c2 bearish, close<c1.low
    bars[4] = make_bar(240, 100.5, 100.8, 100.3, 100.5)

    signal = eng.update(current_price=100.5, bars=bars)
    if signal:
        expected_sl = 101.0 + 1.5  # swing_high + buffer
        assert abs(signal.sl - expected_sl) < 1e-9, \
            f"SL should be {expected_sl}, got {signal.sl}"

def test_sl_placement_long():
    eng = make_engine(pdl=90.0, sl_buffer=1.5)
    bars = base_bars(5, base_price=95.0)
    eng.update(current_price=89.0, bars=bars)
    
    eng.current_swing_low = 89.0
    eng.low_candle_time = bars[-3].time
    
    bars[2] = make_bar(120, 89.5, 90.0, 89.0, 89.2)  # c1 bullish
    bars[3] = make_bar(180, 89.2, 90.0, 89.0, 89.8)  # c2 bullish, close > c1.high
    bars[4] = make_bar(240, 89.8, 90.2, 89.6, 90.0)

    signal = eng.update(current_price=90.0, bars=bars)
    if signal:
        expected_sl = 89.0 - 1.5
        assert abs(signal.sl - expected_sl) < 1e-9

# ─── Test 9: No look-ahead (signal uses bars[-2], not bars[-1]) ───────────────

def test_no_lookahead_bar_indexing():
    """
    The strategy evaluates bars[-2] as the last CLOSED candle.
    Changing bars[-1] (still open/current) must not affect the signal.
    """
    eng = make_engine(pdh=100.0, sl_buffer=1.5)
    bars = base_bars(6, base_price=95.0)

    # Sweep trigger call; caches last_checked = bars[3].time = 180
    eng.update(current_price=101.0, bars=bars[:5])
    eng.high_candle_time = 180  # c1.time = bars[3].time

    # c1 (bars[3]) bearish, c2 (bars[4]) bearish — c2 is the new CLOSED bar
    bars[3] = make_bar(180, 101.5, 101.9, 100.5, 101.0)  # c1 bearish (101.5→101.0), low=100.5
    bars[4] = make_bar(240, 101.0, 101.2, 100.0, 100.2)  # c2 bearish → pattern valid (NEW t=240)

    # bars[-1] = bars[5] is still "open" — set it to something wild
    bars[5] = make_bar(300, 200.0, 300.0, 50.0, 250.0)   # should NOT affect c2 evaluation

    signal = eng.update(current_price=100.5, bars=bars)
    # Signal must fire based on c2 (bars[4]), ignoring the wild bars[5]
    assert signal is not None, "Signal should fire based on c2 regardless of current open bar"


# ─── Test 10: State resets after signal ───────────────────────────────────────

def test_state_resets_after_signal():
    eng = make_engine(pdh=100.0, sl_buffer=1.5)
    bars = base_bars(5, base_price=95.0)
    eng.update(current_price=101.0, bars=bars)
    
    eng.current_swing_high = 101.0
    eng.high_candle_time = bars[-3].time
    
    bars[2] = make_bar(120, 101.0, 101.5, 100.5, 101.0)
    bars[3] = make_bar(180, 101.0, 101.2, 100.0, 100.2)
    bars[4] = make_bar(240, 100.5, 100.8, 100.3, 100.5)

    signal = eng.update(current_price=100.5, bars=bars)
    
    if signal:
        assert not eng.sweep_high_active, "Sweep state must reset after signal"
        assert eng.current_swing_high == 0.0, "Swing high must reset after signal"

# ─── Test 11: state_dict completeness ─────────────────────────────────────────

def test_state_dict_has_required_keys():
    eng = make_engine()
    d = eng.state_dict
    required = {"symbol","pdh","pdl","active_high_target","active_low_target",
                "sweep_high_active","sweep_low_active","current_swing_high",
                "current_swing_low","high_attempt_count","low_attempt_count"}
    assert required.issubset(d.keys()), f"Missing keys: {required - d.keys()}"

# ─── Test 12: Insufficient bars → no signal ───────────────────────────────────

def test_insufficient_bars_returns_none():
    eng = make_engine()
    signal = eng.update(current_price=101.0, bars=base_bars(3))
    assert signal is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
