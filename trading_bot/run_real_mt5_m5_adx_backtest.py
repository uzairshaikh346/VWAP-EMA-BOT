"""
M5 INSTITUTIONAL TREND + ADX FILTER STRATEGY FOR REAL MT5 DATA
Tests Gold on M5 Timeframe with ADX Trend Strength Filter + Proper SL Buffer.
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


def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    n = len(closes)
    if n < (2 * period + 1):
        return [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    smooth_tr = [0.0] * n
    smooth_pdm = [0.0] * n
    smooth_mdm = [0.0] * n
    smooth_tr[period] = sum(tr[1:period + 1])
    smooth_pdm[period] = sum(plus_dm[1:period + 1])
    smooth_mdm[period] = sum(minus_dm[1:period + 1])
    for i in range(period + 1, n):
        smooth_tr[i] = smooth_tr[i - 1] - (smooth_tr[i - 1] / period) + tr[i]
        smooth_pdm[i] = smooth_pdm[i - 1] - (smooth_pdm[i - 1] / period) + plus_dm[i]
        smooth_mdm[i] = smooth_mdm[i - 1] - (smooth_mdm[i - 1] / period) + minus_dm[i]
    dx = [0.0] * n
    for i in range(period, n):
        if smooth_tr[i] > 0:
            pdi = 100.0 * (smooth_pdm[i] / smooth_tr[i])
            mdi = 100.0 * (smooth_mdm[i] / smooth_tr[i])
            di_sum = pdi + mdi
            if di_sum > 0:
                dx[i] = 100.0 * abs(pdi - mdi) / di_sum
    adx = [0.0] * n
    start_adx = (2 * period) - 1
    if start_adx < n:
        adx[start_adx] = sum(dx[period:start_adx + 1]) / period
        for i in range(start_adx + 1, n):
            adx[i] = ((adx[i - 1] * (period - 1)) + dx[i]) / period
    return adx


def calculate_session_vwap(times: List[str], highs: List[float], lows: List[float], closes: List[float], volumes: List[float], anchor_hour_utc: int = 0) -> List[float]:
    n = len(closes)
    vwap = [0.0] * n
    cum_pv = 0.0
    cum_vol = 0.0
    current_day = -1
    for i in range(n):
        try:
            bar_dt = datetime.fromisoformat(times[i])
        except Exception:
            bar_dt = datetime.now(timezone.utc)
        if bar_dt.day != current_day and bar_dt.hour >= anchor_hour_utc:
            current_day = bar_dt.day
            cum_pv = 0.0
            cum_vol = 0.0
        typ_price = (highs[i] + lows[i] + closes[i]) / 3.0
        vol = volumes[i] if volumes[i] > 0 else 1.0
        cum_pv += typ_price * vol
        cum_vol += vol
        vwap[i] = (cum_pv / cum_vol) if cum_vol > 0 else typ_price
    return vwap


def is_golden_session(hour_utc: int) -> bool:
    """London & NY High-Volume Zones (07:00-11:00 UTC and 13:00-19:00 UTC)"""
    return (7 <= hour_utc < 12) or (13 <= hour_utc < 19)


def run_m5_adx_real_backtest(
    symbol: str = "XAUUSDm",
    days_back: int = 30,
    lot_size: float = 0.01,
    min_adx: float = 20.0,
    rr_ratio: float = 1.50,
    daily_profit_target_usd: float = 10.0,
    daily_loss_limit_usd: float = 10.0,
    enable_daily_profit_lock: bool = True,
    spread_points: float = 0.25,
    commission_per_lot_usd: float = 7.0
):
    print("=" * 95)
    print(f"  🏛️  M5 INSTITUTIONAL TREND + ADX CHOP FILTER — REAL MT5 DATA")
    print("=" * 95)
    print(f"  📊 Timeframe:               M5 (5-Minute Candles)")
    print(f"  📅 Historical Period:       {days_back} Days (Real Broker Data)")
    print(f"  💰 Account Capital:         $100.00 USD (0.01 Lot)")
    print(f"  🛡️ ADX Chop Shield:         ADX >= {min_adx} (Blocks sideways chop days)")
    print(f"  🎯 Risk:Reward Ratio:       1:{rr_ratio:.2f} with Dynamic 60% Break-Even Shield")
    print(f"  🛑 Daily Max Loss Shield:   -${daily_loss_limit_usd:.2f} USD (Strict Capital Protection)")
    print("=" * 95)

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("❌ MetaTrader5 python package not installed! Please run: pip install MetaTrader5", flush=True)
        return

    if not mt5.initialize():
        print(f"❌ MT5 initialization failed! Error: {mt5.last_error()}", flush=True)
        return

    selected_symbol = symbol
    if not mt5.symbol_select(selected_symbol, True):
        alt = "XAUUSD" if "m" in symbol else "XAUUSDm"
        if mt5.symbol_select(alt, True):
            selected_symbol = alt
        else:
            print(f"❌ Symbol {symbol} / {alt} not found in MT5 Market Watch!", flush=True)
            mt5.shutdown()
            return

    target_bars = days_back * 288
    print(f"\n⏳ Fetching up to {target_bars:,} REAL M5 historical candles from broker for {selected_symbol}...", flush=True)

    rates = mt5.copy_rates_from_pos(selected_symbol, mt5.TIMEFRAME_M5, 0, target_bars)
    if rates is None or len(rates) == 0:
        utc_to = datetime.now()
        utc_from = utc_to - timedelta(days=days_back)
        rates = mt5.copy_rates_range(selected_symbol, mt5.TIMEFRAME_M5, utc_from, utc_to)

    mt5.shutdown()

    if rates is None or len(rates) == 0:
        print("❌ No rates returned from MT5! Make sure your broker chart is open.", flush=True)
        return

    num_bars = len(rates)
    print(f"✅ Successfully loaded {num_bars:,} REAL M5 candles from broker server!\n", flush=True)

    opens = [float(r['open']) for r in rates]
    highs = [float(r['high']) for r in rates]
    lows = [float(r['low']) for r in rates]
    closes = [float(r['close']) for r in rates]
    times_int = [int(r['time']) for r in rates]
    times_str = [datetime.fromtimestamp(t, tz=timezone.utc).isoformat() for t in times_int]
    volumes = [float(r['tick_volume']) for r in rates]

    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    ema200 = calculate_ema(closes, 150)
    atrs = calculate_atr(highs, lows, closes, 14)
    adx_vals = calculate_adx(highs, lows, closes, 14)
    vwap = calculate_session_vwap(times_str, highs, lows, closes, volumes, 0)

    min_warmup = 160
    trades: List[Dict[str, Any]] = []
    active_trade: Optional[Dict[str, Any]] = None
    comm_per_trade = (commission_per_lot_usd * lot_size) + (spread_points * lot_size * 100)

    days_data: Dict[str, Dict[str, Any]] = {}
    last_loss_bar_index = -9999

    for i in range(min_warmup, num_bars - 1):
        bar_dt = datetime.fromtimestamp(times_int[i], tz=timezone.utc)
        bar_hour = bar_dt.hour
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

            # Dynamic Break-Even Shield at 60%
            if not active_trade["is_be_activated"]:
                if direction == "BUY":
                    be_trigger = entry_p + (tp_p - entry_p) * 0.60
                    if curr_high >= be_trigger:
                        active_trade["sl"] = entry_p + spread_points
                        active_trade["is_be_activated"] = True
                elif direction == "SELL":
                    be_trigger = entry_p - (entry_p - tp_p) * 0.60
                    if curr_low <= be_trigger:
                        active_trade["sl"] = entry_p - spread_points
                        active_trade["is_be_activated"] = True

            sl_p = active_trade["sl"]
            exit_trade = False
            exit_price = 0.0
            exit_reason = ""

            if direction == "BUY":
                if curr_low <= sl_p:
                    exit_trade = True
                    exit_price = sl_p
                    exit_reason = "BE_STOP" if active_trade["is_be_activated"] else "SL"
                elif curr_high >= tp_p:
                    exit_trade = True
                    exit_price = tp_p
                    exit_reason = "TP"
            elif direction == "SELL":
                if curr_high >= sl_p:
                    exit_trade = True
                    exit_price = sl_p
                    exit_reason = "BE_STOP" if active_trade["is_be_activated"] else "SL"
                elif curr_low <= tp_p:
                    exit_trade = True
                    exit_price = tp_p
                    exit_reason = "TP"

            if exit_trade:
                points_diff = (exit_price - entry_p) if direction == "BUY" else (entry_p - exit_price)
                gross_pnl = points_diff * lot_size * 100
                net_pnl = gross_pnl - comm_per_trade

                active_trade["exit_price"] = exit_price
                active_trade["exit_bar"] = i
                active_trade["exit_reason"] = exit_reason
                active_trade["net_pnl"] = net_pnl
                active_trade["is_win"] = net_pnl > 0

                trades.append(active_trade)
                days_data[t_day_key]["trades"].append(active_trade)
                days_data[t_day_key]["realized_pnl"] += net_pnl

                if net_pnl < 0:
                    last_loss_bar_index = i

                if days_data[t_day_key]["realized_pnl"] <= -daily_loss_limit_usd:
                    days_data[t_day_key]["is_halted"] = True
                    days_data[t_day_key]["halt_reason"] = "🛑 Daily Loss Shield (-$10 Stop)"

                if enable_daily_profit_lock and days_data[t_day_key]["realized_pnl"] >= daily_profit_target_usd:
                    days_data[t_day_key]["is_halted"] = True
                    days_data[t_day_key]["halt_reason"] = "🎯 Daily Profit Target (+ $10 Lock)"

                active_trade = None

        # 2. Check for New Entry
        if active_trade is None:
            if days_data[day_key]["is_halted"]:
                continue

            # Limit to 2 trades max per day to eliminate overtrading
            if len(days_data[day_key]["trades"]) >= 2:
                continue

            if not is_golden_session(bar_hour):
                continue

            if (i - last_loss_bar_index) < 3:
                continue

            c_close = closes[i]
            c_open = opens[i]
            c_high = highs[i]
            c_low = lows[i]
            e20 = ema20[i]
            e50 = ema50[i]
            e200 = ema200[i]
            v = vwap[i]
            atr_val = atrs[i] if atrs[i] > 0 else 1.2
            curr_adx = adx_vals[i]

            # ADX Chop Filter (Only trade when market has real momentum)
            if curr_adx < min_adx:
                continue

            action = None
            sl_price = 0.0

            # LONG:
            if e20 > e50 and e50 > e200 and c_close > v:
                pullback = any(lows[i - k] <= (ema20[i - k] + 0.4 * atr_val) for k in range(3))
                if pullback and c_close > c_open and c_close > e20:
                    action = "BUY"
                    recent_low = min(lows[i - 3:i + 1])
                    sl_price = recent_low - (0.8 * atr_val)

            # SHORT:
            elif e20 < e50 and e50 < e200 and c_close < v:
                pullback = any(highs[i - k] >= (ema20[i - k] - 0.4 * atr_val) for k in range(3))
                if pullback and c_close < c_open and c_close < e20:
                    action = "SELL"
                    recent_high = max(highs[i - 3:i + 1])
                    sl_price = recent_high + (0.8 * atr_val)

            if action is not None:
                entry_fill_price = opens[i + 1]
                if action == "BUY":
                    entry_fill_price += spread_points

                risk_distance = abs(entry_fill_price - sl_price)
                if risk_distance < 2.5:
                    risk_distance = 2.5
                elif risk_distance > 5.5:
                    risk_distance = 5.5

                if action == "BUY":
                    real_sl = entry_fill_price - risk_distance
                    real_tp = entry_fill_price + (risk_distance * rr_ratio)
                else:
                    real_sl = entry_fill_price + risk_distance
                    real_tp = entry_fill_price - (risk_distance * rr_ratio)

                active_trade = {
                    "entry_bar": i + 1,
                    "entry_time": times_str[i + 1],
                    "day_key": day_key,
                    "direction": action,
                    "entry_price": entry_fill_price,
                    "sl": real_sl,
                    "tp": real_tp,
                    "is_be_activated": False
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
    print(f"  🏁 REAL BROKER BACKTEST SUMMARY ({selected_symbol} | M5 + ADX | {days_back} DAYS):")
    print("=" * 95)
    print(f"  💵 Starting Balance:         $100.00 USD")
    print(f"  💰 Ending Balance:           ${account_balance:.2f} USD")
    print(f"  📈 Net Total Profit:         ${net_profit:+.2f} USD ({roi:+.1f}% ROI)")
    print(f"  🎯 Overall Win Rate:         {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses across {total_trades} trades)")
    print(f"  🏆 Days Target Locked:       {target_lock_days} Days locked at +$10.00 Target")
    print(f"  🛡️ Days Loss Shielded:       {loss_shield_days} Days protected at -$10.00 Max Loss")
    print("=" * 95)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real MT5 M5+ADX Backtest")
    parser.add_argument("--symbol", type=str, default="XAUUSDm", help="Symbol in MT5 (e.g. XAUUSDm, XAUUSD)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backtest")
    parser.add_argument("--adx", type=float, default=22.0, help="Minimum ADX Trend threshold")
    parser.add_argument("--rr", type=float, default=1.5, help="Risk:Reward ratio")
    args = parser.parse_args()

    run_m5_adx_real_backtest(
        symbol=args.symbol,
        days_back=args.days,
        min_adx=args.adx,
        rr_ratio=args.rr
    )
