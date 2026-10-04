"""
Dedicated Backtest Engine for MetaTrader 5:
Strategy: EMA9 + VWAP Cross Strategy (Gold Scalping Adaptation)

Instrument:       XAUUSD (or XAUUSDm)
Timeframe:        M5 (5-minute candles)
Trading Sessions: Asian session (00:00–08:00 server time) + London session (12:00–17:00 server time).
                  All other sessions (London_Pre, NY, Overlap) are excluded based on backtested performance.

Indicators:
- 9-period EMA on Close price
- Session-based VWAP (resets daily at 00:00 server time)
- ATR(14) for protective Stop Loss

Entry Rules:
- Long (Buy):
    1. 9 EMA crosses above VWAP (fresh cross: EMA was at/below VWAP on previous candle)
    2. Current candle Close > 9 EMA
    3. Enter at candle Close price (0.02 fixed lot)
- Short (Sell):
    1. 9 EMA crosses below VWAP (fresh cross: EMA was at/above VWAP on previous candle)
    2. Current candle Close < 9 EMA
    3. Enter at candle Close price (0.02 fixed lot)

Exit Rules:
- Stop-Loss (protective): ATR(14) x 1.5 (or custom --atr-mult) set at time of entry:
    Long: Entry Price - (atr_mult x ATR)
    Short: Entry Price + (atr_mult x ATR)
- Take-Profit / Trend Exit (primary exit mechanism):
    No fixed target — position is held until a reversal signal.
    Exit triggers when a candle's Close moves at least 20% of that candle's own High-Low range beyond the 9 EMA:
    Long exit:  (EMA9 - Close) >= 0.20 x (Candle High - Candle Low)
    Short exit: (Close - EMA9) >= 0.20 x (Candle High - Candle Low)
    Whichever comes first (SL or the reverse-close exit) closes the trade.

Usage:
  python trading_bot/run_ema9_vwap_backtest.py
  python trading_bot/run_ema9_vwap_backtest.py --days 30 --symbol XAUUSDm --atr-mult 1.75
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from trading_bot.mt5_bridge import MT5Bridge
from trading_bot.strategy import (
    calculate_ema,
    calculate_session_vwap,
    calculate_atr,
    is_ema9_vwap_session_active,
    evaluate_trend_exit
)
from trading_bot.news_filter import EconomicNewsFilter


def run_ema9_vwap_backtest(
    days: int = 30,
    symbol: str = "XAUUSDm",
    starting_balance: float = 100.0,
    lot_size: float = 0.02,
    daily_max_loss: float = 0.0,
    max_daily_trades: int = 0,
    max_session_losses: int = 0,
    atr_mult: float = 2.0,
    min_sl: float = 0.0,
    max_ema_gap: float = 0.0,
    breakeven_atr: float = 0.0,
    use_200_ema: bool = False,
    enable_news_shield: bool = True,
    news_freeze_mins: int = 30,
    mt5_path: Optional[str] = None
):
    print("=" * 95, flush=True)
    print("  🏛️  EMA9 + VWAP CROSS STRATEGY (GOLD SCALPING ADAPTATION)", flush=True)
    print("===============================================================================================", flush=True)
    print(f"  📊 Asset:                   {symbol} (M5 Timeframe)", flush=True)
    print(f"  ⏰ Trading Sessions:        Asian (00:00-08:00) & London (12:00-17:00) Server Time", flush=True)
    print(f"  🛑 Excluded Sessions:       London_Pre (08-12), NY & Overlap (17-24)", flush=True)
    print(f"  💰 Account Capital:         ${starting_balance:.2f} USD (Fixed Lot: {lot_size})", flush=True)
    sl_desc = f"{atr_mult} x ATR(14)" if min_sl == 0 else f"{atr_mult} x ATR(14) (Min SL: ${min_sl:.2f})"
    print(f"  🛡️ Protective SL:           {sl_desc} | Exit: 20% Candle Range Beyond EMA9", flush=True)
    if enable_news_shield:
        print(f"  📡 Economic News Shield:    ON (Freeze ±{news_freeze_mins}m around High-Impact USD News)", flush=True)
    else:
        print(f"  📡 Economic News Shield:    OFF (Disabled)", flush=True)
    if use_200_ema:
        print(f"  📈 200 EMA Macro Filter:    ON (Buys strictly above 200 EMA, Sells strictly below)", flush=True)
    if breakeven_atr > 0:
        print(f"  🎯 Breakeven Trigger:       At +{breakeven_atr:.1f} x ATR Profit (Moves SL to Entry + Spread)", flush=True)
    if max_ema_gap > 0:
        print(f"  🛑 Max EMA Gap Filter:      {max_ema_gap:.2f} x ATR (Skips overextended entries)", flush=True)
    if max_daily_trades > 0:
        print(f"  🛑 Max Daily Trades:        {max_daily_trades} Trades/day Max", flush=True)
    if max_session_losses > 0:
        print(f"  🛑 Session Loss Pause:      {max_session_losses} Consecutive Losses halts current session only", flush=True)
    if daily_max_loss > 0:
        print(f"  🛑 Daily SL Block / Shield: -${daily_max_loss:.2f} USD (Trading halted for the day if hit)", flush=True)
    print("===============================================================================================\n", flush=True)

    news_filter = EconomicNewsFilter(
        target_currencies=["USD"],
        freeze_before_mins=news_freeze_mins,
        freeze_after_mins=news_freeze_mins
    )

    bridge = MT5Bridge(symbol=symbol)
    connected, conn_msg = bridge.connect(path=mt5_path if mt5_path else None)
    if not connected:
        print(f"❌ MT5 init failed: {conn_msg}", flush=True)
        return

    # In M5, 1 day ~ 288 candles. For N days, fetch N * 288 + warm up 250
    bars_needed = (days * 288) + 250
    print(f"⏳ Fetching {bars_needed:,} REAL M5 candles from broker for {symbol}...", flush=True)

    try:
        data = bridge.fetch_recent_bars(symbol=symbol, count=bars_needed, timeframe_str="M5")
    except Exception as e:
        print(f"❌ Error fetching M5 candles: {e}", flush=True)
        return

    closes = data["closes"]
    opens = data["opens"]
    highs = data["highs"]
    lows = data["lows"]
    times = data["times"]
    volumes = data["volumes"]

    total_bars = len(closes)
    print(f"✅ Loaded {total_bars:,} REAL M5 candles!\n", flush=True)

    if total_bars < 50:
        print("❌ Insufficient candle data.", flush=True)
        return

    # Compute indicators causally
    ema9_vals = calculate_ema(closes, period=9)
    vwap_vals = calculate_session_vwap(times, highs, lows, closes, volumes, anchor_hour_utc=0)
    atr_vals = calculate_atr(highs, lows, closes, period=14)
    ema200_vals = calculate_ema(closes, period=200)

    # Simulation state
    balance = starting_balance
    peak_balance = starting_balance
    max_drawdown_usd = 0.0

    trades: List[Dict[str, Any]] = []
    active_pos: Optional[Dict[str, Any]] = None

    # Daily aggregation
    daily_stats: Dict[str, Dict[str, Any]] = {}
    shield_triggered_days = 0

    spread_usd = 0.25  # Standard average Exness gold spread ~ $0.25 per oz

    curr_session_name = ""
    session_loss_count = 0

    # Run chronological simulation
    for i in range(1, total_bars):
        t_raw = times[i]
        if isinstance(t_raw, str):
            try:
                dt = datetime.fromisoformat(t_raw.replace('Z', '+00:00'))
            except Exception:
                dt = datetime.utcfromtimestamp(i * 300)
        elif isinstance(t_raw, (int, float)):
            dt = datetime.fromtimestamp(t_raw, tz=timezone.utc)
        else:
            dt = t_raw

        day_key = dt.strftime("%Y-%m-%d")
        if day_key not in daily_stats:
            daily_stats[day_key] = {
                "date": day_key,
                "start_balance": balance,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl": 0.0,
                "end_balance": balance,
                "shield_hit": False
            }

        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]
        c_close = closes[i]
        c_ema9 = ema9_vals[i]
        c_vwap = vwap_vals[i]
        c_atr = atr_vals[i]

        # 1. Evaluate open position
        if active_pos is not None:
            direction = active_pos["direction"]
            entry_p = active_pos["entry_price"]
            sl_p = active_pos["sl"]
            entry_atr = active_pos.get("entry_atr", c_atr)
            pos_closed = False
            exit_p = 0.0
            exit_reason = ""

            # Check Breakeven Protection: If favorable excursion reaches breakeven_atr * ATR, move SL to Entry + Spread
            if breakeven_atr > 0 and not active_pos.get("be_active", False):
                if direction == "BUY":
                    if c_high >= (entry_p + breakeven_atr * entry_atr):
                        be_sl = round(entry_p + spread_usd, 2)
                        if be_sl > sl_p:
                            active_pos["sl"] = be_sl
                            sl_p = be_sl
                            active_pos["be_active"] = True
                elif direction == "SELL":
                    if c_low <= (entry_p - breakeven_atr * entry_atr):
                        be_sl = round(entry_p - spread_usd, 2)
                        if be_sl < sl_p:
                            active_pos["sl"] = be_sl
                            sl_p = be_sl
                            active_pos["be_active"] = True

            # Check Hard Protective Stop-Loss (or Breakeven Stop)
            if direction == "BUY":
                if c_low <= sl_p:
                    exit_p = sl_p
                    exit_reason = "Breakeven (+Spread) Hit" if active_pos.get("be_active") else f"Protective SL Hit ({atr_mult}x ATR)"
                    pos_closed = True
            elif direction == "SELL":
                if c_high >= sl_p:
                    exit_p = sl_p
                    exit_reason = "Breakeven (+Spread) Hit" if active_pos.get("be_active") else f"Protective SL Hit ({atr_mult}x ATR)"
                    pos_closed = True

            # If SL not hit, check Trend Exit rule at candle close
            if not pos_closed:
                should_exit, dist, reason = evaluate_trend_exit(
                    direction=direction,
                    candle_high=c_high,
                    candle_low=c_low,
                    candle_close=c_close,
                    ema9=c_ema9,
                    reverse_range_pct=0.20
                )
                if should_exit:
                    exit_p = c_close
                    exit_reason = reason
                    pos_closed = True

            # Process position close
            if pos_closed:
                mult = 1 if direction == "BUY" else -1
                raw_diff = (exit_p - entry_p) * mult - spread_usd
                pnl = round(raw_diff * lot_size * 100.0, 2)

                balance += pnl
                if balance > peak_balance:
                    peak_balance = balance
                dd = peak_balance - balance
                if dd > max_drawdown_usd:
                    max_drawdown_usd = dd

                trade_record = {
                    "entry_time": active_pos["entry_time"],
                    "exit_time": dt.strftime("%Y-%m-%d %H:%M"),
                    "direction": direction,
                    "entry_price": entry_p,
                    "exit_price": exit_p,
                    "sl": sl_p,
                    "pnl": pnl,
                    "exit_reason": exit_reason,
                    "balance": balance
                }
                trades.append(trade_record)

                daily_stats[day_key]["trades"] += 1
                daily_stats[day_key]["pnl"] += pnl
                daily_stats[day_key]["end_balance"] = balance

                if pnl >= 0:
                    daily_stats[day_key]["wins"] += 1
                else:
                    daily_stats[day_key]["losses"] += 1

                # Check if balance dropped >= daily_max_loss below day start balance
                loss_from_day_start = daily_stats[day_key]["start_balance"] - balance
                if daily_max_loss > 0 and loss_from_day_start >= daily_max_loss:
                    daily_stats[day_key]["shield_hit"] = True

                if pnl < 0:
                    session_loss_count += 1
                else:
                    session_loss_count = 0

                active_pos = None

        # 2. If no position is open, check entry rules
        if active_pos is None:
            # Check Daily SL Block Shield: If balance dropped >= daily_max_loss below today's starting balance
            day_start_bal = daily_stats[day_key]["start_balance"]
            loss_from_day_start = day_start_bal - balance
            if daily_max_loss > 0 and loss_from_day_start >= daily_max_loss:
                daily_stats[day_key]["shield_hit"] = True
                continue

            # Check Max Daily Trades Limit
            if max_daily_trades > 0 and daily_stats[day_key]["trades"] >= max_daily_trades:
                continue

            is_active, session_name = is_ema9_vwap_session_active(dt)
            if is_active:
                if session_name != curr_session_name:
                    curr_session_name = session_name
                    session_loss_count = 0  # New session starts clean!

                # Check Session Consecutive Loss Pause
                if max_session_losses > 0 and session_loss_count >= max_session_losses:
                    continue

                # Check Economic News Shield (Freezes entry during High-Impact USD News)
                if enable_news_shield:
                    is_frozen, news_reason, _ = news_filter.is_news_freeze_active(dt)
                    if is_frozen:
                        continue

                prev_ema9 = ema9_vals[i - 1]
                prev_vwap = vwap_vals[i - 1]
                ema_gap = abs(c_close - c_ema9)

                # Check Overextension Gap filter (skips entry if close is stretched too far from EMA9)
                if max_ema_gap > 0 and (ema_gap > max_ema_gap * c_atr):
                    continue

                # Long (Buy) Entry:
                # 1. 9 EMA crosses above VWAP
                # 2. Candle Close > 9 EMA
                # 3. If use_200_ema: Candle Close > 200 EMA
                if (prev_ema9 <= prev_vwap) and (c_ema9 > c_vwap) and (c_close > c_ema9) and (not use_200_ema or c_close > ema200_vals[i]):
                    sl_dist = max(min_sl, atr_mult * c_atr)
                    sl = round(c_close - sl_dist, 2)
                    active_pos = {
                        "direction": "BUY",
                        "entry_price": c_close,
                        "sl": sl,
                        "entry_atr": c_atr,
                        "be_active": False,
                        "entry_time": dt.strftime("%Y-%m-%d %H:%M"),
                        "session": session_name
                    }

                # Short (Sell) Entry:
                # 1. 9 EMA crosses below VWAP
                # 2. Candle Close < 9 EMA
                # 3. If use_200_ema: Candle Close < 200 EMA
                elif (prev_ema9 >= prev_vwap) and (c_ema9 < c_vwap) and (c_close < c_ema9) and (not use_200_ema or c_close < ema200_vals[i]):
                    sl_dist = max(min_sl, atr_mult * c_atr)
                    sl = round(c_close + sl_dist, 2)
                    active_pos = {
                        "direction": "SELL",
                        "entry_price": c_close,
                        "sl": sl,
                        "entry_atr": c_atr,
                        "be_active": False,
                        "entry_time": dt.strftime("%Y-%m-%d %H:%M"),
                        "session": session_name
                    }

    # Print Table
    print(f"{'Day':<7} | {'Date':<10} | {'Trades':<8} | {'W/L':<8} | {'Daily PnL ($)':<15} | {'Balance ($)':<15} | {'Status'}", flush=True)
    print("-" * 95, flush=True)

    sorted_days = sorted(daily_stats.keys())
    day_count = 1
    total_wins = 0
    total_losses = 0

    for d_key in sorted_days:
        st = daily_stats[d_key]
        if st["trades"] == 0:
            continue

        pnl = st["pnl"]
        w = st["wins"]
        l = st["losses"]
        total_wins += w
        total_losses += l

        pnl_str = f"${pnl:+.2f} USD"
        bal_str = f"${st['end_balance']:,.2f} USD"

        if st["shield_hit"]:
            status_tag = f"🛑 Daily SL Shield (-${daily_max_loss:.0f})"
            shield_triggered_days += 1
        elif pnl >= 0:
            status_tag = "🟢 Green Day"
        else:
            status_tag = "🔴 Red Day"

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
    print(f"  🏁 EMA9 + VWAP CROSS FRAMEWORK SUMMARY ({symbol} | {days} DAYS):", flush=True)
    print("===============================================================================================", flush=True)
    print(f"  💵 Starting Balance:         ${starting_balance:,.2f} USD", flush=True)
    print(f"  💰 Ending Balance:           ${balance:,.2f} USD", flush=True)
    print(f"  📈 Net Total Profit:         ${net_profit:+.2f} USD ({roi:+.1f}% ROI)", flush=True)
    print(f"  🎯 Overall Win Rate:         {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses across {total_trades_count} trades)", flush=True)
    print(f"  ⚖️ Profit Factor:            {profit_factor:.2f}", flush=True)
    print(f"  📉 Maximum Drawdown:         ${max_drawdown_usd:.2f} USD", flush=True)
    if daily_max_loss > 0:
        print(f"  🛡️ Days Shield Triggered:    {shield_triggered_days} Days halted at Daily SL limit (-${daily_max_loss:.2f})", flush=True)
    print("===============================================================================================\n", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run EMA9 + VWAP Cross Strategy Backtest on MT5")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backtest (default: 30)")
    parser.add_argument("--symbol", type=str, default="XAUUSDm", help="Symbol name (e.g. XAUUSDm, XAUUSD)")
    parser.add_argument("--balance", type=float, default=100.0, help="Starting account balance in USD (default: 100)")
    parser.add_argument("--lot", type=float, default=0.02, help="Fixed lot size (default: 0.02)")
    parser.add_argument("--daily-max-loss", type=float, default=0.0, help="Daily Max Loss Block in USD (default 0.0 = disabled, set e.g. 25.0 to enable)")
    parser.add_argument("--max-daily-trades", type=int, default=0, help="Max trades allowed per day (e.g. 3, 0 = unlimited)")
    parser.add_argument("--max-session-losses", type=int, default=0, help="Max consecutive losses before pausing current session (e.g. 2, 0 = unlimited)")
    parser.add_argument("--atr-mult", type=float, default=2.0, help="ATR SL multiplier (default 2.0, e.g. 1.5 or 2.0)")
    parser.add_argument("--min-sl", type=float, default=0.0, help="Minimum Stop Loss in USD (default 0.0, e.g. 2.5)")
    parser.add_argument("--max-ema-gap", type=float, default=0.0, help="Max allowed gap between Close and EMA9 in ATR units (e.g. 1.0 to skip overextensions, default 0.0 = disabled)")
    parser.add_argument("--breakeven-atr", type=float, default=0.0, help="Move SL to Breakeven (+Spread) when profit reaches N x ATR (e.g. 1.5 or 2.0, default 0.0 = disabled)")
    parser.add_argument("--use-200-ema", action="store_true", help="Filter entries with 200 EMA (Buys strictly above 200 EMA, Sells strictly below)")
    parser.add_argument("--no-news", action="store_true", help="Disable economic news shield")
    parser.add_argument("--news-freeze-mins", type=int, default=30, help="Minutes to freeze before and after high-impact USD events (default: 30)")
    parser.add_argument("--mt5-path", type=str, default="", help="Path to specific MT5 terminal64.exe (e.g. 'C:\\Program Files\\MetaTrader 5 - Bot2\\terminal64.exe')")
    args = parser.parse_args()

    run_ema9_vwap_backtest(
        days=args.days,
        symbol=args.symbol,
        starting_balance=args.balance,
        lot_size=args.lot,
        daily_max_loss=args.daily_max_loss,
        max_daily_trades=args.max_daily_trades,
        max_session_losses=args.max_session_losses,
        atr_mult=args.atr_mult,
        min_sl=args.min_sl,
        max_ema_gap=args.max_ema_gap,
        breakeven_atr=args.breakeven_atr,
        use_200_ema=args.use_200_ema,
        enable_news_shield=not args.no_news,
        news_freeze_mins=args.news_freeze_mins,
        mt5_path=args.mt5_path if args.mt5_path.strip() else None
    )
