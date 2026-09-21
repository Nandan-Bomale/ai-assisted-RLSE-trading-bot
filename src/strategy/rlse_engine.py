"""
src/strategy/rlse_engine.py
────────────────────────────
Pure, testable RLSE (Recursive Level Search Engine) strategy module.

This is the strategy logic extracted from legacy/strategy.py and made
dependency-free (no MT5, no Flask). It operates on plain Python objects
so the backtester, live runner, and unit tests can all import it identically.

Design:
  - Identical logic to legacy/strategy.py (SweepStrategy class).
  - All state is explicit (no hidden globals).
  - update() accepts a scalar price + a list of bar dicts (not a DataFrame)
    so the backtester can feed it bar by bar without pandas overhead.
  - Returns a Signal namedtuple or None.

Author: AI-Assisted RLSE Bot — Phase 0 extraction
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class Bar:
    """
    Lightweight OHLCV bar. Used by the strategy and backtester.
    time: a comparable object (datetime, int timestamp, pandas Timestamp).
    """
    time: Any
    open: float
    high: float
    low: float
    close: float
    tick_volume: float = 0.0
    real_volume: float = 0.0
    spread: float = 0.0

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def total_range(self) -> float:
        return self.high - self.low


@dataclass
class Signal:
    """
    Output of the strategy when a valid pattern is confirmed.
    Consumed by the Orchestrator → Risk Guard → Executor pipeline.
    """
    symbol: str
    action: str                    # "LONG" | "SHORT"
    sl: float                      # Stop loss price
    tp_target: float               # Runner / far target price (PDH or PDL)
    pattern: str                   # "2bar" | "3bar_engulf"
    swing_extreme: float           # The peak/valley that was swept
    entry_time: Any = None         # Timestamp of the triggering bar


class RLSEEngine:
    """
    Recursive Level Search Engine — pure Python, no external dependencies.

    Faithfully replicates legacy/strategy.py (SweepStrategy) with the
    following enhancements:
      - Works with Bar objects (not pandas DataFrames).
      - Exposes internal state as properties for feature extraction.
      - Logs reason for every state transition at DEBUG level.
      - Identical pattern logic so backtester results are comparable.
    """

    def __init__(
        self,
        symbol: str,
        true_pdh: float,
        true_pdl: float,
        active_high: float,
        active_low: float,
        sl_buffer: float,
    ):
        self.symbol = symbol

        # ── Level state ──────────────────────────────────────────────────
        self.pdh = true_pdh          # True previous-day high (for display)
        self.pdl = true_pdl          # True previous-day low  (for display)
        self.active_high_target = active_high
        self.active_low_target = active_low
        self.sl_buffer = sl_buffer

        # ── Sweep state ───────────────────────────────────────────────────
        self.sweep_high_active: bool = False
        self.sweep_low_active: bool = False

        self.current_swing_high: float = 0.0
        self.current_swing_low: float = float("inf")

        self.high_candle_time: Optional[Any] = None
        self.low_candle_time: Optional[Any] = None

        self.last_checked_candle_time: Optional[Any] = None

        # ── Attempt counters (for feature engine, not used in rules) ──────
        self.high_attempt_count: int = 0
        self.low_attempt_count: int = 0

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def update(self, current_price: float, bars: List[Bar]) -> Optional[Signal]:
        """
        Process one tick.

        Parameters
        ----------
        current_price : float
            Latest bid price.
        bars : List[Bar]
            Recent closed + current 1-minute bars, sorted oldest → newest.
            At least 5 bars required; the last element may still be open.

        Returns
        -------
        Signal or None
        """
        if not bars or len(bars) < 4:
            return None

        current_candle_time = bars[-1].time

        # 1. Update sweep state from live price
        self._track_sweeps(current_price, current_candle_time)

        # 2. Pattern evaluation (once per newly closed bar)
        # bars[-2] = last CLOSED candle (bars[-1] may still be open)
        last_closed_time = bars[-2].time
        if self.last_checked_candle_time == last_closed_time:
            return None  # Already evaluated this bar
        self.last_checked_candle_time = last_closed_time

        signal = None
        signal = signal or self._check_short_patterns(bars)
        signal = signal or self._check_long_patterns(bars)
        return signal

    def reset_daily(self, new_pdh: float, new_pdl: float, active_high: float, active_low: float):
        """
        Called at New York daily close to refresh PDH/PDL references.
        Preserves active high/low targets for mid-day bot restarts.
        """
        self.pdh = new_pdh
        self.pdl = new_pdl
        self.active_high_target = active_high
        self.active_low_target = active_low
        self._reset_sweep_state("high")
        self._reset_sweep_state("low")
        logger.info("[%s] Daily reset. New PDH=%.5f  PDL=%.5f", self.symbol, new_pdh, new_pdl)

    # ─────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    def _track_sweeps(self, price: float, candle_time: Any) -> None:
        """Update sweep tracking from latest tick price."""
        if price > self.active_high_target:
            if not self.sweep_high_active:
                logger.info(
                    "[%s] 🚨 HIGH swept (%.5f > %.5f). Watching for reversal...",
                    self.symbol, price, self.active_high_target,
                )
                self.sweep_high_active = True
                self.high_attempt_count += 1

            if price > self.current_swing_high:
                self.current_swing_high = price
                self.high_candle_time = candle_time

        if price < self.active_low_target:
            if not self.sweep_low_active:
                logger.info(
                    "[%s] 🚨 LOW swept (%.5f < %.5f). Watching for reversal...",
                    self.symbol, price, self.active_low_target,
                )
                self.sweep_low_active = True
                self.low_attempt_count += 1

            if price < self.current_swing_low:
                self.current_swing_low = price
                self.low_candle_time = candle_time

    def _check_short_patterns(self, bars: List[Bar]) -> Optional[Signal]:
        """Evaluate short-setup patterns after a high sweep."""
        if not self.sweep_high_active:
            return None

        # Alias candles (same indexing as legacy code)
        # bars[-1] = current (possibly open), bars[-2] = c2 (last closed), etc.
        c2 = bars[-2]  # last closed candle
        c1 = bars[-3]
        c0 = bars[-4]
        cp = bars[-5] if len(bars) >= 5 else c0

        # Pattern 1: two consecutive bearish candles, second closes below first's low
        p1 = (c1.is_bearish and c2.is_bearish and c2.close < c1.low)

        # Pattern 2: Red → Green → Red engulfing (rejects chop)
        p2 = (c0.is_bearish and c1.is_bullish and c2.is_bearish
              and c2.close < min(c0.low, c1.low))

        if p1 and self.high_candle_time in (c0.time, c1.time):
            logger.info("[%s] 🎯 SHORT p1 (2-bar reversal)", self.symbol)
            return self._build_short_signal(c2, "2bar")

        if p2 and self.high_candle_time in (cp.time, c0.time, c1.time):
            logger.info("[%s] 🎯 SHORT p2 (3-bar engulf)", self.symbol)
            return self._build_short_signal(c2, "3bar_engulf")

        # Timeout: extreme is older than 4 bars → mark as new target, reset
        if self.high_candle_time is not None and self.high_candle_time < cp.time:
            logger.info(
                "[%s] ❌ HIGH sweep timed out. New target = %.5f",
                self.symbol, self.current_swing_high,
            )
            self.active_high_target = self.current_swing_high
            self._reset_sweep_state("high")

        return None

    def _check_long_patterns(self, bars: List[Bar]) -> Optional[Signal]:
        """Evaluate long-setup patterns after a low sweep."""
        if not self.sweep_low_active:
            return None

        c2 = bars[-2]
        c1 = bars[-3]
        c0 = bars[-4]
        cp = bars[-5] if len(bars) >= 5 else c0

        # Pattern 1: two consecutive bullish candles, second closes above first's high
        p1 = (c1.is_bullish and c2.is_bullish and c2.close > c1.high)

        # Pattern 2: Green → Red → Green engulfing
        p2 = (c0.is_bullish and c1.is_bearish and c2.is_bullish
              and c2.close > max(c0.high, c1.high))

        if p1 and self.low_candle_time in (c0.time, c1.time):
            logger.info("[%s] 🎯 LONG p1 (2-bar reversal)", self.symbol)
            return self._build_long_signal(c2, "2bar")

        if p2 and self.low_candle_time in (cp.time, c0.time, c1.time):
            logger.info("[%s] 🎯 LONG p2 (3-bar engulf)", self.symbol)
            return self._build_long_signal(c2, "3bar_engulf")

        if self.low_candle_time is not None and self.low_candle_time < cp.time:
            logger.info(
                "[%s] ❌ LOW sweep timed out. New target = %.5f",
                self.symbol, self.current_swing_low,
            )
            self.active_low_target = self.current_swing_low
            self._reset_sweep_state("low")

        return None

    def _build_short_signal(self, trigger_bar: Bar, pattern: str) -> Signal:
        sl = self.current_swing_high + self.sl_buffer
        sig = Signal(
            symbol=self.symbol,
            action="SHORT",
            sl=sl,
            tp_target=self.active_low_target,
            pattern=pattern,
            swing_extreme=self.current_swing_high,
            entry_time=trigger_bar.time,
        )
        self.active_high_target = self.current_swing_high
        self._reset_sweep_state("high")
        return sig

    def _build_long_signal(self, trigger_bar: Bar, pattern: str) -> Signal:
        sl = self.current_swing_low - self.sl_buffer
        sig = Signal(
            symbol=self.symbol,
            action="LONG",
            sl=sl,
            tp_target=self.active_high_target,
            pattern=pattern,
            swing_extreme=self.current_swing_low,
            entry_time=trigger_bar.time,
        )
        self.active_low_target = self.current_swing_low
        self._reset_sweep_state("low")
        return sig

    def _reset_sweep_state(self, side: str) -> None:
        if side == "high":
            self.sweep_high_active = False
            self.current_swing_high = 0.0
            self.high_candle_time = None
        elif side == "low":
            self.sweep_low_active = False
            self.current_swing_low = float("inf")
            self.low_candle_time = None

    # ─────────────────────────────────────────────────────────────────────
    # Properties (exposed for feature engine & dashboard)
    # ─────────────────────────────────────────────────────────────────────

    @property
    def state_dict(self) -> dict:
        """Snapshot of current strategy state (for dashboard & feature engine)."""
        return {
            "symbol": self.symbol,
            "pdh": self.pdh,
            "pdl": self.pdl,
            "active_high_target": self.active_high_target,
            "active_low_target": self.active_low_target,
            "sweep_high_active": self.sweep_high_active,
            "sweep_low_active": self.sweep_low_active,
            "current_swing_high": self.current_swing_high,
            "current_swing_low": self.current_swing_low,
            "high_attempt_count": self.high_attempt_count,
            "low_attempt_count": self.low_attempt_count,
        }
