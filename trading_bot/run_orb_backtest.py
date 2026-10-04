"""
Dedicated Backtest Engine for Strategy 02:
OPENING RANGE BREAKOUT (ORB) (ES / S&P 500 15-Minute Opening Range)

Specifications:
- Instrument:       ES / S&P 500 (auto-resolves US500m, SPX500, US500, ES, or custom symbol)
- Timeframe:        M5 (5-minute candles)
- Opening Range:    Mark the High and Low of the first 15 minutes after 9:30 AM NY Open (09:30–09:45 AM NY).
- Entry Rules:
    - Go Long on a candle Close above Range High (c_close > range_high).
    - Go Short on a candle Close below Range Low (c_close < range_low).
- Stop Loss:
    - Stop at the opposite side of the range (Long SL = range_low, Short SL = range_high).
- Scale Out & Trailing Management:
    - Scale out HALF position at 1x the range height (TP1 = Entry ± range_height).
    - Trail the remaining half 6 points behind price (Trailing Stop = Peak ± 6.0 pts).
- Trade Constraints:
    - Exactly 1 trade per day.
    - Flat by 4:00 PM New York (any open position closed at market).

Usage:
  python trading_bot/run_orb_backtest.py
  python trading_bot/run_orb_backtest.py --days 30 --symbol US500m --lot 0.1
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from trading_bot.mt5_bridge import MT5Bridge


def run_orb_backtest(
    days: int = 30,
    symbol: str = "ES",
    starting_balance: float = 1000.0,
    lot_size: float = 1.0,
    trail_points: float = 6.0
):
    print("=" * 95, flush=True)
    print("  🚀 OPENING RANGE BREAKOUT (ORB) STRATEGY BACKTEST (ES / M5)", flush=True)
    print("===============================================================================================", flush=True)

    bridge = MT5Bridge(symbol=symbol)
    connected, conn_msg = bridge.connect()
    if not connected:
        print(f"❌ MT5 init failed: {conn_msg}", flush=True)
        return

    # Self-contained symbol resolver (works even if local mt5_bridge is unupdated)
    def local_resolve(sym: str) -> str:
        if hasattr(bridge, "resolve_symbol"):
            try:
                res = bridge.resolve_symbol(sym)
                if res:
                    return res
            except Exception:
                pass
        try:
            import MetaTrader5 as mt5
            all_s = mt5.symbols_get()
            if all_s:
                names = [s.name for s in all_s]
                for n in names:
                    if sym.upper() == n.upper():
                        return n
                if sym.upper() in ["ES", "SPX"]:
                    for n in names:
                        if any(k in n.upper() for k in ["US500", "SPX500", "USA500"]):
                            return n
                if sym.upper() in ["NQ", "NASDAQ"]:
                    for n in names:
                        if any(k in n.upper() for k in ["USTEC", "US100", "NAS100", "TECH100"]):
                            return n
        except Exception:
            pass
        return sym

    resolved_symbol = local_resolve(symbol)

    # Ensure symbol is activated in Market Watch
    try:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(resolved_symbol)
        if info is not None and not info.visible:
            mt5.symbol_select(resolved_symbol, True)
    except Exception:
        pass

    print(f"  📊 Asset:                   {resolved_symbol} (Requested: {symbol})", flush=True)
    print(f"  ⏰ Timeframe:               M5 (5-Minute Candles)", flush=True)
    print(f"  🗽 Opening Range Window:    09:30 AM – 09:45 AM New York Time (First 15 Mins)", flush=True)
    print(f"  🎯 Triggers:                Long on Close > Range High | Short on Close < Range Low", flush=True)
    print(f"  🛡️ SL:                      Opposite Side of Opening Range", flush=True)
    print(f"  💰 Position Scale-Out:      Scale out 50% @ +1x Range Height | Trail 50% @ {trail_points:.1f} pts behind", flush=True)
    print(f"  ⏰ Daily Limit:             1 Trade per day | Flat by 4:00 PM NY", flush=True)
    print(f"  💵 Account Capital:         ${starting_balance:,.2f} USD (Lot Size: {lot_size})", flush=True)
    print("===============================================================================================\n", flush=True)

    bars_needed = (days * 288) + 300
    print(f"⏳ Fetching {bars_needed:,} REAL M5 candles from broker for {resolved_symbol}...", flush=True)

    try:
        data = bridge.fetch_recent_bars(symbol=resolved_symbol, count=bars_needed, timeframe_str="M5")
    except Exception as e:
        print(f"❌ Error fetching M5 candles: {e}", flush=True)
        return

    closes = data["closes"]
    opens = data["opens"]
    highs = data["highs"]
    lows = data["lows"]
    times = data["times"]
    total_bars = len(closes)
    print(f"✅ Loaded {total_bars:,} REAL M5 candles!\n", flush=True)

    if total_bars < 100:
        print("❌ Insufficient candle data.", flush=True)
        return

    sym_info = bridge.get_symbol_info(resolved_symbol)
    contract_size = sym_info.trade_contract_size if sym_info else 1.0
    spread_pts = sym_info.spread_usd if sym_info else 0.5

    ny_tz = ZoneInfo("America/New_York")

    balance = starting_balance
    peak_balance = starting_balance
    max_drawdown_usd = 0.0

    trades: List[Dict[str, Any]] = []
    daily_stats: Dict[str, Dict[str, Any]] = {}

    # Convert timestamps to NY time
    ny_datetimes = []
    for t_raw in times:
        if isinstance(t_raw, str):
            try:
                dt_utc = datetime.fromisoformat(t_raw.replace('Z', '+00:00'))
            except Exception:
                dt_utc = datetime.now(timezone.utc)
        elif isinstance(t_raw, (int, float)):
            dt_utc = datetime.fromtimestamp(t_raw, tz=timezone.utc)
        else:
            dt_utc = t_raw
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        ny_datetimes.append(dt_utc.astimezone(ny_tz))

    # Pre-group indices by trading day
    day_indices: Dict[str, List[int]] = {}
    for idx, dt_ny in enumerate(ny_datetimes):
        d_key = dt_ny.strftime("%Y-%m-%d")
        if d_key not in day_indices:
            day_indices[d_key] = []
        day_indices[d_key].append(idx)

    sorted_days = sorted(day_indices.keys())

    for d_key in sorted_days:
        indices = day_indices[d_key]
        if len(indices) < 20:
            continue

        daily_stats[d_key] = {
            "date": d_key,
            "start_balance": balance,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "pnl": 0.0,
            "end_balance": balance
        }

        # 1. Identify 15-Minute Opening Range (09:30 to 09:45 AM NY = 3 M5 candles)
        orb_indices = [
            i for i in indices
            if (ny_datetimes[i].hour == 9 and ny_datetimes[i].minute in [30, 35, 40])
        ]

        if len(orb_indices) < 2:
            continue

        range_high = max(highs[i] for i in orb_indices)
        range_low = min(lows[i] for i in orb_indices)
        range_height = range_high - range_low

        if range_height <= 0:
            continue

        trade_taken_today = False
        active_pos: Optional[Dict[str, Any]] = None

        # Scan candles after 09:45 AM
        for i in indices:
            dt_ny = ny_datetimes[i]
            c_high = highs[i]
            c_low = lows[i]
            c_close = closes[i]

            # 2. Manage open position
            if active_pos is not None:
                pos = active_pos
                direction = pos["direction"]
                entry_p = pos["entry_price"]
                sl_p = pos["sl"]
                scale_target = pos["scale_target"]
                scaled_out = pos["scaled_out"]
                trail_sl = pos["trail_sl"]

                pos_closed = False
                exit_price = 0.0
                exit_reason = ""

                # Step A: Check Stop Loss
                if direction == "BUY":
                    effective_sl = trail_sl if scaled_out else sl_p
                    if c_low <= effective_sl:
                        exit_price = effective_sl
                        exit_reason = "Trailing SL Hit" if scaled_out else "Range Opposite SL Hit"
                        pos_closed = True
                elif direction == "SELL":
                    effective_sl = trail_sl if scaled_out else sl_p
                    if c_high >= effective_sl:
                        exit_price = effective_sl
                        exit_reason = "Trailing SL Hit" if scaled_out else "Range Opposite SL Hit"
                        pos_closed = True

                # Step B: Check Scale Out (Half Position at 1x Range Height)
                if not pos_closed and not scaled_out:
                    if direction == "BUY" and c_high >= scale_target:
                        pos["scaled_out"] = True
                        scaled_out = True
                        # Bank half position profit
                        half_lot = lot_size / 2.0
                        half_pnl = round((scale_target - entry_p - spread_pts) * half_lot * contract_size, 2)
                        pos["banked_pnl"] += half_pnl
                        balance += half_pnl
                        # Initiate trailing stop at 6 points behind price
                        pos["trail_sl"] = max(entry_p, c_high - trail_points)

                    elif direction == "SELL" and c_low <= scale_target:
                        pos["scaled_out"] = True
                        scaled_out = True
                        half_lot = lot_size / 2.0
                        half_pnl = round((entry_p - scale_target - spread_pts) * half_lot * contract_size, 2)
                        pos["banked_pnl"] += half_pnl
                        balance += half_pnl
                        pos["trail_sl"] = min(entry_p, c_low + trail_points)

                # Step C: Update Trailing Stop for the remaining half
                if not pos_closed and scaled_out:
                    if direction == "BUY":
                        new_trail = c_high - trail_points
                        if new_trail > pos["trail_sl"]:
                            pos["trail_sl"] = new_trail
                    elif direction == "SELL":
                        new_trail = c_low + trail_points
                        if new_trail < pos["trail_sl"]:
                            pos["trail_sl"] = new_trail

                # Step D: Flat by 4:00 PM NY
                if not pos_closed and dt_ny.hour >= 16:
                    exit_price = c_close
                    exit_reason = "4:00 PM NY Flat Exit"
                    pos_closed = True

                # Step E: Finalize full close
                if pos_closed:
                    mult = 1 if direction == "BUY" else -1
                    if scaled_out:
                        # Close remaining 50%
                        rem_lot = lot_size / 2.0
                        rem_pnl = round(((exit_price - entry_p) * mult - spread_pts) * rem_lot * contract_size, 2)
                        total_trade_pnl = pos["banked_pnl"] + rem_pnl
                        balance += rem_pnl
                    else:
                        # Full position closed at initial SL or EOD
                        total_trade_pnl = round(((exit_price - entry_p) * mult - spread_pts) * lot_size * contract_size, 2)
                        balance += total_trade_pnl

                    if balance > peak_balance:
                        peak_balance = balance
                    dd = peak_balance - balance
                    if dd > max_drawdown_usd:
                        max_drawdown_usd = dd

                    trades.append({
                        "date": d_key,
                        "direction": direction,
                        "entry_price": entry_p,
                        "exit_price": exit_price,
                        "pnl": total_trade_pnl,
                        "exit_reason": exit_reason,
                        "entry_time": pos["entry_time"],
                        "exit_time": dt_ny.strftime("%H:%M")
                    })

                    daily_stats[d_key]["trades"] += 1
                    daily_stats[d_key]["pnl"] += total_trade_pnl
                    daily_stats[d_key]["end_balance"] = balance
                    if total_trade_pnl >= 0:
                        daily_stats[d_key]["wins"] += 1
                    else:
                        daily_stats[d_key]["losses"] += 1

                    active_pos = None

            # 3. Check for New Breakout Entry (after 09:45 AM, only 1 trade per day)
            is_post_orb = (dt_ny.hour > 9 or (dt_ny.hour == 9 and dt_ny.minute >= 45)) and (dt_ny.hour < 15)
            if is_post_orb and not trade_taken_today and active_pos is None:
                # Bullish Breakout: Candle Closes Above Range High
                if c_close > range_high:
                    active_pos = {
                        "direction": "BUY",
                        "entry_price": c_close,
                        "sl": range_low,
                        "scale_target": c_close + range_height,
                        "scaled_out": False,
                        "banked_pnl": 0.0,
                        "trail_sl": range_low,
                        "entry_time": dt_ny.strftime("%H:%M")
                    }
                    trade_taken_today = True

                # Bearish Breakout: Candle Closes Below Range Low
                elif c_close < range_low:
                    active_pos = {
                        "direction": "SELL",
                        "entry_price": c_close,
                        "sl": range_high,
                        "scale_target": c_close - range_height,
                        "scaled_out": False,
                        "banked_pnl": 0.0,
                        "trail_sl": range_high,
                        "entry_time": dt_ny.strftime("%H:%M")
                    }
                    trade_taken_today = True

    # Print Table
    print(f"{'Day':<7} | {'Date':<10} | {'Trades':<8} | {'W/L':<8} | {'Daily PnL ($)':<15} | {'Balance ($)':<15} | {'Status'}", flush=True)
    print("-" * 95, flush=True)

    day_count = 1
    total_wins = 0
    total_losses = 0

    for d_key in sorted_days:
        st = daily_stats.get(d_key)
        if not st or st["trades"] == 0:
            continue

        pnl = st["pnl"]
        w = st["wins"]
        l = st["losses"]
        total_wins += w
        total_losses += l

        pnl_str = f"${pnl:+.2f} USD"
        bal_str = f"${st['end_balance']:,.2f} USD"
        status_tag = "🟢 Green Day" if pnl >= 0 else "🔴 Red Day"

        print(f"Day {day_count:<3} | {st['date']} | {st['trades']:<8} | {w}W/{l}L    | {pnl_str:<15} | {bal_str:<15} | {status_tag}", flush=True)
        day_count += 1

    total_trades_count = len(trades)
    win_rate = (total_wins / total_trades_count * 100.0) if total_trades_count > 0 else 0.0
    net_profit = balance - starting_balance
    roi = (net_profit / starting_balance) * 100.0

    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

    print("=" * 95, flush=True)
    print(f"  🏁 OPENING RANGE BREAKOUT (ORB) SUMMARY ({resolved_symbol} | {days} DAYS):", flush=True)
    print("===============================================================================================", flush=True)
    print(f"  💵 Starting Balance:         ${starting_balance:,.2f} USD", flush=True)
    print(f"  💰 Ending Balance:           ${balance:,.2f} USD", flush=True)
    print(f"  📈 Net Total Profit:         ${net_profit:+.2f} USD ({roi:+.1f}% ROI)", flush=True)
    print(f"  🎯 Overall Win Rate:         {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses across {total_trades_count} trades)", flush=True)
    print(f"  ⚖️ Profit Factor:            {profit_factor:.2f}", flush=True)
    print(f"  📉 Maximum Drawdown:         ${max_drawdown_usd:.2f} USD", flush=True)
    print("===============================================================================================\n", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Opening Range Breakout (ORB) Strategy Backtest on MT5 (ES / S&P500)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backtest (default 30)")
    parser.add_argument("--symbol", type=str, default="ES", help="Symbol alias or name (e.g. ES, US500m, SPX500, US500)")
    parser.add_argument("--balance", type=float, default=1000.0, help="Starting account balance in USD (default 1000)")
    parser.add_argument("--lot", type=float, default=1.0, help="Fixed lot size (default 1.0 = $1/pt on US500m)")
    parser.add_argument("--trail-pts", type=float, default=6.0, help="Trailing distance in points behind price (default 6.0)")
    args = parser.parse_args()

    run_orb_backtest(
        days=args.days,
        symbol=args.symbol,
        starting_balance=args.balance,
        lot_size=args.lot,
        trail_points=args.trail_pts
    )
