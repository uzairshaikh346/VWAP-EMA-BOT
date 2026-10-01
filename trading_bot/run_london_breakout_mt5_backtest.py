"""
LONDON MOMENTUM BREAKOUT & EXPANSION STRATEGY (GOLD REAL MT5 DATA)
Tests true Gold session breakout (Following the London trend expansion rather than fighting it).
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional


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


def run_london_breakout_backtest(
    symbol: str = "XAUUSDm",
    days_back: int = 30,
    lot_size: float = 0.01,
    rr_ratio: float = 1.50,
    daily_profit_target_usd: float = 10.0,
    daily_loss_limit_usd: float = 10.0,
    spread_points: float = 0.25
):
    print("=" * 95)
    print(f"  🏛️  LONDON SESSION MOMENTUM BREAKOUT & TREND EXPANSION (GOLD)")
    print("=" * 95)
    print(f"  📊 Strategy:                Breakout of Asian Range in London Open (Trend Continuation)")
    print(f"  📅 Period:                  {days_back} Days (Real MT5 Broker Data)")
    print(f"  💰 Capital:                 $100.00 USD (0.01 Lot)")
    print(f"  🎯 Risk:Reward:             1:{rr_ratio:.2f} with Dynamic 50% Break-Even Protection")
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
    atrs = calculate_atr(highs, lows, closes, 14)

    day_bars: Dict[str, List[int]] = {}
    for i, t_val in enumerate(times_int):
        dt = datetime.fromtimestamp(t_val, tz=timezone.utc)
        d_key = dt.strftime("%Y-%m-%d")
        if d_key not in day_bars:
            day_bars[d_key] = []
        day_bars[d_key].append(i)

    account_balance = 100.0
    total_wins = 0
    total_losses = 0
    total_trades = 0
    target_locked_days = 0
    loss_shielded_days = 0

    print(f"\n{'Day':<6} | {'Date':<10} | {'Trades':<8} | {'W/L':<8} | {'Daily PnL ($)':<14} | {'Balance ($)':<14} | {'Status'}")
    print("-" * 95)

    for idx, (d_key, bar_indices) in enumerate(sorted(day_bars.items()), 1):
        if len(bar_indices) < 50:
            continue

        # 1. Asian Range (00:00 - 06:00 UTC)
        asian_high = -1e9
        asian_low = 1e9
        asian_found = False

        for b_idx in bar_indices:
            dt = datetime.fromtimestamp(times_int[b_idx], tz=timezone.utc)
            if 0 <= dt.hour < 6:
                asian_high = max(asian_high, highs[b_idx])
                asian_low = min(asian_low, lows[b_idx])
                asian_found = True

        if not asian_found or (asian_high - asian_low) < 1.0 or (asian_high - asian_low) > 15.0:
            continue

        daily_trades = []
        daily_pnl = 0.0
        trade_taken = False
        asian_mid = (asian_high + asian_low) / 2.0

        for b_idx in bar_indices:
            if trade_taken:
                break
            dt = datetime.fromtimestamp(times_int[b_idx], tz=timezone.utc)
            
            # London Breakout Window (07:00 - 11:00 UTC)
            if 7 <= dt.hour <= 11:
                c_close = closes[b_idx]
                c_open = opens[b_idx]
                c_high = highs[b_idx]
                c_low = lows[b_idx]
                atr_val = atrs[b_idx] if atrs[b_idx] > 0 else 1.5

                action = None
                entry_p = 0.0
                sl_p = 0.0

                # Bullish Breakout: Candle closes ABOVE Asian High with body
                if c_close > asian_high and c_close > c_open and (c_close - asian_high) <= (1.0 * atr_val):
                    action = "BUY"
                    entry_p = opens[b_idx + 1] if b_idx + 1 < len(opens) else c_close
                    entry_p += spread_points
                    sl_p = asian_mid  # SL at Asian mid point or 1.5 ATR below
                    if (entry_p - sl_p) > 5.0:
                        sl_p = entry_p - 4.0
                    elif (entry_p - sl_p) < 2.0:
                        sl_p = entry_p - 2.5

                # Bearish Breakout: Candle closes BELOW Asian Low with body
                elif c_close < asian_low and c_close < c_open and (asian_low - c_close) <= (1.0 * atr_val):
                    action = "SELL"
                    entry_p = opens[b_idx + 1] if b_idx + 1 < len(opens) else c_close
                    sl_p = asian_mid
                    if (sl_p - entry_p) > 5.0:
                        sl_p = entry_p + 4.0
                    elif (sl_p - entry_p) < 2.0:
                        sl_p = entry_p + 2.5

                if action is not None:
                    trade_taken = True
                    risk_dist = abs(entry_p - sl_p)
                    tp_p = (entry_p + risk_dist * rr_ratio) if action == "BUY" else (entry_p - risk_dist * rr_ratio)
                    be_activated = False
                    
                    # Simulate with Dynamic 50% Break-Even
                    for future_idx in range(b_idx + 1, bar_indices[-1] + 1):
                        f_high = highs[future_idx]
                        f_low = lows[future_idx]

                        if not be_activated:
                            if action == "BUY" and f_high >= (entry_p + risk_dist * 0.50):
                                sl_p = entry_p + spread_points
                                be_activated = True
                            elif action == "SELL" and f_low <= (entry_p - risk_dist * 0.50):
                                sl_p = entry_p - spread_points
                                be_activated = True

                        # Exit checks
                        if action == "BUY":
                            if f_low <= sl_p:
                                pnl = ((sl_p - entry_p) * 0.01 * 100) - 0.35
                                daily_pnl += pnl
                                if pnl > 0:
                                    total_wins += 1
                                    daily_trades.append("W")
                                else:
                                    total_losses += 1
                                    daily_trades.append("L")
                                total_trades += 1
                                break
                            elif f_high >= tp_p:
                                pnl = ((tp_p - entry_p) * 0.01 * 100) - 0.35
                                daily_pnl += pnl
                                total_wins += 1
                                total_trades += 1
                                daily_trades.append("W")
                                break
                        elif action == "SELL":
                            if f_high >= sl_p:
                                pnl = ((entry_p - sl_p) * 0.01 * 100) - 0.35
                                daily_pnl += pnl
                                if pnl > 0:
                                    total_wins += 1
                                    daily_trades.append("W")
                                else:
                                    total_losses += 1
                                    daily_trades.append("L")
                                total_trades += 1
                                break
                            elif f_low <= tp_p:
                                pnl = ((entry_p - tp_p) * 0.01 * 100) - 0.35
                                daily_pnl += pnl
                                total_wins += 1
                                total_trades += 1
                                daily_trades.append("W")
                                break

        account_balance += daily_pnl
        w_cnt = daily_trades.count("W")
        l_cnt = daily_trades.count("L")
        t_cnt = len(daily_trades)

        status = "⚪ No Setup" if t_cnt == 0 else ("🟢 Green Day" if daily_pnl > 0 else "🔴 Red Day")
        if daily_pnl >= 8.0:
            target_locked_days += 1
        elif daily_pnl <= -8.0:
            loss_shielded_days += 1

        print(f"Day {idx:<2} | {d_key:<10} | {t_cnt:<8} | {w_cnt}W/{l_cnt}L{'':<3} | ${daily_pnl:+6.2f} USD{'':<4} | ${account_balance:7.2f} USD{'':<4} | {status}")

    win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
    net_p = account_balance - 100.0

    print("=" * 95)
    print(f"  🏁 SUMMARY (LONDON MOMENTUM BREAKOUT & EXPANSION):")
    print("=" * 95)
    print(f"  💵 Starting Capital:        $100.00 USD")
    print(f"  💰 Ending Capital:          ${account_balance:.2f} USD")
    print(f"  📈 Net Total Profit:        ${net_p:+.2f} USD ({(net_p/100)*100:+.1f}%)")
    print(f"  🎯 Overall Win Rate:        {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses across {total_trades} trades)")
    print("=" * 95)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="London Breakout Backtest")
    parser.add_argument("--symbol", type=str, default="XAUUSDm")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    run_london_breakout_backtest(symbol=args.symbol, days_back=args.days)
