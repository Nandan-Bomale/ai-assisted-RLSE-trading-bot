"""
run_phase1.py
═══════════════
Phase 1 runner — Data pipeline + Backtester + Expectancy Report

Usage:
    python run_phase1.py --mode mt5         # Load from connected MT5 terminal
    python run_phase1.py --mode binance     # Load BTC from Binance public data
    python run_phase1.py --mode backtest    # Run backtester on existing parquet data
    python run_phase1.py --mode full        # All of the above in sequence
    python run_phase1.py --mode report      # Re-generate report from existing setups.db

Requirements:
    - For --mode mt5: MT5 terminal must be running and connected
    - For --mode binance: internet connection
    - For --mode backtest: parquet data must already be fetched

Output:
    - data/XAUUSD_1m_*.parquet      (Gold 1m bars)
    - data/BTCUSDT_1m_*.parquet     (BTC 1m bars)
    - data/setups.db                (SQLite setup log with outcomes)
    - reports/quality_XAUUSD.json   (data quality report)
    - reports/quality_BTCUSD.json
    - reports/phase1_expectancy.md  (THE key gate B report)
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("phase1")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# ─── Default config ───────────────────────────────────────────────────────────

GOLD_SYMBOL_MT5 = "GOLD.i#"     # As named in broker
GOLD_SYMBOL     = "XAUUSD"      # Canonical name for data files
BTC_SYMBOL_MT5  = "BTCUSD#"
BTC_SYMBOL      = "BTCUSD"

BACKTEST_CONFIG = {
    GOLD_SYMBOL: {
        "sl_buffer":    1.5,
        "lot_size":     0.01,
        "tp_rr_list":   [1.0, 2.0, 3.0],
        "spread_points": 0.30,
        "slippage_points": 0.10,
        "point_value":  1.0,
    },
    BTC_SYMBOL: {
        "sl_buffer":    100.0,
        "lot_size":     0.01,
        "tp_rr_list":   [1.0, 2.0, 3.0],
        "spread_points": 30.0,
        "slippage_points": 10.0,
        "point_value":  1.0,
    },
}

# Years to pull from Binance (BTC data)
BINANCE_START = (2021, 1)
BINANCE_END   = (2024, 12)


# ─── Stage 1: MT5 Data Load ───────────────────────────────────────────────────

def stage_mt5(args):
    logger.info("=== STAGE 1: MT5 Data Load ===")
    try:
        import MetaTrader5 as mt5
        from src.data.mt5_loader import fetch_and_save, get_available_history_range
    except ImportError as e:
        logger.error("Cannot import MT5 or data loaders: %s", e)
        return

    if not mt5.initialize():
        logger.warning("MT5 not connected. Skipping MT5 data load.")
        return

    for mt5_sym, canonical in [(GOLD_SYMBOL_MT5, GOLD_SYMBOL), (BTC_SYMBOL_MT5, BTC_SYMBOL)]:
        logger.info("Fetching history range for %s ...", mt5_sym)
        earliest, latest, count = get_available_history_range(mt5_sym)
        if earliest is None:
            logger.warning("No history available for %s — skipping", mt5_sym)
            continue

        logger.info(
            "%s: %d bars available from %s to %s",
            mt5_sym, count,
            earliest.strftime("%Y-%m-%d"),
            latest.strftime("%Y-%m-%d"),
        )

        df, path = fetch_and_save(
            symbol=mt5_sym,
            start_dt=earliest,
            end_dt=latest,
            output_dir=str(DATA_DIR),
        )
        logger.info("Saved %d bars → %s", len(df), path)

        # Run quality check
        try:
            from src.data.quality import run_quality_check, save_quality_report
            report = run_quality_check(path, canonical)
            save_quality_report(report, str(REPORTS_DIR))
        except Exception as e:
            logger.warning("Quality check failed for %s: %s", canonical, e)

    mt5.shutdown()
    logger.info("=== MT5 Stage Done ===\n")


# ─── Stage 2: Binance BTC Download ────────────────────────────────────────────

def stage_binance(args):
    logger.info("=== STAGE 2: Binance BTC Download ===")
    try:
        from src.data.binance_loader import fetch_binance_range
        from src.data.quality import run_quality_check, save_quality_report
    except ImportError as e:
        logger.error("Cannot import data loaders: %s", e)
        return

    sy, sm = BINANCE_START
    ey, em = BINANCE_END
    logger.info("Downloading BTCUSDT 1m: %d-%02d to %d-%02d", sy, sm, ey, em)

    df = fetch_binance_range(sy, sm, ey, em, output_dir=str(DATA_DIR))
    logger.info("Total BTC bars downloaded: %d", len(df))

    # Save quality report
    parquet_files = sorted(DATA_DIR.glob("BTCUSDT_1m_*.parquet"))
    if parquet_files:
        report = run_quality_check(str(parquet_files[-1]), BTC_SYMBOL)
        save_quality_report(report, str(REPORTS_DIR))

    logger.info("=== Binance Stage Done ===\n")


# ─── Stage 3: Backtest ────────────────────────────────────────────────────────

def stage_backtest(args):
    logger.info("=== STAGE 3: Backtest ===")
    try:
        from src.backtest.broker_sim import BrokerConfig, BrokerSimulator
        from src.backtest.engine import BacktestEngine
        from src.data.daily_levels import build_levels_series
        from src.data.mt5_loader import load_from_parquet
        from src.labels.setup_logger import SetupLogger
        from src.labels.labeler import label_trades, compute_r_distribution, compute_drawdown
    except ImportError as e:
        logger.error("Import error: %s — have you installed requirements?", e)
        return

    all_trades = []
    setup_logger = SetupLogger(db_path=str(DATA_DIR / "setups.db"))

    for canonical, cfg in BACKTEST_CONFIG.items():
        # Find parquet file
        parquet_files = sorted(DATA_DIR.glob(f"{canonical}_1m_*.parquet"))
        if not parquet_files:
            # Also check BTCUSDT variant
            parquet_files = sorted(DATA_DIR.glob(f"BTCUSDT_1m_*.parquet"))
        if not parquet_files:
            logger.warning("No parquet data found for %s — skipping backtest", canonical)
            continue

        parquet_path = str(parquet_files[-1])
        logger.info("Loading %s from %s ...", canonical, parquet_path)
        df_1m = load_from_parquet(parquet_path)
        logger.info("  Loaded %d bars (%s to %s)", len(df_1m),
                    df_1m.index[0].strftime("%Y-%m-%d"),
                    df_1m.index[-1].strftime("%Y-%m-%d"))

        # Build daily levels (PDH/PDL per bar, no look-ahead)
        logger.info("  Computing daily levels (NY close rule) ...")
        df_levels = build_levels_series(df_1m)
        logger.info("  Levels computed. Bars with valid PDH/PDL: %d",
                    df_levels["pdh"].notna().sum())

        # Run backtester
        broker_cfg = BrokerConfig(
            symbol=canonical,
            spread_points=cfg["spread_points"],
            slippage_points=cfg["slippage_points"],
            point_value=cfg["point_value"],
            min_lot=0.01,
            max_lot=10.0,
            lot_step=0.01,
        )
        engine = BacktestEngine(
            broker_config=broker_cfg,
            sl_buffer=cfg["sl_buffer"],
            lot_size=cfg["lot_size"],
            tp_rr_list=cfg["tp_rr_list"],
        )

        logger.info("  Running backtest for %s ...", canonical)
        trades = engine.run(df_1m, df_levels, symbol=canonical)
        logger.info("  %s: %d positions from %d signals", canonical,
                    len(trades), len(trades) // max(1, len(cfg["tp_rr_list"])))

        # Log to SQLite
        setup_logger.log_backtest_trades(trades, df_levels)
        all_trades.extend(trades)

    logger.info("Total positions across all instruments: %d", len(all_trades))
    logger.info("=== Backtest Stage Done ===\n")
    return all_trades


# ─── Stage 4: Expectancy Report ───────────────────────────────────────────────

def stage_report(args):
    logger.info("=== STAGE 4: Expectancy Report (Phase 1 Gate B) ===")
    try:
        from src.labels.setup_logger import SetupLogger
        from src.labels.labeler import label_trades, compute_r_distribution, compute_drawdown
    except ImportError as e:
        logger.error("Import error: %s", e)
        return

    db_path = str(DATA_DIR / "setups.db")
    if not os.path.exists(db_path):
        logger.error("setups.db not found. Run --mode backtest first.")
        return

    setup_logger = SetupLogger(db_path=db_path)
    df_all = setup_logger.get_labeled_df()

    if df_all.empty:
        logger.error("No completed trades in setups.db. Run backtest first.")
        return

    report_lines = [
        "# Phase 1 Gate B — Base RLSE Expectancy Report",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
    ]

    instruments = df_all["symbol"].unique() if "symbol" in df_all.columns else ["ALL"]
    all_good = True

    for sym in instruments:
        df_sym = df_all[df_all["symbol"] == sym] if "symbol" in df_all.columns else df_all
        # Dedupe to one-row-per-signal by taking TP1 only (lowest RR)
        if "tp_label" in df_sym.columns:
            df_sym = df_sym[df_sym["tp_label"] == "TP1"]

        from src.labels.labeler import label_trades, compute_r_distribution, compute_drawdown
        import pandas as pd
        # label_trades expects list[TradeRecord] but we have a df; use it directly
        labeled = df_sym.copy()
        if "outcome" not in labeled.columns:
            labeled["outcome"] = labeled["pnl_r"].apply(lambda x: "WIN" if x > 0 else "LOSS")

        dist = compute_r_distribution(labeled)
        dd   = compute_drawdown(labeled)

        n_signals = len(labeled)
        exp = dist.get("expectancy_r", 0.0)
        decision = "✅ GO — Positive expectancy detected." if exp > 0 else "🚫 STOP — No positive expectancy. Do NOT build models yet."
        if exp <= 0:
            all_good = False

        report_lines += [
            f"## {sym}",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Signals | {n_signals} |",
            f"| Win Rate | {dist.get('win_rate', 0)*100:.1f}% |",
            f"| Avg Winner (R) | {dist.get('avg_winner_r', 0):.2f}R |",
            f"| Avg Loser (R) | {dist.get('avg_loser_r', 0):.2f}R |",
            f"| **Expectancy (R/trade)** | **{exp:.3f}R** |",
            f"| Profit Factor | {dist.get('profit_factor', 0):.2f} |",
            f"| Max Drawdown | {dd.get('max_dd_r', 0):.2f}R ({dd.get('max_dd_trades', 0)} trades) |",
            f"| Max Consec. Losses | {dist.get('max_consecutive_losses', 0)} |",
            f"| MFE p50/p75/p90/p95 | {dist.get('mfe_p50',0):.1f}R / {dist.get('mfe_p75',0):.1f}R / {dist.get('mfe_p90',0):.1f}R / {dist.get('mfe_p95',0):.1f}R |",
            f"| PnL p10/p25/p50/p75/p90 | {dist.get('pnl_p10',0):.1f} / {dist.get('pnl_p25',0):.1f} / {dist.get('pnl_p50',0):.1f} / {dist.get('pnl_p75',0):.1f} / {dist.get('pnl_p90',0):.1f} |",
            f"| Large Winners (≥5R MFE) | {dist.get('large_winners_5r', 0)} ({dist.get('large_winners_5r',0)/max(1,n_signals)*100:.1f}%) |",
            f"| Large Winners (≥10R MFE) | {dist.get('large_winners_10r', 0)} ({dist.get('large_winners_10r',0)/max(1,n_signals)*100:.1f}%) |",
            "",
            f"### Decision: {decision}",
            "",
            "---",
            "",
        ]

    report_lines += [
        "## Overall Verdict",
        "",
        "✅ All instruments show positive expectancy. Proceed to Phase 2 (Risk Guard + rule-based baselines)."
        if all_good else
        "🚫 One or more instruments show no positive expectancy. STOP and review before building ML models.",
        "",
    ]

    report_text = "\n".join(report_lines)
    report_path = REPORTS_DIR / "phase1_expectancy.md"
    report_path.write_text(report_text, encoding="utf-8")
    logger.info("Report saved → %s", report_path)
    print("\n" + report_text)
    return report_text


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phase 1 Runner — RLSE AI Bot")
    parser.add_argument(
        "--mode",
        choices=["mt5", "binance", "backtest", "report", "full"],
        default="full",
        help="Which stage to run (default: full = all stages)",
    )
    args = parser.parse_args()

    mode = args.mode
    if mode in ("mt5", "full"):
        stage_mt5(args)
    if mode in ("binance", "full"):
        stage_binance(args)
    if mode in ("backtest", "full"):
        stage_backtest(args)
    if mode in ("report", "full"):
        stage_report(args)

    logger.info("Phase 1 runner complete.")


if __name__ == "__main__":
    main()
