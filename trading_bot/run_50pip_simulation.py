"""
Simulation of 50 Pips Daily Lock with 0.02 Lot Size on XAU/USD (Gold M1)
Compares:
1. Target: 50 Pips (+10.00 USD on 0.02 lot)
2. As soon as daily net pnl reaches +$10.00 (50 pips), BOT LOCKS PROFITS & SLEEPS FOR THE DAY
3. Max Daily Loss Guard: -$10.00 (stops day if 2 losses occur)
"""

import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from trading_bot.strategy import StrategyParameters
from trading_bot.data_feed import generate_realistic_gold_data
from trading_bot.backtest import run_causal_backtest


def is_golden_session(hour_utc: int) -> bool:
    return (7 <= hour_utc < 12) or (16 <= hour_utc < 21)


def run_50pip_002lot_simulation():
    days = 30
    bars_count = days * 1440
    print("=" * 88)
    print(f"  🧪 SIMULATION: 50 PIPS DAILY LOCK @ 0.02 LOT SIZE (XAU/USD GOLD M1)")
    print(f"  🎯 Target: 50 Pips = $10.00 USD Net Profit per Day on 0.02 Lot")
    print(f"  🛡️ Strategy: Hit 50 Pips -> Auto Lock Profits & Stop for the Day")
    print("=" * 88)

    data = generate_realistic_gold_data(num_bars=bars_count, seed=101, volatility=0.68)

    params = StrategyParameters(
        ema_fast_period=9,
        ema_slow_period=21,
        vwap_anchor_hour_utc=0,
        enable_vwap_slope=True,
        vwap_slope_lookback=4,
        min_adx=0.0,
        adx_period=14,
        ob_swing_lookback=3,
        ob_max_age_bars=60,
        max_pullback_bars=20,
        pullback_atr_mult=1.0,
        anti_exhaustion_atr_mult=2.2,
        atr_period=14,
        rr_ratio=1.5,
        min_sl_distance_points=1.8,
        max_sl_distance_points=3.8,
        avoid_toxic_hours=False,
        enable_session_filter=False,
        enable_be=True,
        be_trigger_ratio=0.70
    )

    # Run causal backtest with 0.02 lot
    lot_size = 0.02
    result = run_causal_backtest(
        opens=data["opens"],
        highs=data["highs"],
        lows=data["lows"],
        closes=data["closes"],
        times=data["times"],
        volumes=data["volumes"],
        params=params,
        initial_balance=500.0, # Typical micro balance
        split_ratio=0.75,
        spread_points=0.25,
        commission_per_lot_usd=7.0,
        fixed_lot_size=lot_size,
        num_noise_shuffles=10
    )

    # Filter to Golden Sessions
    golden_trades = []
    for t in result.trades:
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

    # Daily Profit Lock Engine: Stop as soon as >= $10.00 net (50 pips) is achieved or daily loss hit
    daily_results: Dict[str, Dict[str, Any]] = {}

    for t in golden_trades:
        day_key = t.entry_time.split("T")[0] if "T" in t.entry_time else t.entry_time[:10]
        if day_key not in daily_results:
            daily_results[day_key] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl": 0.0,
                "pips": 0.0,
                "locked": False,
                "stopped_loss": False
            }

        st = daily_results[day_key]
        if st["locked"] or st["stopped_loss"]:
            continue  # Day is already finished!

        pts = (t.exit_price - t.entry_price) if t.direction == "BUY" else (t.entry_price - t.exit_price)
        pips = pts * 10.0

        st["trades"] += 1
        st["pnl"] += t.net_pnl_usd
        st["pips"] += pips
        if t.net_pnl_usd > 0:
            st["wins"] += 1
        else:
            st["losses"] += 1

        # Target Check: 50 Pips / +$10.00 Net
        if st["pnl"] >= 10.0 or st["pips"] >= 50.0:
            st["locked"] = True
        # Daily Max Loss Guard: -$10.00
        elif st["pnl"] <= -10.0:
            st["stopped_loss"] = True

    # Reporting
    print(f" {'Day':<8} | {'Date':<10} | {'Trades':<7} | {'Win %':<7} | {'Pips':<12} | {'Net PnL ($)':<12} | {'Day Status'}")
    print("-" * 88)

    days_target_hit = 0
    profitable_days = 0
    loss_days = 0
    total_net = 0.0
    total_pips = 0.0
    total_trades_taken = 0

    d_num = 1
    for day, st in sorted(daily_results.items()):
        total_trades_taken += st["trades"]
        total_net += st["pnl"]
        total_pips += st["pips"]
        wr = (st["wins"] / st["trades"] * 100) if st["trades"] > 0 else 0

        status = ""
        if st["pnl"] >= 10.0 or st["pips"] >= 50.0:
            status = "🎯 50 PIPS HIT (+$10.00 LOCKED!)"
            days_target_hit += 1
            profitable_days += 1
        elif st["pnl"] > 0:
            status = "🟢 Profitable Day"
            profitable_days += 1
        else:
            status = "🔴 Loss Day"
            loss_days += 1

        print(f" Day {d_num:02d}  | {day} | {st['trades']:<7} | {wr:5.1f}% | {st['pips']:+8.1f} pips | ${st['pnl']:+8.2f} USD  | {status}")
        d_num += 1

    print("-" * 88)
    print("\n" + "=" * 88)
    print("  🏆 1-MONTH RESULTS WITH 50-PIP LOCK @ 0.02 LOT:")
    print("=" * 88)
    print(f"  • Total Realized Profit:        ${total_net:+,.2f} USD (across 30 days)")
    print(f"  • Total Pips Captured:          {total_pips:+,.1f} Pips")
    print(f"  • Days Hitting $10 / 50 Pips:   {days_target_hit} out of {len(daily_results)} Days ({days_target_hit/len(daily_results)*100:.1f}%)")
    print(f"  • Total Profitable Days:        {profitable_days} out of {len(daily_results)} Days ({profitable_days/len(daily_results)*100:.1f}%)")
    print(f"  • Average Trades per Day:       {total_trades_taken/len(daily_results):.1f} trades/day (Fast & Stress-Free!)")
    print(f"  • Average Daily Profit:         ${total_net/len(daily_results):+.2f} USD/Day")
    print("=" * 88)


if __name__ == "__main__":
    run_50pip_002lot_simulation()
