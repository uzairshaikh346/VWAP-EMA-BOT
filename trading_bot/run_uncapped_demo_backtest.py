"""
15-Day and 30-Day Forward Backtest Simulation for $100 Capital Demo Account
WITHOUT Daily Profit Cap (Unlimited Daily Profit Potential)
Retaining:
- Starting Balance: $100.00
- Fixed Lot Size: 0.01 Lot
- Daily Max Loss Limit: -$10.00 (Halts trading for the day if -$10 hit)
- Daily Profit Target: NONE (Unlimited - trades entire Golden Sessions)
- Risk:Reward Ratio: 1:1.50 with 70% Break-Even Protection
- Golden Sessions: London (07-12 UTC) + NY Afternoon (16-21 UTC)
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


def run_uncapped_demo_simulation(days: int = 15):
    bars_count = days * 1440  # 15 days = 21,600 M1 bars
    print("=" * 95)
    print(f"  🧪 RUNNING {days}-DAY UNLIMITED DAILY PROFIT BACKTEST FOR $100.00 CAPITAL (0.01 LOT)")
    print("=" * 95)
    print(f"  💰 Starting Balance:       $100.00 USD")
    print(f"  📊 Fixed Lot Size:          0.01 Lot")
    print(f"  🎯 Daily Profit Goal:       NO CAP (Trades full Golden Sessions)")
    print(f"  🛑 Daily Max Loss Shield:   -$10.00 USD (-10% Capital Protection)")
    print(f"  ⚖️  Risk:Reward Ratio:       1:1.50 (with 70% Break-Even Shield)")
    print(f"  ⏰ Active Sessions:         London (12-5 PM PKT) & NY Afternoon (9 PM-2 AM PKT)")
    print("-" * 95)

    data = generate_realistic_gold_data(num_bars=bars_count, seed=42, volatility=0.68)

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

    result = run_causal_backtest(
        opens=data["opens"],
        highs=data["highs"],
        lows=data["lows"],
        closes=data["closes"],
        times=data["times"],
        volumes=data["volumes"],
        params=params,
        initial_balance=100.0,
        split_ratio=0.75,
        spread_points=0.25,
        commission_per_lot_usd=7.0,
        fixed_lot_size=0.01,
        num_noise_shuffles=20
    )

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

    days_data: Dict[str, List[Any]] = {}
    for t in golden_trades:
        day_key = t.entry_time.split("T")[0] if "T" in t.entry_time else t.entry_time[:10]
        if day_key not in days_data:
            days_data[day_key] = []
        days_data[day_key].append(t)

    account_balance = 100.0
    daily_results = []
    total_wins = 0
    total_losses = 0
    total_trades_taken = 0
    loss_limit_days = 0

    print(f"\n{'Day':<6} | {'Date':<10} | {'Trades':<8} | {'W/L':<8} | {'Daily PnL ($)':<14} | {'End Balance ($)':<16} | {'Status'}")
    print("-" * 95)

    for i, (day_key, trades_in_day) in enumerate(sorted(days_data.items()), 1):
        day_pnl = 0.0
        day_wins = 0
        day_losses = 0
        day_trades = 0
        day_halted = False
        status = "Active Session"

        for t in trades_in_day:
            if day_halted:
                continue

            day_trades += 1
            total_trades_taken += 1
            day_pnl += t.net_pnl_usd

            if t.net_pnl_usd > 0:
                day_wins += 1
                total_wins += 1
            else:
                day_losses += 1
                total_losses += 1

            # Only Daily Max Loss limit applies (-$10 USD), NO PROFIT CAP
            if day_pnl <= -10.0:
                day_halted = True
                status = "🛑 Max Loss Shield (-$10 Stop)"
                loss_limit_days += 1
                break

        if not day_halted:
            if day_pnl > 0:
                status = f"🟢 Green Day (+${day_pnl:.2f})"
            elif day_pnl < 0:
                status = f"🔴 Red Day (-${abs(day_pnl):.2f})"
            else:
                status = "⚪ Break-Even"

        account_balance += day_pnl
        daily_results.append({
            "day": i,
            "date": day_key,
            "trades": day_trades,
            "wins": day_wins,
            "losses": day_losses,
            "pnl": day_pnl,
            "balance": account_balance,
            "status": status
        })

        print(f"Day {i:<2} | {day_key:<10} | {day_trades:<8} | {day_wins}W/{day_losses}L{'':<3} | ${day_pnl:+6.2f} USD{'':<4} | ${account_balance:7.2f} USD{'':<5} | {status}")

    win_rate = (total_wins / total_trades_taken * 100.0) if total_trades_taken > 0 else 0.0
    net_profit = account_balance - 100.0
    roi_pct = (net_profit / 100.0) * 100.0

    print("=" * 95)
    print(f"  🏁 FINAL {days}-DAY UNLIMITED PROFIT RESULTS:")
    print("=" * 95)
    print(f"  💵 Starting Balance:       $100.00 USD")
    print(f"  💰 Ending Balance:         ${account_balance:.2f} USD")
    print(f"  📈 Net Total Profit:       ${net_profit:+.2f} USD ({roi_pct:+.1f}% ROI)")
    print(f"  🎯 Overall Win Rate:       {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses across {total_trades_taken} trades)")
    print(f"  🛡️ Days Loss Shielded:     {loss_limit_days} Days stopped at -$10.00 max loss")
    print("=" * 95)


if __name__ == "__main__":
    run_uncapped_demo_simulation(15)
