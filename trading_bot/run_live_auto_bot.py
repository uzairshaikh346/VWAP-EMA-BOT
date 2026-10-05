"""
Autonomous Execution Engine for MT5:
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
- Stop-Loss (protective): ATR(14) x 1.5 set at time of entry:
    Long: Entry Price - (1.5 x ATR)
    Short: Entry Price + (1.5 x ATR)
- Take-Profit / Trend Exit (primary exit mechanism):
    No fixed target — position is held until a reversal signal.
    Exit triggers when a candle's Close moves at least 20% of that candle's own High-Low range beyond the 9 EMA:
    Long exit:  (EMA9 - Close) >= 0.20 x (Candle High - Candle Low)
    Short exit: (Close - EMA9) >= 0.20 x (Candle High - Candle Low)
    Whichever comes first (SL or the reverse-close exit) closes the trade.

Position Sizing:
- Lot size: 0.02 (fixed)
- Contract size: 100 oz (standard XAUUSD)
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

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
from trading_bot.storage import BotStorage


def run_live_auto_trading(
    symbol: str = "XAUUSDm",
    enable_news_shield: bool = True,
    daily_max_loss: float = 0.0,
    max_daily_trades: int = 0,
    max_session_losses: int = 0,
    atr_mult: float = 2.0,
    min_sl: float = 0.0,
    max_ema_gap: float = 0.0,
    max_candle_range: float = 0.0,
    breakeven_atr: float = 0.0,
    use_200_ema: bool = False,
    trigger_mode: str = "ema_cross",
    lot: float = 0.02,
    mt5_path: Optional[str] = None,
    magic_number: int = 9050201,
    login: Optional[int] = None,
    server: Optional[str] = None,
    password: Optional[str] = None
):
    print("=" * 95, flush=True)
    print("🚀 STARTING LIVE AUTONOMOUS ENGINE: EMA9 + VWAP CROSS STRATEGY (GOLD SCALPING)", flush=True)
    print(f"📊 Instrument: {symbol} | Timeframe: M5 | Lot Size: {lot} | Magic: {magic_number}", flush=True)
    if mt5_path:
        print(f"🖥️ Targeted MT5 Terminal: {mt5_path}", flush=True)
    if login:
        print(f"👤 Targeted Account: #{login} (Server: {server or 'Current'})", flush=True)
    trigger_desc = "Candle crosses VWAP (Aligned with EMA9)" if trigger_mode == "candle_vwap_cross" else "9 EMA crosses VWAP (Aligned with Candle)"
    print(f"🎯 Entry Mode: {trigger_desc}", flush=True)
    print("⏰ Trading Sessions: Asian (00:00–08:00) + London (12:00–17:00) Server Time", flush=True)
    sl_desc = f"{atr_mult} x ATR(14)" if min_sl == 0 else f"{atr_mult} x ATR(14) (Min SL: ${min_sl:.2f})"
    print(f"🛡️ Exits: Hard SL = {sl_desc} | Trend Reversal Exit = 20% candle range beyond EMA9", flush=True)
    if use_200_ema:
        print(f"📈 200 EMA Macro Filter: ON (Buys strictly above 200 EMA, Sells strictly below)", flush=True)
    if breakeven_atr > 0:
        print(f"🛡️ Breakeven Level: +{breakeven_atr:.1f} x ATR Profit (Moves SL to Entry + Spread)", flush=True)
    if max_ema_gap > 0:
        print(f"🛑 Max EMA Gap Filter: {max_ema_gap:.2f} x ATR (Skips overextended entries)", flush=True)
    if max_candle_range > 0:
        print(f"🛑 Giant Candle Filter: {max_candle_range:.2f} x ATR (Skips climax spike candles)", flush=True)
    if max_daily_trades > 0:
        print(f"🛑 Max Daily Trades: {max_daily_trades} Trades/day Max", flush=True)
    if max_session_losses > 0:
        print(f"🛑 Session Loss Pause: {max_session_losses} Consecutive Losses halts current session only", flush=True)
    if daily_max_loss > 0:
        print(f"🛑 Daily SL Block / Shield: -${daily_max_loss:.2f} USD (New entries blocked if hit today)", flush=True)
    print("=" * 95, flush=True)

    storage = BotStorage()
    mt5_bridge = MT5Bridge(symbol=symbol, magic_number=magic_number)

    news_filter = EconomicNewsFilter(target_currencies=["USD"], freeze_before_mins=30, freeze_after_mins=30)
    if enable_news_shield:
        print("📡 Fetching High-Impact Economic News Calendar (ForexFactory)...", flush=True)
        try:
            news_filter.fetch_calendar_events()
            next_ev = news_filter.get_next_upcoming_event()
            if next_ev:
                print(f"📅 Next High-Impact USD News: '{next_ev['title']}' at {next_ev['time_utc'].strftime('%Y-%m-%d %H:%M UTC')}", flush=True)
            else:
                print("📅 No immediate High-Impact USD events in calendar window.", flush=True)
        except Exception as e:
            print(f"⚠️ Could not load news calendar ({e}); running with price-action safety.", flush=True)

    ok, conn_msg = mt5_bridge.connect(
        path=mt5_path if mt5_path else None,
        login=login,
        server=server,
        password=password
    )
    if not ok:
        print(f"❌ Could not connect to MetaTrader 5 terminal: {conn_msg}", flush=True)
        return

    acc = mt5_bridge.get_account_info()
    algo_allowed = mt5_bridge.is_algo_trading_enabled()
    day_start_balance = acc.balance
    current_day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"✅ Connected to MT5 Account: {acc.login} | Mode: {acc.trade_mode} | Balance: ${acc.balance:,.2f}", flush=True)
    print(f"⚡ Target Symbol: {mt5_bridge.symbol} | Default Lot: 0.02 | Algo Allowed: {algo_allowed}", flush=True)
    print(f"🌅 Day Start Balance: ${day_start_balance:,.2f} USD", flush=True)
    print("⚡ Auto-Scanner active. Streaming live ticks and monitoring M5 candles...\n", flush=True)

    last_evaluated_bar_time = None
    last_shield_print_time = 0
    processed_deal_tickets = set()
    today_realized_pnl = 0.0
    today_trades_count = 0
    current_session_str = ""
    session_consecutive_losses = 0

    try:
        while True:
            time.sleep(3)

            # Check new day transition to reset Day Start Balance and trade count
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if today_str != current_day_str:
                current_day_str = today_str
                today_trades_count = 0
                fresh_acc = mt5_bridge.get_account_info()
                if fresh_acc:
                    day_start_balance = fresh_acc.balance
                print(f"\n🌅 [NEW TRADING DAY: {today_str}] Day Start Balance: ${day_start_balance:,.2f} USD", flush=True)

            # 1. Fetch live open positions
            open_positions = mt5_bridge.get_open_positions()

            # 2. Track any closed deals today for accurate reporting
            if hasattr(mt5_bridge, "get_closed_deals"):
                today_midnight_utc = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
                closed_deals = mt5_bridge.get_closed_deals(from_timestamp=today_midnight_utc)
                today_realized_pnl = sum(d["profit"] for d in closed_deals)
                for deal in closed_deals:
                    ticket = deal["ticket"]
                    pnl = deal["profit"]
                    if ticket not in processed_deal_tickets:
                        processed_deal_tickets.add(ticket)
                        exit_p = deal["close_price"]
                        try:
                            storage.update_closed_trade(ticket, exit_p, pnl, exit_reason="MT5 Deal Closed")
                        except Exception as e:
                            print(f"⚠️ Storage update warning: {e}", flush=True)
                        if pnl >= 0:
                            session_consecutive_losses = 0
                            print(f"🎉 [TRADE CLOSED - WIN] Deal #{ticket} closed at +${pnl:.2f} profit! Today's Net: ${today_realized_pnl:+.2f}", flush=True)
                        else:
                            session_consecutive_losses += 1
                            print(f"⚠️ [TRADE CLOSED - LOSS] Deal #{ticket} closed at -${abs(pnl):.2f}. Session Losses: {session_consecutive_losses}. Today's Net: ${today_realized_pnl:+.2f}", flush=True)

            # 3. Fetch recent M5 bars
            try:
                bars_dict = mt5_bridge.fetch_recent_bars(symbol=symbol, count=150, timeframe_str="M5")
            except Exception as e:
                print(f"⚠️ Error fetching M5 bars: {e}", flush=True)
                continue

            closes = bars_dict["closes"]
            opens = bars_dict.get("opens", [])
            highs = bars_dict["highs"]
            lows = bars_dict["lows"]
            times = bars_dict["times"]
            volumes = bars_dict["volumes"]

            if not closes or len(closes) < 30:
                continue

            # Compute indicators
            ema9_vals = calculate_ema(closes, period=9)
            vwap_vals = calculate_session_vwap(times, highs, lows, closes, volumes, anchor_hour_utc=0)
            atr_vals = calculate_atr(highs, lows, closes, period=14)
            ema200_vals = calculate_ema(closes, period=200)

            # Current completed bar is the penultimate bar [-2] if last is still building, or [-1]
            # In live MT5 rates, [-1] is currently forming bar, [-2] is last closed candle.
            # To evaluate on completed candle close, we evaluate on bar_idx = len(closes) - 2
            completed_idx = len(closes) - 2
            completed_time = times[completed_idx]

            # Parse datetime of completed candle
            if isinstance(completed_time, str):
                try:
                    bar_dt = datetime.fromisoformat(completed_time.replace('Z', '+00:00'))
                except Exception:
                    bar_dt = datetime.now(timezone.utc)
            elif isinstance(completed_time, (int, float)):
                bar_dt = datetime.fromtimestamp(completed_time, tz=timezone.utc)
            else:
                bar_dt = completed_time

            is_session, session_name = is_ema9_vwap_session_active(bar_dt)

            c_close = closes[completed_idx]
            c_open = opens[completed_idx] if (opens and len(opens) > completed_idx) else c_close
            c_high = highs[completed_idx]
            c_low = lows[completed_idx]
            c_ema9 = ema9_vals[completed_idx]
            c_vwap = vwap_vals[completed_idx]
            c_atr = atr_vals[completed_idx]
            c_ema200 = ema200_vals[completed_idx]

            # 4. Check if a new M5 candle has closed
            is_new_candle = (completed_time != last_evaluated_bar_time)
            if is_new_candle:
                last_evaluated_bar_time = completed_time

                c_range = max(0.01, c_high - c_low)
                c_exit_thresh = 0.20 * c_range

                # Live print on M5 Candle Close
                time_str = bar_dt.strftime("%H:%M Server")
                pos_str = f"1 OPEN ({open_positions[0]['direction']} @ ${open_positions[0]['entry_price']:.2f})" if open_positions else "0 OPEN"

                print(
                    f"\n🕯️ [{time_str} | M5 CANDLE CLOSED] Close: ${c_close:.2f} | EMA9: ${c_ema9:.2f} | VWAP: ${c_vwap:.2f} | ATR: ${c_atr:.2f}\n"
                    f"   ├─ ⏰ Session: {session_name}\n"
                    f"   ├─ 🎯 Candle Range: ${c_range:.2f} | 20% Exit Threshold: ${c_exit_thresh:.2f}\n"
                    f"   └─ 🛡️ Active Position: {pos_str}",
                    flush=True
                )

                # =========================================================
                # 5. EVALUATE TREND EXIT ON ACTIVE POSITIONS
                # =========================================================
                for pos in open_positions:
                    pos_ticket = pos["ticket"]
                    pos_dir = pos["direction"]

                    should_exit, dist, exit_reason = evaluate_trend_exit(
                        direction=pos_dir,
                        candle_high=c_high,
                        candle_low=c_low,
                        candle_close=c_close,
                        ema9=c_ema9,
                        reverse_range_pct=0.20
                    )

                    if should_exit:
                        print(f"🎯 >>> TREND REVERSAL EXIT TRIGGERED FOR {pos_dir} #{pos_ticket} <<<", flush=True)
                        print(f"   Reason: {exit_reason}", flush=True)
                        closed_ok, msg = mt5_bridge.close_position(pos_ticket, comment="EMA9_TrendExit")
                        if closed_ok:
                            print(f"✅ {msg}\n", flush=True)
                            try:
                                storage.update_closed_trade(pos_ticket, c_close, 0.0, exit_reason=exit_reason)
                            except Exception as e:
                                print(f"⚠️ Storage update warning: {e}", flush=True)
                        else:
                            print(f"❌ Failed to close position: {msg}\n", flush=True)

                # Refresh open positions after potential exit
                open_positions = mt5_bridge.get_open_positions()

                # 5b. Evaluate Breakeven SL Update on active positions
                if breakeven_atr > 0 and open_positions:
                    for pos in open_positions:
                        pos_ticket = pos["ticket"]
                        pos_dir = pos["direction"]
                        entry_p = pos["entry_price"]
                        current_sl = pos.get("sl", 0.0)

                        if pos_dir == "BUY":
                            be_trigger = entry_p + (breakeven_atr * c_atr)
                            target_be_sl = round(entry_p + 0.25, 2)
                            if c_high >= be_trigger and current_sl < target_be_sl:
                                ok_mod = mt5_bridge.modify_position_sl(pos_ticket, target_be_sl)
                                if ok_mod:
                                    print(f"🛡️ [BREAKEVEN TRIGGERED] Buy #{pos_ticket} reached +{breakeven_atr:.1f}x ATR (${be_trigger:.2f})! SL moved to Breakeven (+Spread): ${target_be_sl:.2f}", flush=True)
                        elif pos_dir == "SELL":
                            be_trigger = entry_p - (breakeven_atr * c_atr)
                            target_be_sl = round(entry_p - 0.25, 2)
                            if c_low <= be_trigger and (current_sl == 0.0 or current_sl > target_be_sl):
                                ok_mod = mt5_bridge.modify_position_sl(pos_ticket, target_be_sl)
                                if ok_mod:
                                    print(f"🛡️ [BREAKEVEN TRIGGERED] Sell #{pos_ticket} reached +{breakeven_atr:.1f}x ATR (${be_trigger:.2f})! SL moved to Breakeven (+Spread): ${target_be_sl:.2f}", flush=True)

                # =========================================================
                # 6. EVALUATE NEW ENTRY RULES (IF NO POSITION OPEN)
                # =========================================================
                if len(open_positions) == 0:
                    # Check Daily SL Shield: If balance drops >= daily_max_loss from Day Start Balance
                    curr_acc = mt5_bridge.get_account_info()
                    curr_bal = curr_acc.balance if curr_acc else day_start_balance
                    loss_from_day_start = day_start_balance - curr_bal

                    if daily_max_loss > 0 and loss_from_day_start >= daily_max_loss:
                        if (time.time() - last_shield_print_time) > 300:
                            last_shield_print_time = time.time()
                            print(f"🛑 [DAILY SL BLOCK ACTIVE] Balance (${curr_bal:.2f}) dropped -${loss_from_day_start:.2f} below Day-Start Balance (${day_start_balance:.2f}, limit -${daily_max_loss:.2f})! Halting new entries for today. Resuming tomorrow at day open.", flush=True)
                        continue

                    if not is_session:
                        # Outside allowed session (only Asian 00-08 and London 12-17 allowed)
                        continue

                    if session_name != current_session_str:
                        current_session_str = session_name
                        session_consecutive_losses = 0  # New session starts clean!

                    # Check Max Daily Trades Limit
                    if max_daily_trades > 0 and today_trades_count >= max_daily_trades:
                        continue

                    # Check Session Consecutive Loss Pause
                    if max_session_losses > 0 and session_consecutive_losses >= max_session_losses:
                        continue

                    # Check News Shield
                    if enable_news_shield:
                        is_news_f, news_stat_msg, _ = news_filter.is_news_freeze_active()
                        if is_news_f:
                            print(f"🚨 [NEWS SHIELD BLOCKED] {news_stat_msg}. Pausing entry.", flush=True)
                            continue

                    # Previous completed bar values
                    prev_idx = completed_idx - 1
                    prev_ema9 = ema9_vals[prev_idx]
                    prev_vwap = vwap_vals[prev_idx]
                    ema_gap = abs(c_close - c_ema9)
                    candle_range = c_high - c_low

                    if max_ema_gap > 0 and (ema_gap > max_ema_gap * c_atr):
                        print(f"⚠️ [OVEREXTENSION SKIPPED] Close (${c_close:.2f}) is ${ema_gap:.2f} away from EMA9 ({c_ema9:.2f}) > {max_ema_gap:.2f}x ATR (${max_ema_gap * c_atr:.2f}). Skipping overextended entry.", flush=True)
                        continue

                    if max_candle_range > 0 and (candle_range > max_candle_range * c_atr):
                        print(f"⚠️ [GIANT CANDLE SKIPPED] Candle range (${candle_range:.2f}) > {max_candle_range:.2f}x ATR (${max_candle_range * c_atr:.2f}). Skipping climax spike.", flush=True)
                        continue

                    if trigger_mode == "candle_vwap_cross":
                        is_buy = ((c_open <= c_vwap) or (closes[prev_idx] <= prev_vwap)) and (c_close > c_vwap) and (c_close > c_ema9)
                        is_sell = ((c_open >= c_vwap) or (closes[prev_idx] >= prev_vwap)) and (c_close < c_vwap) and (c_close < c_ema9)
                    else:
                        is_buy = (prev_ema9 <= prev_vwap) and (c_ema9 > c_vwap) and (c_close > c_ema9)
                        is_sell = (prev_ema9 >= prev_vwap) and (c_ema9 < c_vwap) and (c_close < c_ema9)

                    # Check 200 EMA Macro Trend Filter
                    if use_200_ema and is_buy and (c_close <= c_ema200):
                        print(f"⚠️ [200 EMA BLOCKED] Buy signal skipped: Close (${c_close:.2f}) <= 200 EMA (${c_ema200:.2f})", flush=True)
                        is_buy = False
                    if use_200_ema and is_sell and (c_close >= c_ema200):
                        print(f"⚠️ [200 EMA BLOCKED] Sell signal skipped: Close (${c_close:.2f}) >= 200 EMA (${c_ema200:.2f})", flush=True)
                        is_sell = False

                    if is_buy:
                        sl_dist = max(min_sl, atr_mult * c_atr)
                        suggested_sl = round(c_close - sl_dist, 2)
                        sym_info = mt5_bridge.get_symbol_info()
                        ask_price = sym_info.ask if sym_info else c_close

                        print(f"\n🚀 >>> FRESH BUY SIGNAL DETECTED ON M5! EXECUTING BUY @ ${ask_price:.2f} <<<", flush=True)
                        print(f"   Mode: {trigger_mode} | Close: ${c_close:.2f} | EMA9: ${c_ema9:.2f} | VWAP: ${c_vwap:.2f}", flush=True)
                        print(f"   Protective SL: ${suggested_sl:.2f} ({atr_mult} x ATR = ${atr_mult * c_atr:.2f}) | TP: Trend-Following (Open)", flush=True)

                        res = mt5_bridge.send_order(
                            direction="BUY",
                            volume=lot,
                            sl_price=suggested_sl,
                            tp_price=0.0,  # Open TP: Exit is managed dynamically by Trend Exit rule
                            magic_number=mt5_bridge.magic_number,
                            comment="EMA9_VWAP_BUY"
                        )
                        ok, ticket, msg = res if (isinstance(res, tuple) and len(res) == 3) else (False, 0, str(res))
                        if ok:
                            today_trades_count += 1
                            print(f"✅ {msg} (Trades Today: {today_trades_count})\n", flush=True)
                            try:
                                storage.record_trade({
                                    "order_id": ticket,
                                    "symbol": mt5_bridge.symbol,
                                    "direction": "BUY",
                                    "volume": lot,
                                    "entry_price": ask_price,
                                    "sl": suggested_sl,
                                    "tp": 0.0,
                                    "status": "OPEN",
                                    "opened_at": datetime.now(timezone.utc).isoformat()
                                })
                            except Exception as e:
                                print(f"⚠️ Storage record warning: {e}", flush=True)
                        else:
                            print(f"❌ Buy Order Failed: {msg}\n", flush=True)

                    elif is_sell:
                        sl_dist = max(min_sl, atr_mult * c_atr)
                        suggested_sl = round(c_close + sl_dist, 2)
                        sym_info = mt5_bridge.get_symbol_info()
                        bid_price = sym_info.bid if sym_info else c_close

                        print(f"\n🚀 >>> FRESH SELL SIGNAL DETECTED ON M5! EXECUTING SELL @ ${bid_price:.2f} <<<", flush=True)
                        print(f"   Mode: {trigger_mode} | Close: ${c_close:.2f} | EMA9: ${c_ema9:.2f} | VWAP: ${c_vwap:.2f}", flush=True)
                        print(f"   Protective SL: ${suggested_sl:.2f} ({atr_mult} x ATR = ${atr_mult * c_atr:.2f}) | TP: Trend-Following (Open)", flush=True)

                        res = mt5_bridge.send_order(
                            direction="SELL",
                            volume=lot,
                            sl_price=suggested_sl,
                            tp_price=0.0,  # Open TP: Exit managed dynamically by Trend Exit rule
                            magic_number=mt5_bridge.magic_number,
                            comment="EMA9_VWAP_SELL"
                        )
                        ok, ticket, msg = res if (isinstance(res, tuple) and len(res) == 3) else (False, 0, str(res))
                        if ok:
                            today_trades_count += 1
                            print(f"✅ {msg} (Trades Today: {today_trades_count})\n", flush=True)
                            try:
                                storage.record_trade({
                                    "order_id": ticket,
                                    "symbol": mt5_bridge.symbol,
                                    "direction": "SELL",
                                    "volume": lot,
                                    "entry_price": bid_price,
                                    "sl": suggested_sl,
                                    "tp": 0.0,
                                    "status": "OPEN",
                                    "opened_at": datetime.now(timezone.utc).isoformat()
                                })
                            except Exception as e:
                                print(f"⚠️ Storage record warning: {e}", flush=True)
                        else:
                            print(f"❌ Sell Order Failed: {msg}\n", flush=True)

    except KeyboardInterrupt:
        print("\n🛑 Auto-trading engine stopped by user.", flush=True)
        mt5_bridge.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Live EMA9 + VWAP Cross Strategy on MT5")
    parser.add_argument("--symbol", type=str, default="XAUUSDm", help="Trading Symbol (e.g. XAUUSDm, XAUUSD)")
    parser.add_argument("--days", type=int, default=30, help="Days of history (ignored in live execution, accepted for CLI compatibility)")
    parser.add_argument("--balance", type=float, default=100.0, help="Starting account balance (ignored in live execution, reads broker balance)")
    parser.add_argument("--lot", type=float, default=0.02, help="Fixed lot size (default 0.02)")
    parser.add_argument("--daily-max-loss", type=float, default=0.0, help="Daily Max Loss Block in USD (default 0.0 = disabled, set e.g. 25.0 to enable)")
    parser.add_argument("--max-daily-trades", type=int, default=0, help="Max trades allowed per day (e.g. 3, 0 = unlimited)")
    parser.add_argument("--max-session-losses", type=int, default=0, help="Max consecutive losses before pausing current session (e.g. 2, 0 = unlimited)")
    parser.add_argument("--atr-mult", type=float, default=2.0, help="ATR SL multiplier (default 2.0, e.g. 1.5 or 2.0)")
    parser.add_argument("--min-sl", type=float, default=0.0, help="Minimum Stop Loss in USD (default 0.0, e.g. 2.5)")
    parser.add_argument("--max-ema-gap", type=float, default=0.0, help="Max allowed gap between Close and EMA9 in ATR units (e.g. 0.8 or 1.0, default 0.0 = disabled)")
    parser.add_argument("--max-candle-range", type=float, default=0.0, help="Max trigger candle range in ATR units (e.g. 1.8 or 2.0, default 0.0 = disabled)")
    parser.add_argument("--breakeven-atr", type=float, default=0.0, help="Move SL to Breakeven (+Spread) once profit reaches N x ATR (e.g. 1.5 or 2.0, default 0.0 = disabled)")
    parser.add_argument("--use-200-ema", action="store_true", help="Filter trades with 200 EMA (Buys above 200 EMA, Sells below 200 EMA)")
    parser.add_argument("--trigger-mode", type=str, choices=["ema_cross", "candle_vwap_cross"], default="ema_cross", help="Trigger mode: 'ema_cross' (default) or 'candle_vwap_cross'")
    parser.add_argument("--candle-vwap-cross", action="store_true", help="Shortcut to run candle crosses VWAP while aligned with EMA9")
    parser.add_argument("--no-news", action="store_true", help="Disable economic news shield")
    parser.add_argument("--mt5-path", type=str, default="", help="Path to specific MT5 terminal64.exe (e.g. 'C:\\Program Files\\MetaTrader 5 - Bot2\\terminal64.exe')")
    parser.add_argument("--magic-number", type=int, default=9050201, help="Unique Magic Number for order tracking (default 9050201)")
    parser.add_argument("--login", type=int, default=0, help="MT5 Account Number to bind / connect to (e.g. 12345678)")
    parser.add_argument("--server", type=str, default="", help="Broker server name (optional, e.g. 'Exness-MT5Real')")
    parser.add_argument("--password", type=str, default="", help="Account password (optional, needed only if not already saved in MT5)")
    args = parser.parse_args()

    mode = "candle_vwap_cross" if args.candle_vwap_cross else args.trigger_mode

    run_live_auto_trading(
        symbol=args.symbol,
        enable_news_shield=not args.no_news,
        daily_max_loss=args.daily_max_loss,
        max_daily_trades=args.max_daily_trades,
        max_session_losses=args.max_session_losses,
        atr_mult=args.atr_mult,
        min_sl=args.min_sl,
        max_ema_gap=args.max_ema_gap,
        max_candle_range=args.max_candle_range,
        breakeven_atr=args.breakeven_atr,
        use_200_ema=args.use_200_ema,
        trigger_mode=mode,
        lot=args.lot,
        mt5_path=args.mt5_path if args.mt5_path.strip() else None,
        magic_number=args.magic_number,
        login=args.login if args.login > 0 else None,
        server=args.server if args.server.strip() else None,
        password=args.password if args.password.strip() else None
    )
