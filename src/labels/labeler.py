import pandas as pd
from typing import List, Dict
from src.backtest.engine import TradeRecord

def label_trades(trades: List[TradeRecord]) -> pd.DataFrame:
    data = []
    for t in trades:
        d = t.__dict__.copy()
        d['outcome'] = 'WIN' if t.pnl_r > 0 else 'LOSS'
        d['hit_1r'] = bool(t.pnl_r >= 1.0 or t.mfe_r >= 1.0)
        d['hit_2r'] = bool(t.pnl_r >= 2.0 or t.mfe_r >= 2.0)
        d['hit_3r'] = bool(t.pnl_r >= 3.0 or t.mfe_r >= 3.0)
        d['breakout_flag'] = bool(t.exit_reason == 'SL_HIT' and t.mfe_r < 0.5)
        d['regime_label'] = 'sweep' if t.mfe_r >= 1.0 else 'breakout'
        d['large_winner'] = bool(t.mfe_r >= 5.0)
        data.append(d)
    return pd.DataFrame(data)

def compute_r_distribution(df_labeled: pd.DataFrame) -> Dict:
    if df_labeled.empty:
        return {}
        
    win_rate = (df_labeled['outcome'] == 'WIN').mean()
    avg_winner_r = df_labeled[df_labeled['outcome'] == 'WIN']['pnl_r'].mean()
    avg_loser_r = df_labeled[df_labeled['outcome'] == 'LOSS']['pnl_r'].mean()
    expectancy_r = df_labeled['pnl_r'].mean()
    
    sum_losses = df_labeled[df_labeled['pnl_r'] < 0]['pnl_r'].sum()
    sum_wins = df_labeled[df_labeled['pnl_r'] > 0]['pnl_r'].sum()
    profit_factor = abs(sum_wins / sum_losses) if sum_losses != 0 else float('inf')
    
    pnl_p10 = df_labeled['pnl_r'].quantile(0.10)
    pnl_p25 = df_labeled['pnl_r'].quantile(0.25)
    pnl_p50 = df_labeled['pnl_r'].quantile(0.50)
    pnl_p75 = df_labeled['pnl_r'].quantile(0.75)
    pnl_p90 = df_labeled['pnl_r'].quantile(0.90)
    
    mfe_p50 = df_labeled['mfe_r'].quantile(0.50)
    mfe_p75 = df_labeled['mfe_r'].quantile(0.75)
    mfe_p90 = df_labeled['mfe_r'].quantile(0.90)
    mfe_p95 = df_labeled['mfe_r'].quantile(0.95)
    
    df_labeled['loss'] = df_labeled['outcome'] == 'LOSS'
    df_labeled['win'] = df_labeled['outcome'] == 'WIN'
    max_consecutive_losses = (df_labeled['loss'].groupby((~df_labeled['loss']).cumsum()).cumsum()).max()
    max_consecutive_wins = (df_labeled['win'].groupby((~df_labeled['win']).cumsum()).cumsum()).max()
    
    large_winners_5r = int((df_labeled['mfe_r'] >= 5.0).sum())
    large_winners_10r = int((df_labeled['mfe_r'] >= 10.0).sum())
    
    return {
        'win_rate': float(win_rate),
        'avg_winner_r': float(avg_winner_r),
        'avg_loser_r': float(avg_loser_r),
        'expectancy_r': float(expectancy_r),
        'profit_factor': float(profit_factor),
        'pnl_percentiles': {'p10': pnl_p10, 'p25': pnl_p25, 'p50': pnl_p50, 'p75': pnl_p75, 'p90': pnl_p90},
        'mfe_percentiles': {'p50': mfe_p50, 'p75': mfe_p75, 'p90': mfe_p90, 'p95': mfe_p95},
        'max_consecutive_losses': int(max_consecutive_losses),
        'max_consecutive_wins': int(max_consecutive_wins),
        'large_winners_5r': large_winners_5r,
        'large_winners_10r': large_winners_10r
    }

def compute_drawdown(df_labeled: pd.DataFrame) -> Dict:
    if df_labeled.empty:
        return {'max_dd_r': 0.0, 'max_dd_trades': 0, 'equity_curve': []}
        
    equity = df_labeled['pnl_r'].cumsum()
    peak = equity.cummax()
    drawdown = peak - equity
    max_dd_r = float(drawdown.max())
    
    dd_mask = drawdown > 0
    max_dd_trades = int((dd_mask.groupby((~dd_mask).cumsum()).cumsum()).max())
    
    return {
        'max_dd_r': max_dd_r,
        'max_dd_trades': max_dd_trades,
        'equity_curve': equity.tolist()
    }
