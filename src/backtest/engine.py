from dataclasses import dataclass
from typing import List, Any, Tuple
import pandas as pd

from src.strategy.rlse_engine import RLSEEngine, Signal, Bar
from src.backtest.broker_sim import BrokerConfig, Fill, BrokerSimulator

@dataclass
class TradeRecord:
    symbol: str
    action: str
    lots: float
    entry_price: float
    sl: float
    tp: float
    ticket: int
    open_time: Any
    pattern: str
    commission: float
    exit_price: float
    exit_time: Any
    exit_reason: str
    pnl_points: float
    pnl_r: float
    initial_risk_points: float
    mfe_r: float
    mae_r: float
    bars_in_trade: int
    attempt_number: int

class BacktestEngine:
    def __init__(self, broker_config: BrokerConfig, sl_buffer: float, lot_size: float, tp_rr_list: List[float]):
        self.broker_config = broker_config
        self.sl_buffer = sl_buffer
        self.lot_size = lot_size
        self.tp_rr_list = tp_rr_list

    def run(self, df_1m: pd.DataFrame, df_levels: pd.DataFrame, symbol: str) -> List[TradeRecord]:
        broker = BrokerSimulator(self.broker_config)
        trades: List[TradeRecord] = []
        open_fills: List[tuple[Fill, int, float, float]] = [] # fill, attempt_number, mfe_r, mae_r
        
        engine = None
        current_pdh = None
        current_pdl = None
        
        bars_list: List[Bar] = []
        
        for i in range(len(df_1m)):
            row = df_1m.iloc[i]
            time_val = df_1m.index[i] if isinstance(df_1m.index, pd.DatetimeIndex) else row.get('time', i)
            
            if time_val in df_levels.index:
                levels_row = df_levels.loc[time_val]
                new_pdh = levels_row['pdh']
                new_pdl = levels_row['pdl']
            else:
                new_pdh = current_pdh
                new_pdl = current_pdl
                
            if new_pdh != current_pdh or new_pdl != current_pdl:
                current_pdh = new_pdh
                current_pdl = new_pdl
                
                # End of day check - close open positions
                closed_fills_idx = []
                for idx, (fill, attempt, mfe_r, mae_r) in enumerate(open_fills):
                    exit_price = broker.get_exit_price(fill, 'END_OF_DATA', bars_list[-1] if bars_list else None)
                    if fill.action == "LONG":
                        pnl_points = exit_price - fill.entry_price
                    else:
                        pnl_points = fill.entry_price - exit_price
                    
                    initial_risk = abs(fill.entry_price - fill.sl) or 1e-5
                    pnl_r = pnl_points / initial_risk
                    open_bar_time = fill.open_time
                    open_bar_idx = next((j for j, b in enumerate(bars_list) if b.time == open_bar_time), len(bars_list))
                    bars_in_trade = len(bars_list) - open_bar_idx
                    
                    trades.append(TradeRecord(
                        symbol=fill.symbol, action=fill.action, lots=fill.lots, entry_price=fill.entry_price,
                        sl=fill.sl, tp=fill.tp, ticket=fill.ticket, open_time=fill.open_time,
                        pattern=fill.pattern, commission=fill.commission, exit_price=exit_price,
                        exit_time=time_val, exit_reason='END_OF_DATA', pnl_points=pnl_points,
                        pnl_r=pnl_r, initial_risk_points=initial_risk, mfe_r=mfe_r, mae_r=mae_r,
                        bars_in_trade=bars_in_trade, attempt_number=attempt
                    ))
                    closed_fills_idx.append(idx)
                    
                for idx in reversed(closed_fills_idx):
                    open_fills.pop(idx)

                if engine is None:
                    if current_pdh is not None and current_pdl is not None:
                        engine = RLSEEngine(symbol, current_pdh, current_pdl, current_pdh, current_pdl, self.sl_buffer)
                else:
                    engine.reset_daily(current_pdh, current_pdl, current_pdh, current_pdl)
            
            if engine is None:
                continue

            bar = Bar(
                time=time_val,
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close']
            )
            bars_list.append(bar)
            
            start_idx = max(0, len(bars_list) - 5)
            window_bars = bars_list[start_idx:]
            
            closed_fills_idx = []
            for idx, (fill, attempt, mfe_r, mae_r) in enumerate(open_fills):
                initial_risk = abs(fill.entry_price - fill.sl) or 1e-5
                    
                if fill.action == "LONG":
                    fav_excursion = (bar.high - fill.entry_price) / initial_risk
                    adv_excursion = (fill.entry_price - bar.low) / initial_risk
                else:
                    fav_excursion = (fill.entry_price - bar.low) / initial_risk
                    adv_excursion = (bar.high - fill.entry_price) / initial_risk
                    
                mfe_r = max(mfe_r, fav_excursion)
                mae_r = max(mae_r, adv_excursion)
                open_fills[idx] = (fill, attempt, mfe_r, mae_r)
                
                exit_reason = broker.check_fill(fill, bar)
                if exit_reason:
                    exit_price = broker.get_exit_price(fill, exit_reason, bar)
                    
                    if fill.action == "LONG":
                        pnl_points = exit_price - fill.entry_price
                    else:
                        pnl_points = fill.entry_price - exit_price
                        
                    pnl_r = pnl_points / initial_risk
                    
                    open_bar_idx = next((j for j, b in enumerate(bars_list) if b.time == fill.open_time), len(bars_list))
                    bars_in_trade = len(bars_list) - 1 - open_bar_idx
                    
                    trade = TradeRecord(
                        symbol=fill.symbol,
                        action=fill.action,
                        lots=fill.lots,
                        entry_price=fill.entry_price,
                        sl=fill.sl,
                        tp=fill.tp,
                        ticket=fill.ticket,
                        open_time=fill.open_time,
                        pattern=fill.pattern,
                        commission=fill.commission,
                        exit_price=exit_price,
                        exit_time=bar.time,
                        exit_reason=exit_reason,
                        pnl_points=pnl_points,
                        pnl_r=pnl_r,
                        initial_risk_points=initial_risk,
                        mfe_r=mfe_r,
                        mae_r=mae_r,
                        bars_in_trade=bars_in_trade,
                        attempt_number=attempt
                    )
                    trades.append(trade)
                    closed_fills_idx.append(idx)
                    
            for idx in reversed(closed_fills_idx):
                open_fills.pop(idx)

            signal = engine.update(bar.close, window_bars)
            if signal:
                attempt = engine.high_attempt_count if signal.action == "SHORT" else engine.low_attempt_count
                for rr in self.tp_rr_list:
                    initial_risk = abs(bar.close - signal.sl)
                    if signal.action == "LONG":
                        tp = bar.close + (initial_risk * rr)
                    else:
                        tp = bar.close - (initial_risk * rr)
                    
                    signal_copy = Signal(
                        symbol=signal.symbol,
                        action=signal.action,
                        sl=signal.sl,
                        tp_target=tp,
                        pattern=signal.pattern,
                        swing_extreme=signal.swing_extreme,
                        entry_time=signal.entry_time
                    )
                    
                    fill = broker.execute(signal_copy, bar, self.lot_size)
                    open_fills.append((fill, attempt, 0.0, 0.0))
                    
        return trades

    def get_summary(self, trades: List[TradeRecord]) -> dict:
        return {}
