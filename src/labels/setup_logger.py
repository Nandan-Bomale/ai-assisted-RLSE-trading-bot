import sqlite3
import pandas as pd
from typing import List
from datetime import datetime

from src.strategy.rlse_engine import Signal
from src.backtest.broker_sim import Fill
from src.backtest.engine import TradeRecord

class SetupLogger:
    def __init__(self, db_path: str = 'data/setups.db'):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        import os
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS setups (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              logged_at TEXT,
              symbol TEXT,
              signal_time TEXT,
              side TEXT,
              pattern TEXT,
              entry_price REAL,
              sl REAL,
              initial_risk_points REAL,
              tp1 REAL, tp2 REAL, tp3 REAL,
              pdh REAL, pdl REAL,
              swing_extreme REAL,
              attempt_number INTEGER,
              exit_price REAL,
              exit_time TEXT,
              exit_reason TEXT,
              pnl_r REAL,
              mfe_r REAL,
              mae_r REAL,
              bars_in_trade INTEGER,
              outcome TEXT,
              breakout_flag INTEGER,
              hour_of_day INTEGER,
              day_of_week INTEGER,
              distance_beyond_level_atr REAL,
              candle_body_atr REAL,
              session TEXT,
              model_version TEXT DEFAULT 'none'
            )
        """)
        conn.commit()
        conn.close()

    def log_signal(self, signal: Signal, fill: Fill, pdh: float, pdl: float, attempt: int, features: dict = None) -> int:
        if features is None:
            features = {}
            
        initial_risk = abs(fill.entry_price - signal.sl)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO setups (
                logged_at, symbol, signal_time, side, pattern,
                entry_price, sl, initial_risk_points,
                tp1, tp2, tp3, pdh, pdl, swing_extreme, attempt_number,
                hour_of_day, day_of_week, distance_beyond_level_atr,
                candle_body_atr, session, model_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(), signal.symbol, str(signal.entry_time), signal.action, signal.pattern,
            fill.entry_price, signal.sl, initial_risk,
            fill.tp, None, None, pdh, pdl, signal.swing_extreme, attempt,
            features.get('hour_of_day'), features.get('day_of_week'),
            features.get('distance_beyond_level_atr'), features.get('candle_body_atr'),
            features.get('session'), features.get('model_version', 'none')
        ))
        setup_id = c.lastrowid
        conn.commit()
        conn.close()
        return setup_id

    def update_outcome(self, setup_id: int, trade: TradeRecord):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        outcome = 'WIN' if trade.pnl_r > 0 else 'LOSS'
        breakout_flag = 1 if (trade.exit_reason == 'SL_HIT' and trade.mfe_r < 0.5) else 0
        
        c.execute("""
            UPDATE setups SET
                exit_price = ?,
                exit_time = ?,
                exit_reason = ?,
                pnl_r = ?,
                mfe_r = ?,
                mae_r = ?,
                bars_in_trade = ?,
                outcome = ?,
                breakout_flag = ?
            WHERE id = ?
        """, (
            trade.exit_price, str(trade.exit_time), trade.exit_reason,
            trade.pnl_r, trade.mfe_r, trade.mae_r, trade.bars_in_trade,
            outcome, breakout_flag, setup_id
        ))
        conn.commit()
        conn.close()

    def log_backtest_trades(self, trades: List[TradeRecord], df_levels: pd.DataFrame):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for t in trades:
            dt = pd.to_datetime(t.open_time)
            hour = dt.hour
            dow = dt.dayofweek
            
            if 0 <= hour < 8:
                session = 'ASIA'
            elif 8 <= hour < 13:
                session = 'LONDON'
            elif 13 <= hour < 16:
                session = 'OVERLAP'
            else:
                session = 'NY'
                
            pdh, pdl = 0.0, 0.0
            if t.open_time in df_levels.index:
                pdh = df_levels.loc[t.open_time]['pdh']
                pdl = df_levels.loc[t.open_time]['pdl']

            outcome = 'WIN' if t.pnl_r > 0 else 'LOSS'
            breakout_flag = 1 if (t.exit_reason == 'SL_HIT' and t.mfe_r < 0.5) else 0
            
            c.execute("""
                INSERT INTO setups (
                    logged_at, symbol, signal_time, side, pattern,
                    entry_price, sl, initial_risk_points,
                    tp1, pdh, pdl, attempt_number,
                    exit_price, exit_time, exit_reason,
                    pnl_r, mfe_r, mae_r, bars_in_trade, outcome, breakout_flag,
                    hour_of_day, day_of_week, session, model_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.utcnow().isoformat(), t.symbol, str(t.open_time), t.action, t.pattern,
                t.entry_price, t.sl, t.initial_risk_points,
                t.tp, pdh, pdl, t.attempt_number,
                t.exit_price, str(t.exit_time), t.exit_reason,
                t.pnl_r, t.mfe_r, t.mae_r, t.bars_in_trade, outcome, breakout_flag,
                hour, dow, session, 'none'
            ))
        conn.commit()
        conn.close()

    def to_dataframe(self) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query("SELECT * FROM setups", conn)
        conn.close()
        return df

    def get_labeled_df(self) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query("SELECT * FROM setups WHERE exit_price IS NOT NULL", conn)
        conn.close()
        return df
