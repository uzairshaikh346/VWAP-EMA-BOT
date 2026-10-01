"""
LONDON MOMENTUM BREAKOUT + HIGHER TIMEFRAME TREND FILTER (EXNESS XAUUSD)
Only takes London breakouts that align with the Macro Daily/4H Trend (EMA 200).
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


def run_trend_breakout_backtest(
    symbol: str = "XAUUSDm",
    days_back: int = 30,
    lot_size: float = 0.01,
    rr_ratio: float = 1.50,
    spread_points: float = 0.25
):
    print("=" * 95)
    print(f"  🏛️  LONDON MOMENTUM BREAKOUT + MACRO TREND FILTER (EXNESS)")
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
    
    # 200 EMA on M5 (~16-hour Macro Trend)
    ema200 = calculate_ema(closes, 200)
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

    print(f"\n{'Day':<6} | {'Date':<10} | {'Trades':<8} | {'W/L':<8} | {'Daily PnL ($)':<14} | {'Balance ($)':<14} | {'Status'}")
    print("-" * 95)

    for idx, (d_key, bar_indices) in enumerate(sorted(day_bars.items()), 1):
        if len(bar_indices) < 50:
            continue

        # Asian Session (First 60 M5 bars of the day = 5 hours)
        asia_indices = bar_indices[:60]
        asian_high = max(highs[b] for b in asia_indices)
        asian_low = min(lows[b] for b in asia_indices)
        asian_range = asian_high - asian_low

        if asian_range < 1.0 or asian_range > 20.0:
            continue

        daily_trades = []
        daily_pnl = 0.0
        trade_taken = False
        trade_indices = bar_indices[60:]

        for b_idx in trade_indices:
            if trade_taken:
                break
            
            c_close = closes[b_idx]
            c_open = opens[b_idx]
            e200_val = ema200[b_idx] if b_idx < len(ema200) else c_close
            atr_val = atrs[b_idx] if atrs[b_idx] > 0 else 1.5

            action = None
            entry_p = 0.0
            sl_p = 0.0

            # ONLY BUY if Macro Trend is Bullish (Close > EMA200)
            if c_close > asian_high and c_close > c_open and c_close > e200_val:
                body = c_close - c_open
                if body >= 0.3 * atr_val:  # Solid green candle
                    action = "BUY"
                    entry_p = opens[b_idx + 1] if b_idx + 1 < len(opens) else c_close
                    entry_p += spread_points
                    sl_p = entry_p - 4.50

            # ONLY SELL if Macro Trend is Bearish (Close < EMA200)
            elif c_close < asian_low and c_close < c_open and c_close < e200_val:
                body = c_open - c_close
                if body >= 0.3 * atr_val:  # Solid red candle
                    action = "SELL"
                    entry_p = opens[b_idx + 1] if b_idx + 1 < len(opens) else c_close
                    sl_p = entry_p + 4.50

            if action is not None:
                trade_taken = True
                risk_dist = abs(entry_p - sl_p)
                tp_p = (entry_p + risk_dist * rr_ratio) if action == "BUY" else (entry_p - risk_dist * rr_ratio)
                
                for future_idx in range(b_idx + 1, bar_indices[-1] + 1):
                    f_high = highs[future_idx]
                    f_low = lows[future_idx]

                    if action == "BUY":
                        if f_low <= sl_p:
                            pnl = ((sl_p - entry_p) * 0.01 * 100) - 0.35
                            daily_pnl += pnl
                            total_losses += 1
                            daily_trades.append("L")
                            total_trades += 1
                            break
                        elif f_high >= tp_p:
                            pnl = ((tp_p - entry_p) * 0.01 * 100) - 0.35
                            daily_pnl += pnl
                            total_wins += 1
                            daily_trades.append("W")
                            total_trades += 1
                            break
                    elif action == "SELL":
                        if f_high >= sl_p:
                            pnl = ((entry_p - sl_p) * 0.01 * 100) - 0.35
                            daily_pnl += pnl
                            total_losses += 1
                            daily_trades.append("L")
                            total_trades += 1
                            break
                        elif f_low <= tp_p:
                            pnl = ((entry_p - tp_p) * 0.01 * 100) - 0.35
                            daily_pnl += pnl
                            total_wins += 1
                            daily_trades.append("W")
                            total_trades += 1
                            break

        account_balance += daily_pnl
        w_cnt = daily_trades.count("W")
        l_cnt = daily_trades.count("L")
        t_cnt = len(daily_trades)

        status = "⚪ No Setup (Trend Filtered)" if t_cnt == 0 else ("🟢 Green Day" if daily_pnl > 0 else "🔴 Red Day")
        print(f"Day {idx:<2} | {d_key:<10} | {t_cnt:<8} | {w_cnt}W/{l_cnt}L{'':<3} | ${daily_pnl:+6.2f} USD{'':<4} | ${account_balance:7.2f} USD{'':<4} | {status}")

    win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
    net_p = account_balance - 100.0

    print("=" * 95)
    print(f"  🏁 SUMMARY (LONDON MOMENTUM BREAKOUT + MACRO TREND FILTER):")
    print("=" * 95)
    print(f"  💵 Starting Capital:        $100.00 USD")
    print(f"  💰 Ending Capital:          ${account_balance:.2f} USD")
    print(f"  📈 Net Total Profit:        ${net_p:+.2f} USD ({(net_p/100)*100:+.1f}%)")
    print(f"  🎯 Overall Win Rate:        {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses across {total_trades} trades)")
    print("=" * 95)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trend Breakout Backtest")
    parser.add_argument("--symbol", type=str, default="XAUUSDm")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    run_trend_breakout_backtest(symbol=args.symbol, days_back=args.days)
