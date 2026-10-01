"""
Win-Rate Optimization Engine for XAU/USD Gold Scalper
Tests parameter variations to discover how to increase Win Rate from ~58% to 68% - 75%+:
1. RR Ratio: 1:1.0, 1:1.2, 1:1.3, 1:1.5
2. ADX Threshold: 0, 18, 22, 25
3. Target Pips / Fixed Scalp Target: 25 pips ($2.50), 30 pips ($3.00), 40 pips ($4.00)
4. Tighter Order Block & Pullback tolerances
"""

import os
import sys
from typing import Dict, List, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from trading_bot.strategy import StrategyParameters
from trading_bot.data_feed import generate_realistic_gold_data
from trading_bot.backtest import run_causal_backtest


def is_golden_session(hour_utc: int) -> bool:
    return (7 <= hour_utc < 12) or (16 <= hour_utc < 21)


def test_configurations():
    days = 30
    bars_count = days * 1440
    print("=" * 90)
    print("  🔬 WIN-RATE OPTIMIZATION STUDY (30 DAYS / 43,200 BARS ON GOLD M1)")
    print("=" * 90)

    data = generate_realistic_gold_data(num_bars=bars_count, seed=101, volatility=0.68)

    configs = [
        {"name": "Current Baseline (1:1.50 RR, ADX=0)", "rr": 1.50, "min_adx": 0.0, "be_ratio": 0.70, "pullback_mult": 1.0},
        {"name": "Config 1: Quick Scalp (1:1.00 RR, ADX=0)", "rr": 1.00, "min_adx": 0.0, "be_ratio": 0.65, "pullback_mult": 1.0},
        {"name": "Config 2: Balanced Scalp (1:1.20 RR, ADX=0)", "rr": 1.20, "min_adx": 0.0, "be_ratio": 0.65, "pullback_mult": 1.0},
        {"name": "Config 3: High Confluence (1:1.20 RR, ADX>=20)", "rr": 1.20, "min_adx": 20.0, "be_ratio": 0.65, "pullback_mult": 0.85},
        {"name": "Config 4: High Confluence (1:1.00 RR, ADX>=22)", "rr": 1.00, "min_adx": 22.0, "be_ratio": 0.60, "pullback_mult": 0.80},
        {"name": "Config 5: Strict Trend (1:1.25 RR, ADX>=20)", "rr": 1.25, "min_adx": 20.0, "be_ratio": 0.70, "pullback_mult": 0.90},
    ]

    print(f" {'Configuration':<45} | {'Trades':<7} | {'Win Rate':<9} | {'Net ($) 0.02':<12} | {'PF':<6}")
    print("-" * 90)

    for cfg in configs:
        params = StrategyParameters(
            ema_fast_period=9,
            ema_slow_period=21,
            vwap_anchor_hour_utc=0,
            enable_vwap_slope=True,
            vwap_slope_lookback=4,
            min_adx=cfg["min_adx"],
            adx_period=14,
            ob_swing_lookback=3,
            ob_max_age_bars=60,
            max_pullback_bars=20,
            pullback_atr_mult=cfg["pullback_mult"],
            anti_exhaustion_atr_mult=2.2,
            atr_period=14,
            rr_ratio=cfg["rr"],
            min_sl_distance_points=1.8,
            max_sl_distance_points=3.5,
            avoid_toxic_hours=False,
            enable_session_filter=False,
            enable_be=True,
            be_trigger_ratio=cfg["be_ratio"]
        )

        res = run_causal_backtest(
            opens=data["opens"],
            highs=data["highs"],
            lows=data["lows"],
            closes=data["closes"],
            times=data["times"],
            volumes=data["volumes"],
            params=params,
            initial_balance=500.0,
            split_ratio=0.75,
            spread_points=0.25,
            commission_per_lot_usd=7.0,
            fixed_lot_size=0.02,
            num_noise_shuffles=1
        )

        # Filter to Golden Sessions
        golden_trades = []
        for t in res.trades:
            hour = 0
            if "T" in t.entry_time:
                hour = int(t.entry_time.split("T")[1].split(":")[0])
            else:
                try:
                    hour = int(t.entry_time.split(" ")[1].split(":")[0])
                except Exception:
                    hour = 0
            if is_golden_session(hour):
                golden_trades.append(t)

        tot_trades = len(golden_trades)
        wins = sum(1 for t in golden_trades if t.net_pnl_usd > 0)
        wr = (wins / tot_trades * 100) if tot_trades > 0 else 0
        net_pnl = sum(t.net_pnl_usd for t in golden_trades)
        gross_w = sum(t.net_pnl_usd for t in golden_trades if t.net_pnl_usd > 0)
        gross_l = abs(sum(t.net_pnl_usd for t in golden_trades if t.net_pnl_usd < 0))
        pf = (gross_w / gross_l) if gross_l > 0 else 99.0

        print(f" {cfg['name']:<45} | {tot_trades:<7} | {wr:5.1f}%   | ${net_pnl:+8.2f}    | {pf:4.2f}")

    print("=" * 90)


if __name__ == "__main__":
    test_configurations()
