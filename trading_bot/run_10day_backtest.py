"""
Comprehensive 24-Hour Multi-Session Backtest & Analytics Engine for XAU/USD (Gold M1)
Runs across all 24 hours (14,400 bars over 10 days) without any session blocks or circuit breakers,
analyzing which specific sessions/hours produce the highest win rates, profit factors, and daily pips.
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


def classify_session(hour_utc: int) -> str:
    if 0 <= hour_utc < 7:
        return "Asian Session (00:00-07:00 UTC | PKT 05:00-12:00)"
    elif 7 <= hour_utc < 12:
        return "London Session (07:00-12:00 UTC | PKT 12:00-17:00)"
    elif 12 <= hour_utc < 16:
        return "NY Morning / US Overlap (12:00-16:00 UTC | PKT 17:00-21:00)"
    elif 16 <= hour_utc < 21:
        return "NY Afternoon (16:00-21:00 UTC | PKT 21:00-02:00)"
    else:
        return "Pacific / Off-Hours (21:00-24:00 UTC | PKT 02:00-05:00)"


def run_24h_session_analysis():
    days = 10
    bars_count = days * 1440
    print("=" * 85)
    print(f"  🏆 RUNNING FULL 24-HOUR MULTI-SESSION AUDIT ON XAU/USD (GOLD M1) - {bars_count:,} BARS")
    print("=" * 85)
    print("  ⚙️ Test Setup: Pure 24-Hour Operation (Zero Session Blocks, Zero Circuit Breaker Halts)")
    print("     • Fast EMA: 9 | Slow EMA: 21 | M15 EMA 50 Macro Alignment (Quantified Neutrality)")
    print("     • Anti-Exhaustion Proximity Shield: <= 2.2 ATR from EMA9")
    print("     • Realistic Gold SL: $1.80 min to $3.80 max | RR: 1:1.50")
    print("     • Execution: Next-Bar Open | Spread: $0.25 | Commission: $7.00/lot")
    print("-" * 85)

    print(f"  📥 Loading/Synthesizing 10 full 24-hour days of authentic Gold tick regimes ({bars_count:,} M1 candles)...")
    data = generate_realistic_gold_data(num_bars=bars_count, seed=42, volatility=0.65)

    # 1. TEST CONFIG A: Dynamic 70% BE
    params_be = StrategyParameters(
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
        avoid_toxic_hours=False,  # 24H Full Testing
        enable_session_filter=False, # 24H Full Testing
        enable_be=True,
        be_trigger_ratio=0.70
    )

    print("  🚀 Simulating 24-Hour Causal Execution (With 70% BE Shield)...")
    res_be = run_causal_backtest(
        opens=data["opens"],
        highs=data["highs"],
        lows=data["lows"],
        closes=data["closes"],
        times=data["times"],
        volumes=data["volumes"],
        params=params_be,
        initial_balance=10000.0,
        split_ratio=0.75,
        spread_points=0.25,
        commission_per_lot_usd=7.0,
        fixed_lot_size=0.10,
        num_noise_shuffles=100
    )

    # 2. TEST CONFIG B: Pure 1:1.5 RR (No BE - Let Winners Run as Claude advised)
    params_no_be = StrategyParameters(
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
        enable_be=False  # Let Winners Run
    )

    print("  🚀 Simulating 24-Hour Causal Execution (Pure 1:1.5 RR - No BE Lock)...")
    res_no_be = run_causal_backtest(
        opens=data["opens"],
        highs=data["highs"],
        lows=data["lows"],
        closes=data["closes"],
        times=data["times"],
        volumes=data["volumes"],
        params=params_no_be,
        initial_balance=10000.0,
        split_ratio=0.75,
        spread_points=0.25,
        commission_per_lot_usd=7.0,
        fixed_lot_size=0.10,
        num_noise_shuffles=50
    )

    # Pick the superior model
    ov_be = res_be.overall_metrics
    ov_nobe = res_no_be.overall_metrics
    print("\n" + "=" * 85)
    print("  🥊 BREAK-EVEN (BE) EXPERIMENT: CLAUDE'S HYPOTHESIS TEST")
    print("=" * 85)
    print(f"  • With 70% BE Lock:   Net PnL = ${ov_be.total_net_pnl_usd:+8.2f} | Win Rate = {ov_be.win_rate_pct:.1f}% | PF = {ov_be.profit_factor:.2f}")
    print(f"  • Pure 1:1.5 RR (No BE): Net PnL = ${ov_nobe.total_net_pnl_usd:+8.2f} | Win Rate = {ov_nobe.win_rate_pct:.1f}% | PF = {ov_nobe.profit_factor:.2f}")
    better_model = res_be if ov_be.total_net_pnl_usd >= ov_nobe.total_net_pnl_usd else res_no_be
    better_name = "With 70% BE Lock" if better_model == res_be else "Pure 1:1.5 RR (No BE)"
    print(f"  ⭐ Winning Architecture: {better_name}")
    print("=" * 85)

    # Perform Deep Session Breakdown on the Best Result
    trades = better_model.trades
    ov = better_model.overall_metrics

    session_data: Dict[str, Dict[str, Any]] = {}
    hourly_data: Dict[int, Dict[str, Any]] = {h: {"trades": 0, "wins": 0, "pnl": 0.0, "pips": 0.0} for h in range(24)}
    daily_data: Dict[str, Dict[str, Any]] = {}

    for t in trades:
        # Determine hour and session
        hour = 0
        if "T" in t.entry_time:
            hour = int(t.entry_time.split("T")[1].split(":")[0])
            day = t.entry_time.split("T")[0]
        else:
            day = t.entry_time[:10]
            try:
                hour = int(t.entry_time.split(" ")[1].split(":")[0])
            except Exception:
                hour = 0

        sess = classify_session(hour)
        if sess not in session_data:
            session_data[sess] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "pips": 0.0}
        
        # Pips calculation: On Gold, $1.00 move = 10 pips ($1.00 on 0.01 lot)
        # On 0.10 lot, 10 pips = $10.00 PnL. So pips = (t.net_pnl_usd / 10.0) * 10 = net_pnl_usd
        # Point diff on Gold:
        if t.direction == "BUY":
            pts = (t.exit_price - t.entry_price) if t.exit_price else 0.0
        else:
            pts = (t.entry_price - t.exit_price) if t.exit_price else 0.0
        pips = pts * 10.0

        session_data[sess]["trades"] += 1
        session_data[sess]["pnl"] += t.net_pnl_usd
        session_data[sess]["pips"] += pips
        if t.net_pnl_usd > 0:
            session_data[sess]["wins"] += 1
        else:
            session_data[sess]["losses"] += 1

        hourly_data[hour]["trades"] += 1
        hourly_data[hour]["pnl"] += t.net_pnl_usd
        hourly_data[hour]["pips"] += pips
        if t.net_pnl_usd > 0:
            hourly_data[hour]["wins"] += 1

        if day not in daily_data:
            daily_data[day] = {"trades": 0, "wins": 0, "pnl": 0.0, "pips": 0.0}
        daily_data[day]["trades"] += 1
        daily_data[day]["pnl"] += t.net_pnl_usd
        daily_data[day]["pips"] += pips
        if t.net_pnl_usd > 0:
            daily_data[day]["wins"] += 1

    print("\n" + "=" * 85)
    print("  🌐 24-HOUR GLOBAL SESSION BREAKDOWN (10 DAYS AUDIT)")
    print("=" * 85)
    print(f" {'Trading Session':<42} | {'Trades':<7} | {'Win %':<7} | {'Net PnL (0.10)':<14} | {'Pips':<9} | {'0.01 Lot ($)'}")
    print("-" * 95)
    for s_name, s_st in session_data.items():
        wr = (s_st["wins"] / s_st["trades"] * 100) if s_st["trades"] > 0 else 0
        micro_pnl = s_st["pnl"] / 10.0
        print(f" {s_name:<42} | {s_st['trades']:<7} | {wr:5.1f}% | ${s_st['pnl']:+11.2f}  | {s_st['pips']:+8.1f} | ${micro_pnl:+8.2f}")
    print("-" * 95)
    print(f" {'OVERALL 24-HOUR TOTAL':<42} | {ov.total_trades:<7} | {ov.win_rate_pct:5.1f}% | ${ov.total_net_pnl_usd:+11.2f}  | {sum(d['pips'] for d in daily_data.values()):+8.1f} | ${ov.total_net_pnl_usd/10.0:+8.2f}\n")

    print("=" * 85)
    print("  📅 DAILY TARGET & 100-PIP BENCHMARK TRACKER (0.01 Lot vs 0.10 Lot)")
    print("=" * 85)
    print(f" {'Day':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Pips Captured':<15} | {'0.01 Lot PnL':<14} | {'0.10 Lot PnL'}")
    print("-" * 85)
    d_num = 1
    total_pips = 0.0
    days_100pips_hit = 0
    for d_key, d_st in sorted(daily_data.items()):
        wr = (d_st["wins"] / d_st["trades"] * 100) if d_st["trades"] > 0 else 0
        micro_usd = d_st["pnl"] / 10.0
        pips = d_st["pips"]
        total_pips += pips
        hit_marker = "🎯 100 PIPS HIT!" if pips >= 100.0 or micro_usd >= 10.0 else ""
        if pips >= 100.0 or micro_usd >= 10.0:
            days_100pips_hit += 1
        print(f" Day {d_num:02d} ({d_key}) | {d_st['trades']:<8} | {wr:5.1f}%     | {pips:+10.1f} pips  | ${micro_usd:+8.2f} USD  | ${d_st['pnl']:+9.2f} USD {hit_marker}")
        d_num += 1
    print("-" * 85)
    avg_pips_day = total_pips / days
    avg_micro_usd = (ov.total_net_pnl_usd / 10.0) / days
    print(f"  • Average Pips Captured per Day:    {avg_pips_day:+.1f} Pips/Day")
    print(f"  • Average Daily Profit on 0.01 Lot: ${avg_micro_usd:+.2f} USD/Day")
    print(f"  • 100-Pip Target Met:               {days_100pips_hit} out of {days} days")
    print("=" * 85)

    print("\n⏰ HOURLY PROFITABILITY HEATMAP (UTC HOURS 00 to 23):")
    print("-" * 65)
    print(f" {'UTC Hour':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Net PnL ($)':<12} | {'Status'}")
    print("-" * 65)
    for h in range(24):
        h_st = hourly_data[h]
        if h_st["trades"] > 0:
            h_wr = (h_st["wins"] / h_st["trades"] * 100)
            status = "🟢 Highly Profitable" if h_st["pnl"] >= 50 else ("🟡 Profitable" if h_st["pnl"] > 0 else "🔴 Loss Maker")
            print(f" {h:02d}:00 UTC  | {h_st['trades']:<8} | {h_wr:5.1f}%     | ${h_st['pnl']:+8.2f}    | {status}")
        else:
            print(f" {h:02d}:00 UTC  | 0        |    -        | $    0.00    | ⚪ No Trades")
    print("-" * 65)

    return better_model


if __name__ == "__main__":
    run_24h_session_analysis()
