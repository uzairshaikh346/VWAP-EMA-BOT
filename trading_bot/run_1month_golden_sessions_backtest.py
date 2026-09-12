"""
1-Month (30 Days / 43,200 Bars) Golden Sessions Backtest on XAU/USD (Gold M1)
Strictly trading the 2 high-performing sessions:
1. London Session:       07:00 - 12:00 UTC (PKT 12:00 PM - 05:00 PM)
2. New York Afternoon:   16:00 - 21:00 UTC (PKT 09:00 PM - 02:00 AM)

Compares:
A) Uncapped Trading across the 2 Golden Sessions
B) With Daily 100-Pip Profit Lock (Locks profits and rests once 100 pips / $10 on 0.01 lot is reached)
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
    # London Window: 07:00 to 11:59 UTC
    # NY Afternoon Window: 16:00 to 20:59 UTC
    return (7 <= hour_utc < 12) or (16 <= hour_utc < 21)


def run_1month_golden_backtest():
    days = 30
    bars_count = days * 1440  # 43,200 bars
    print("=" * 88)
    print(f"  🏆 RUNNING 1-MONTH (30 DAYS) GOLDEN SESSIONS BACKTEST ON XAU/USD (GOLD M1)")
    print(f"  📊 Total Candles Analyzed: {bars_count:,} 1-Minute Bars")
    print("=" * 88)
    print("  ⭐ Active Golden Sessions:")
    print("     1. London Flow:     07:00 - 12:00 UTC  (Pakistan: 12:00 PM - 05:00 PM)")
    print("     2. NY Afternoon:    16:00 - 21:00 UTC  (Pakistan: 09:00 PM - 02:00 AM)")
    print("     ❌ US Open Trap (12:00-16:00 UTC) & Asian Slump (00:00-07:00 UTC) 100% FILTERED OUT!")
    print("     • Target Goal: 100 Pips / Day (+10.00 USD on 0.01 lot / +100.00 USD on 0.10 lot)")
    print("-" * 88)

    print(f"  📥 Synthesizing 30 full days of authentic Gold tick regimes ({bars_count:,} M1 bars)...")
    data = generate_realistic_gold_data(num_bars=bars_count, seed=101, volatility=0.68)

    # Strategy Parameters for Golden Sessions
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
        enable_session_filter=False, # We filter directly in execution loop or session check
        enable_be=True,
        be_trigger_ratio=0.70
    )

    print("  🚀 Running causal backtest simulation across the full 30-day dataset...")
    # Run base causal backtest
    result = run_causal_backtest(
        opens=data["opens"],
        highs=data["highs"],
        lows=data["lows"],
        closes=data["closes"],
        times=data["times"],
        volumes=data["volumes"],
        params=params,
        initial_balance=10000.0,
        split_ratio=0.75,
        spread_points=0.25,
        commission_per_lot_usd=7.0,
        fixed_lot_size=0.10,
        num_noise_shuffles=50
    )

    # Filter trades to strictly the Golden Sessions
    all_trades = result.trades
    golden_trades = []
    for t in all_trades:
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

    # Day-by-day analysis
    daily_stats: Dict[str, Dict[str, Any]] = {}
    daily_stats_capped: Dict[str, Dict[str, Any]] = {}

    for t in golden_trades:
        day_key = t.entry_time.split("T")[0] if "T" in t.entry_time else t.entry_time[:10]
        if day_key not in daily_stats:
            daily_stats[day_key] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "pips": 0.0}
            daily_stats_capped[day_key] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "pips": 0.0, "locked": False}

        # Calculate pips (Gold points * 10)
        pts = (t.exit_price - t.entry_price) if t.direction == "BUY" else (t.entry_price - t.exit_price)
        pips = pts * 10.0

        # Uncapped mode
        daily_stats[day_key]["trades"] += 1
        daily_stats[day_key]["pnl"] += t.net_pnl_usd
        daily_stats[day_key]["pips"] += pips
        if t.net_pnl_usd > 0:
            daily_stats[day_key]["wins"] += 1
        else:
            daily_stats[day_key]["losses"] += 1

        # Capped mode (locks trading for the day once 100 pips / $10 on 0.01 lot is reached)
        if not daily_stats_capped[day_key]["locked"]:
            daily_stats_capped[day_key]["trades"] += 1
            daily_stats_capped[day_key]["pnl"] += t.net_pnl_usd
            daily_stats_capped[day_key]["pips"] += pips
            if t.net_pnl_usd > 0:
                daily_stats_capped[day_key]["wins"] += 1
            else:
                daily_stats_capped[day_key]["losses"] += 1

            if daily_stats_capped[day_key]["pips"] >= 100.0 or daily_stats_capped[day_key]["pnl"] >= 100.0:
                daily_stats_capped[day_key]["locked"] = True

    total_golden_trades = len(golden_trades)
    winning_trades = sum(st["wins"] for st in daily_stats.values())
    losing_trades = sum(st["losses"] for st in daily_stats.values())
    win_rate = (winning_trades / total_golden_trades * 100) if total_golden_trades > 0 else 0
    total_net_pnl_010 = sum(st["pnl"] for st in daily_stats.values())
    total_net_pnl_001 = total_net_pnl_010 / 10.0
    total_pips = sum(st["pips"] for st in daily_stats.values())

    gross_wins = sum(t.net_pnl_usd for t in golden_trades if t.net_pnl_usd > 0)
    gross_losses = abs(sum(t.net_pnl_usd for t in golden_trades if t.net_pnl_usd < 0))
    pf = (gross_wins / gross_losses) if gross_losses > 0 else 99.0

    print("\n" + "=" * 88)
    print("  📊 1-MONTH (30 DAYS) GOLDEN SESSIONS PERFORMANCE SUMMARY")
    print("=" * 88)
    print(f"  • Total Trades Taken:      {total_golden_trades} trades (~{total_golden_trades/days:.1f} trades/day)")
    print(f"  • Overall Win Rate:        {win_rate:.1f}% ({winning_trades} Wins / {losing_trades} Losses)")
    print(f"  • Profit Factor:           {pf:.2f}")
    print(f"  • Total Net PnL (0.10):    ${total_net_pnl_010:+,.2f} USD")
    print(f"  • Total Net PnL (0.01):    ${total_net_pnl_001:+,.2f} USD")
    print(f"  • Total Pips Captured:     {total_pips:+,.1f} Pips across 30 Days")
    print(f"  • Average Pips Per Day:    {total_pips/days:+,.1f} Pips/Day")
    print(f"  • Average Profit Per Day:  ${total_net_pnl_001/days:+.2f} USD/Day on 0.01 Lot")
    print("-" * 88)

    print("\n📅 FULL 30-DAY LOG (DAY-BY-DAY AUDIT):")
    print("-" * 88)
    print(f" {'Day':<8} | {'Date':<10} | {'Trades':<7} | {'Win %':<7} | {'Pips Captured':<15} | {'0.01 Lot':<10} | {'0.10 Lot':<12} | {'Goal Target'}")
    print("-" * 88)

    days_100_hit = 0
    day_i = 1
    for d_key, d_st in sorted(daily_stats.items()):
        wr = (d_st["wins"] / d_st["trades"] * 100) if d_st["trades"] > 0 else 0
        pnl_010 = d_st["pnl"]
        pnl_001 = pnl_010 / 10.0
        pips = d_st["pips"]
        
        hit_str = "🎯 100+ PIPS HIT!" if pips >= 100.0 or pnl_001 >= 10.0 else ("🟢 Profitable" if pips > 0 else "🔴 Loss Day")
        if pips >= 100.0 or pnl_001 >= 10.0:
            days_100_hit += 1

        print(f" Day {day_i:02d}  | {d_key} | {d_st['trades']:<7} | {wr:5.1f}% | {pips:+10.1f} pips  | ${pnl_001:+8.2f}  | ${pnl_010:+9.2f}  | {hit_str}")
        day_i += 1

    print("-" * 88)
    print(f"  🎯 100-Pip Target Consistency Rate: {days_100_hit} out of {len(daily_stats)} Days ({days_100_hit/len(daily_stats)*100:.1f}%)")
    
    # Capped results comparison
    tot_capped_pnl_001 = sum(st["pnl"] for st in daily_stats_capped.values()) / 10.0
    tot_capped_pips = sum(st["pips"] for st in daily_stats_capped.values())
    print("\n" + "=" * 88)
    print("  🔒 BENEFIT OF AUTO-PROFIT LOCK (Target Hit -> Stop for the Day):")
    print(f"     • With 100-Pip Profit Lock: Total Net = ${tot_capped_pnl_001:+,.2f} USD on 0.01 lot ({tot_capped_pips:+,.1f} pips)")
    print(f"     • Without Lock (Uncapped):  Total Net = ${total_net_pnl_001:+,.2f} USD on 0.01 lot ({total_pips:+,.1f} pips)")
    print("=" * 88)


if __name__ == "__main__":
    run_1month_golden_backtest()
