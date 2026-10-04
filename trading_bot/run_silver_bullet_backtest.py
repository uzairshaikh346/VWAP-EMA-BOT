"""
Dedicated Backtest Engine for Strategy 01:
THE SILVER BULLET (ICT 10:00–11:00 AM New York Session)

Specifications:
- Instrument:       NQ / Nasdaq 100 (auto-resolves USTECm, US100m, NAS100, NQ, or custom symbol)
- Timeframe:        M5 (5-minute candles)
- Trading Window:   10:00 AM – 11:00 AM New York Time (EST/EDT)
- Core Mechanism:
    1. Identify Prior Session High/Low (London / Pre-Market Liquidity Pool: 03:00–09:30 AM NY).
    2. Wait for a Liquidity Sweep:
       - Bullish: Price trades below Prior Session Low (Sell-Side Liquidity grab).
       - Bearish: Price trades above Prior Session High (Buy-Side Liquidity grab).
    3. Look for a 3-candle Fair Value Gap (FVG) in the opposite direction inside/around the 10-11am window.
    4. Rest a Limit Order at the gap's midpoint (Consequent Encroachment = 50% FVG).
    5. Fill on touch when price retraces into the midpoint.
    6. Stop Loss: Just past the sweep extreme.
    7. Take Profit: Opposing session liquidity (Prior High for Long, Prior Low for Short).
    8. Limit: Strictly 1 trade per day.

Usage:
  python trading_bot/run_silver_bullet_backtest.py
  python trading_bot/run_silver_bullet_backtest.py --days 30 --symbol USTECm --lot 0.1
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


def run_silver_bullet_backtest(
    days: int = 30,
    symbol: str = "NQ",
    starting_balance: float = 1000.0,
    lot_size: float = 1.0
):
    print("=" * 95, flush=True)
    print("  ⚡ ICT THE SILVER BULLET STRATEGY BACKTEST (NQ / M5)", flush=True)
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
                if sym.upper() in ["NQ", "NASDAQ"]:
                    for n in names:
                        if any(k in n.upper() for k in ["USTEC", "US100", "NAS100", "TECH100"]):
                            return n
                if sym.upper() in ["ES", "SPX"]:
                    for n in names:
                        if any(k in n.upper() for k in ["US500", "SPX500", "USA500"]):
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
    print(f"  🗽 Trading Window:          10:00 AM – 11:00 AM New York Time", flush=True)
    print(f"  🎯 Setup:                   Prior Session Sweep -> FVG in Opposite Direction -> 50% Midpoint Limit", flush=True)
    print(f"  🛡️ SL / TP:                 SL Past Sweep | TP at Opposing Session Liquidity", flush=True)
    print(f"  💰 Account Capital:         ${starting_balance:,.2f} USD (Lot Size: {lot_size})", flush=True)
    print("===============================================================================================\n", flush=True)

    # In M5, 1 day has ~288 bars. For N days fetch N * 288 + 300 warm-up bars
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
    spread_pts = sym_info.spread_usd if sym_info else 1.0

    ny_tz = ZoneInfo("America/New_York")

    # Simulation state
    balance = starting_balance
    peak_balance = starting_balance
    max_drawdown_usd = 0.0

    trades: List[Dict[str, Any]] = []
    active_pos: Optional[Dict[str, Any]] = None
    pending_limit: Optional[Dict[str, Any]] = None

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

    # Process day by day
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

        # 1. Identify Prior Session Range (London / Pre-Market: 03:00 to 09:30 AM NY)
        premarket_indices = [
            i for i in indices
            if (ny_datetimes[i].hour > 3 or (ny_datetimes[i].hour == 3 and ny_datetimes[i].minute >= 0))
            and (ny_datetimes[i].hour < 9 or (ny_datetimes[i].hour == 9 and ny_datetimes[i].minute <= 30))
        ]

        if len(premarket_indices) < 5:
            continue

        prior_high = max(highs[i] for i in premarket_indices)
        prior_low = min(lows[i] for i in premarket_indices)

        swept_low = False
        sweep_low_price = prior_low
        swept_high = False
        sweep_high_price = prior_high

        trade_taken_today = False
        pending_limit = None

        for i in indices:
            dt_ny = ny_datetimes[i]
            c_high = highs[i]
            c_low = lows[i]
            c_close = closes[i]

            # Check if active position closes
            if active_pos is not None:
                pos = active_pos
                closed = False
                exit_price = 0.0
                exit_reason = ""

                if pos["direction"] == "BUY":
                    if c_low <= pos["sl"]:
                        exit_price = pos["sl"]
                        exit_reason = "SL Hit"
                        closed = True
                    elif c_high >= pos["tp"]:
                        exit_price = pos["tp"]
                        exit_reason = "TP Hit (Opposing Liquidity)"
                        closed = True
                elif pos["direction"] == "SELL":
                    if c_high >= pos["sl"]:
                        exit_price = pos["sl"]
                        exit_reason = "SL Hit"
                        closed = True
                    elif c_low <= pos["tp"]:
                        exit_price = pos["tp"]
                        exit_reason = "TP Hit (Opposing Liquidity)"
                        closed = True

                # End of day close (flat before close of session)
                if not closed and dt_ny.hour >= 16:
                    exit_price = c_close
                    exit_reason = "EOD Square-Off"
                    closed = True

                if closed:
                    mult = 1 if pos["direction"] == "BUY" else -1
                    raw_diff = (exit_price - pos["entry_price"]) * mult - spread_pts
                    pnl = round(raw_diff * lot_size * contract_size, 2)

                    balance += pnl
                    if balance > peak_balance:
                        peak_balance = balance
                    dd = peak_balance - balance
                    if dd > max_drawdown_usd:
                        max_drawdown_usd = dd

                    trades.append({
                        "date": d_key,
                        "direction": pos["direction"],
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "exit_reason": exit_reason,
                        "entry_time": pos["entry_time"],
                        "exit_time": dt_ny.strftime("%H:%M")
                    })

                    daily_stats[d_key]["trades"] += 1
                    daily_stats[d_key]["pnl"] += pnl
                    daily_stats[d_key]["end_balance"] = balance
                    if pnl >= 0:
                        daily_stats[d_key]["wins"] += 1
                    else:
                        daily_stats[d_key]["losses"] += 1

                    active_pos = None

            # Detect Liquidity Sweeps (between 09:30 AM and 11:00 AM NY)
            if (dt_ny.hour == 9 and dt_ny.minute >= 30) or (dt_ny.hour == 10):
                if c_low < prior_low:
                    swept_low = True
                    sweep_low_price = min(sweep_low_price, c_low)
                if c_high > prior_high:
                    swept_high = True
                    sweep_high_price = max(sweep_high_price, c_high)

            # Check if pending limit order is filled on touch
            if pending_limit is not None and active_pos is None:
                pl = pending_limit
                limit_p = pl["limit_price"]
                filled = False

                if pl["direction"] == "BUY" and c_low <= limit_p:
                    filled = True
                elif pl["direction"] == "SELL" and c_high >= limit_p:
                    filled = True

                if filled:
                    active_pos = {
                        "direction": pl["direction"],
                        "entry_price": limit_p,
                        "sl": pl["sl"],
                        "tp": pl["tp"],
                        "entry_time": dt_ny.strftime("%H:%M")
                    }
                    pending_limit = None
                    trade_taken_today = True

                # Expire limit if past 11:30 AM NY without touch
                elif dt_ny.hour > 11 or (dt_ny.hour == 11 and dt_ny.minute >= 30):
                    pending_limit = None

            # Look for Silver Bullet Setup inside 10:00 AM - 11:00 AM New York
            is_silver_bullet_window = (dt_ny.hour == 10)
            if is_silver_bullet_window and not trade_taken_today and active_pos is None and pending_limit is None:
                # 3-candle Fair Value Gap detection (i-2, i-1, i)
                if i >= 2:
                    c1_h = highs[i - 2]
                    c1_l = lows[i - 2]
                    c3_h = highs[i]
                    c3_l = lows[i]

                    # Bullish FVG after sweeping prior low: C1 High < C3 Low
                    if swept_low and (c3_l > c1_h):
                        fvg_gap = c3_l - c1_h
                        if fvg_gap >= 2.0:  # Reasonable FVG size on NQ
                            fvg_mid = round((c1_h + c3_l) / 2.0, 2)
                            sl_level = round(sweep_low_price - 2.0, 2)
                            tp_level = round(prior_high, 2)
                            if tp_level > fvg_mid and fvg_mid > sl_level:
                                pending_limit = {
                                    "direction": "BUY",
                                    "limit_price": fvg_mid,
                                    "sl": sl_level,
                                    "tp": tp_level
                                }

                    # Bearish FVG after sweeping prior high: C1 Low > C3 High
                    elif swept_high and (c3_h < c1_l):
                        fvg_gap = c1_l - c3_h
                        if fvg_gap >= 2.0:  # Reasonable FVG size on NQ
                            fvg_mid = round((c1_l + c3_h) / 2.0, 2)
                            sl_level = round(sweep_high_price + 2.0, 2)
                            tp_level = round(prior_low, 2)
                            if tp_level < fvg_mid and fvg_mid < sl_level:
                                pending_limit = {
                                    "direction": "SELL",
                                    "limit_price": fvg_mid,
                                    "sl": sl_level,
                                    "tp": tp_level
                                }

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
    print(f"  🏁 THE SILVER BULLET SUMMARY ({resolved_symbol} | {days} DAYS):", flush=True)
    print("===============================================================================================", flush=True)
    print(f"  💵 Starting Balance:         ${starting_balance:,.2f} USD", flush=True)
    print(f"  💰 Ending Balance:           ${balance:,.2f} USD", flush=True)
    print(f"  📈 Net Total Profit:         ${net_profit:+.2f} USD ({roi:+.1f}% ROI)", flush=True)
    print(f"  🎯 Overall Win Rate:         {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses across {total_trades_count} trades)", flush=True)
    print(f"  ⚖️ Profit Factor:            {profit_factor:.2f}", flush=True)
    print(f"  📉 Maximum Drawdown:         ${max_drawdown_usd:.2f} USD", flush=True)
    print("===============================================================================================\n", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ICT The Silver Bullet Strategy Backtest on MT5 (NQ / Nasdaq)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backtest (default 30)")
    parser.add_argument("--symbol", type=str, default="NQ", help="Symbol alias or name (e.g. NQ, USTECm, US100, NAS100)")
    parser.add_argument("--balance", type=float, default=1000.0, help="Starting account balance in USD (default 1000)")
    parser.add_argument("--lot", type=float, default=1.0, help="Fixed lot size (default 1.0 = $1/pt on USTECm)")
    args = parser.parse_args()

    run_silver_bullet_backtest(
        days=args.days,
        symbol=args.symbol,
        starting_balance=args.balance,
        lot_size=args.lot
    )
