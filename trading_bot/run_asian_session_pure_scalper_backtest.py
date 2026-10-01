"""
ASIAN SESSION PURE MEAN-REVERSION SCALPER (REAL MT5 DATA)
Trades ONLY the predictable Asian Range (00:00 - 06:00 UTC / 5 AM - 11 AM PKT).
Auto-Halted before London open to lock in all morning profits!
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional


def calculate_ema(data: List[float], period: int) -> List[float]:
    if not data or len(data) < period:
        return []
    alpha = 2.0 / (period + 1)
    ema = [0.0] * len(data)
    ema[period - 1] = sum(data[:period]) / period
    for i in range(period, len(data)):
        ema[i] = (data[i] * alpha) + (ema[i - 1] * (1.0 - alpha))
    return ema


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    n = len(closes)
    if n < period + 1:
        return [0.0] * n
    tr = [0.0] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    atr = [0.0] * n
    atr[period] = sum(tr[1:period + 1]) / period
    for i in range(period + 1, n):
        atr[i] = ((atr[i - 1] * (period - 1)) + tr[i]) / period
    return atr


def calculate_bollinger_bands(closes: List[float], period: int = 20, std_dev: float = 2.0):
    n = len(closes)
    mid = [0.0] * n
    upper = [0.0] * n
    lower = [0.0] * n
    for i in range(period - 1, n):
        slice_c = closes[i - period + 1:i + 1]
        m = sum(slice_c) / period
        variance = sum((x - m) ** 2 for x in slice_c) / period
        sd = variance ** 0.5
        mid[i] = m
        upper[i] = m + (std_dev * sd)
        lower[i] = m - (std_dev * sd)
    return upper, mid, lower


def run_asian_pure_scalper(
    symbol: str = "XAUUSDm",
    days_back: int = 30,
    lot_size: float = 0.01,
    daily_profit_target_usd: float = 10.0,
    daily_loss_limit_usd: float = 10.0,
    spread_points: float = 0.25,
    commission_per_lot_usd: float = 7.0
):
    print("=" * 95)
    print(f"  🏛️  ASIAN SESSION PURE MEAN-REVERSION SCALPER (REAL MT5 BROKER DATA)")
    print("=" * 95)
    print(f"  📊 Asset:                   {symbol} (M5 Timeframe)")
    print(f"  ⏰ Active Trading Hours:    00:00 - 05:30 UTC ONLY (05:00 AM - 10:30 AM PKT)")
    print(f"  🛑 Hard London Freeze:      All trading strictly STOPPED before London Open (06:00 UTC)")
    print(f"  🎯 Daily Profit Goal:       +${daily_profit_target_usd:.2f} USD (Auto-Lock)")
    print(f"  🛑 Daily Max Loss Shield:   -${daily_loss_limit_usd:.2f} USD")
    print("=" * 95)

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("❌ MetaTrader5 package not installed!", flush=True)
        return

    if not mt5.initialize():
        print(f"❌ MT5 init failed: {mt5.last_error()}", flush=True)
        return

    selected_symbol = symbol
    if not mt5.symbol_select(selected_symbol, True):
        alt = "XAUUSD" if "m" in symbol else "XAUUSDm"
        if mt5.symbol_select(alt, True):
            selected_symbol = alt
        else:
            print(f"❌ Symbol {symbol} not found!", flush=True)
            mt5.shutdown()
            return

    target_bars = days_back * 288
    rates = mt5.copy_rates_from_pos(selected_symbol, mt5.TIMEFRAME_M5, 0, target_bars)
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        print("❌ No rates returned from MT5!", flush=True)
        return

    opens = [float(r['open']) for r in rates]
    highs = [float(r['high']) for r in rates]
    lows = [float(r['low']) for r in rates]
    closes = [float(r['close']) for r in rates]
    times_int = [int(r['time']) for r in rates]
    times_str = [datetime.fromtimestamp(t, tz=timezone.utc).isoformat() for t in times_int]

    upper_bb, mid_bb, lower_bb = calculate_bollinger_bands(closes, 20, 2.0)
    ema9 = calculate_ema(closes, 9)
    atrs = calculate_atr(highs, lows, closes, 14)

    min_warmup = 50
    comm_per_trade = (commission_per_lot_usd * lot_size) + (spread_points * lot_size * 100)

    days_data: Dict[str, Dict[str, Any]] = {}
    active_trade: Optional[Dict[str, Any]] = None

    for i in range(min_warmup, len(closes) - 1):
        bar_dt = datetime.fromtimestamp(times_int[i], tz=timezone.utc)
        bar_hour = bar_dt.hour
        bar_min = bar_dt.minute
        day_key = bar_dt.strftime("%Y-%m-%d")

        if day_key not in days_data:
            days_data[day_key] = {
                "trades": [],
                "realized_pnl": 0.0,
                "is_halted": False,
                "halt_reason": ""
            }

        # 1. Manage Active Trade
        if active_trade is not None:
            curr_high = highs[i]
            curr_low = lows[i]
            direction = active_trade["direction"]
            entry_p = active_trade["entry_price"]
            sl_p = active_trade["sl"]
            tp_p = active_trade["tp"]
            t_day_key = active_trade["day_key"]

            exit_trade = False
            exit_price = 0.0
            exit_reason = ""

            # Check Hard London Cut-off (Force close by 06:00 UTC)
            if bar_hour >= 6:
                exit_trade = True
                exit_price = closes[i]
                exit_reason = "SESSION_CLOSE"
            elif direction == "BUY":
                if curr_low <= sl_p:
                    exit_trade = True
                    exit_price = sl_p
                    exit_reason = "SL"
                elif curr_high >= tp_p:
                    exit_trade = True
                    exit_price = tp_p
                    exit_reason = "TP"
            elif direction == "SELL":
                if curr_high >= sl_p:
                    exit_trade = True
                    exit_price = sl_p
                    exit_reason = "SL"
                elif curr_low <= tp_p:
                    exit_trade = True
                    exit_price = tp_p
                    exit_reason = "TP"

            if exit_trade:
                points_diff = (exit_price - entry_p) if direction == "BUY" else (entry_p - exit_price)
                gross_pnl = points_diff * lot_size * 100
                net_pnl = gross_pnl - comm_per_trade

                active_trade["exit_price"] = exit_price
                active_trade["exit_reason"] = exit_reason
                active_trade["net_pnl"] = net_pnl
                active_trade["is_win"] = net_pnl > 0

                days_data[t_day_key]["trades"].append(active_trade)
                days_data[t_day_key]["realized_pnl"] += net_pnl

                if days_data[t_day_key]["realized_pnl"] <= -daily_loss_limit_usd:
                    days_data[t_day_key]["is_halted"] = True
                    days_data[t_day_key]["halt_reason"] = "🛑 Daily Loss Shield (-$10 Stop)"

                if days_data[t_day_key]["realized_pnl"] >= daily_profit_target_usd:
                    days_data[t_day_key]["is_halted"] = True
                    days_data[t_day_key]["halt_reason"] = "🎯 Daily Profit Target (+ $10 Lock)"

                active_trade = None

        # 2. Check for New Entry (ONLY during 00:00 - 05:15 UTC)
        if active_trade is None:
            if days_data[day_key]["is_halted"]:
                continue

            if not (0 <= bar_hour < 5 or (bar_hour == 5 and bar_min <= 15)):
                continue

            c_close = closes[i]
            c_open = opens[i]
            c_high = highs[i]
            c_low = lows[i]
            u_bb = upper_bb[i]
            l_bb = lower_bb[i]
            m_bb = mid_bb[i]
            e9 = ema9[i]
            atr_val = atrs[i] if atrs[i] > 0 else 1.2

            action = None
            sl_price = 0.0
            tp_price = 0.0

            # LONG Mean Reversion: Price touches/pierces Lower Bollinger Band and rejects back with green candle
            if (c_low <= l_bb or closes[i - 1] <= lower_bb[i - 1]) and c_close > c_open and c_close > l_bb:
                action = "BUY"
                sl_price = min(c_low, l_bb) - (0.5 * atr_val)
                tp_price = m_bb  # Target middle band (EMA 20)

            # SHORT Mean Reversion: Price touches/pierces Upper Bollinger Band and rejects back with red candle
            elif (c_high >= u_bb or closes[i - 1] >= upper_bb[i - 1]) and c_close < c_open and c_close < u_bb:
                action = "SELL"
                sl_price = max(c_high, u_bb) + (0.5 * atr_val)
                tp_price = m_bb

            if action is not None:
                entry_fill = opens[i + 1] if i + 1 < len(opens) else c_close
                if action == "BUY":
                    entry_fill += spread_points

                risk_dist = abs(entry_fill - sl_price)
                reward_dist = abs(entry_fill - tp_price)

                if risk_dist < 1.8:
                    risk_dist = 1.8
                elif risk_dist > 4.5:
                    continue  # Skip wide risk trades in Asia

                if reward_dist < (1.1 * risk_dist):
                    # Set minimum 1:1.2 RR target
                    tp_price = (entry_fill + risk_dist * 1.20) if action == "BUY" else (entry_fill - risk_dist * 1.20)

                active_trade = {
                    "entry_bar": i + 1,
                    "entry_time": times_str[i + 1],
                    "day_key": day_key,
                    "direction": action,
                    "entry_price": entry_fill,
                    "sl": (entry_fill - risk_dist) if action == "BUY" else (entry_fill + risk_dist),
                    "tp": tp_price
                }

    # Print Table
    print(f"\n{'Day':<6} | {'Date':<10} | {'Trades':<8} | {'W/L':<8} | {'Daily PnL ($)':<14} | {'Balance ($)':<14} | {'Status'}")
    print("-" * 95)

    account_balance = 100.0
    total_wins = 0
    total_losses = 0
    total_trades = 0
    green_days = 0
    target_lock_days = 0
    loss_shield_days = 0

    for idx, (d_key, d_info) in enumerate(sorted(days_data.items()), 1):
        d_trades = d_info["trades"]
        if len(d_trades) == 0:
            continue

        d_pnl = d_info["realized_pnl"]
        d_w = sum(1 for t in d_trades if t["is_win"])
        d_l = len(d_trades) - d_w
        total_wins += d_w
        total_losses += d_l
        total_trades += len(d_trades)

        account_balance += d_pnl

        status_str = d_info["halt_reason"]
        if not status_str:
            if d_pnl > 0:
                status_str = "🟢 Green Day"
                green_days += 1
            elif d_pnl < 0:
                status_str = "🔴 Red Day"
            else:
                status_str = "⚪ Break-Even"
        else:
            if "Target" in status_str:
                target_lock_days += 1
                green_days += 1
            elif "Shield" in status_str:
                loss_shield_days += 1

        print(f"Day {idx:<2} | {d_key:<10} | {len(d_trades):<8} | {d_w}W/{d_l}L{'':<3} | ${d_pnl:+6.2f} USD{'':<4} | ${account_balance:7.2f} USD{'':<4} | {status_str}")

    win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
    net_profit = account_balance - 100.0
    roi = (net_profit / 100.0) * 100.0

    print("=" * 95)
    print(f"  🏁 ASIAN SESSION SCALPER SUMMARY ({selected_symbol} | {days_back} DAYS):")
    print("=" * 95)
    print(f"  💵 Starting Balance:         $100.00 USD")
    print(f"  💰 Ending Balance:           ${account_balance:.2f} USD")
    print(f"  📈 Net Total Profit:         ${net_profit:+.2f} USD ({roi:+.1f}% ROI)")
    print(f"  🎯 Overall Win Rate:         {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses across {total_trades} trades)")
    print(f"  🏆 Days Target Locked:       {target_lock_days} Days locked at +$10.00 Target")
    print(f"  🛡️ Days Loss Shielded:       {loss_shield_days} Days protected at -$10.00 Max Loss")
    print("=" * 95)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Asian Session Pure Scalper")
    parser.add_argument("--symbol", type=str, default="XAUUSDm")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    run_asian_pure_scalper(symbol=args.symbol, days_back=args.days)
