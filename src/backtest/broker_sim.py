from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.strategy.rlse_engine import Signal, Bar


@dataclass
class BrokerConfig:
    symbol: str
    spread_points: float
    slippage_points: float
    commission_per_lot: float = 0.0
    point_value: float = 1.0
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01


@dataclass
class Fill:
    symbol: str
    action: str
    lots: float
    entry_price: float
    sl: float
    tp: float
    ticket: int
    open_time: datetime
    pattern: str
    commission: float


class BrokerSimulator:
    def __init__(self, config: BrokerConfig):
        self.config = config
        self._ticket_counter = 0

    def execute(self, signal: Signal, bar: Bar, lots: float) -> Fill:
        self._ticket_counter += 1
        
        # Round lots to nearest lot_step
        steps = round(lots / self.config.lot_step)
        rounded_lots = steps * self.config.lot_step
        rounded_lots = max(self.config.min_lot, min(rounded_lots, self.config.max_lot))
        
        if signal.action == "LONG":
            entry_price = bar.close + self.config.spread_points + self.config.slippage_points
        else: # SHORT
            entry_price = bar.close - self.config.slippage_points
            
        commission = rounded_lots * self.config.commission_per_lot
        
        return Fill(
            symbol=self.config.symbol,
            action=signal.action,
            lots=rounded_lots,
            entry_price=entry_price,
            sl=signal.sl,
            tp=signal.tp_target,
            ticket=self._ticket_counter,
            open_time=bar.time,
            pattern=signal.pattern,
            commission=commission
        )

    def check_fill(self, fill: Fill, bar: Bar) -> Optional[str]:
        if fill.action == "LONG":
            if bar.low <= fill.sl:
                return "SL_HIT"
            if bar.high >= fill.tp:
                return "TP_HIT"
        else: # SHORT
            if bar.high >= fill.sl:
                return "SL_HIT"
            if bar.low <= fill.tp:
                return "TP_HIT"
        return None

    def get_exit_price(self, fill: Fill, exit_reason: str, bar: Bar) -> float:
        if exit_reason == "SL_HIT":
            return fill.sl
        if exit_reason == "TP_HIT":
            return fill.tp
        # Default end-of-data or end-of-day close
        return bar.close
