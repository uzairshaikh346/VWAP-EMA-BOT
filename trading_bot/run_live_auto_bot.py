"""
Autonomous Institutional-Grade Live Scalper Engine for MT5 (XAUUSD M1).
Features:
1. Multi-Timeframe Trend Filter (M15 EMA 50 alignment prevents counter-trend traps)
2. Institutional Killzone Tracker (London & New York high-volume momentum)
3. Smart Dynamic ATR-Buffered SL & TP (Minimum $1.80 breathing room prevents stop-hunting)
4. Dynamic Auto Break-Even Shield (Moves SL to entry + spread at 50% TP progress)
5. Single Active Position Enforcement (Prevents dangerous stacking/over-leveraging)
6. Post-Loss Cooling Guard (5-minute circuit pause prevents revenge whipsaws)
"""

import time
import sys
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from trading_bot.mt5_bridge import MT5Bridge
from trading_bot.strategy import (
    StrategyParameters,
    evaluate_checklist_at_bar,
    calculate_sl_tp,
    calculate_atr,
    evaluate_htf_trend,
    is_in_killzone
)
from trading_bot.circuit_breakers import CircuitBreakerConfig, CircuitBreakerManager
from trading_bot.storage import BotStorage
from trading_bot.news_filter import EconomicNewsFilter


def run_live_auto_trading():
    print("=" * 85, flush=True)
    print("🚀 STARTING INSTITUTIONAL PRO SCALPER ENGINE (XAUUSD M1)", flush=True)
    print("🛡️ ACTIVE CONFLUENCES: M15 Trend Align | Break-Even Shield | Smart ATR Buffer", flush=True)
    print("=" * 85, flush=True)

    # Institutional-Grade Parameters (Optimized Quick Scalper for Gold M1)
    params = StrategyParameters()
    params.max_pullback_bars = 30        # Realistic pullback window
    params.ob_buffer_atr = 0.35          # Clean Order Block retest zone
    params.pullback_atr_mult = 1.6       # Proximity to EMA 9/21 zone
    params.rr_ratio = 1.25               # Realistic 1:1.25 Risk:Reward for fast scalping
    params.sl_lookback_bars = 4          # Tight recent swing lookback
    params.sl_buffer_atr = 0.25          # Tight cushion beyond swing pivots
    params.min_sl_distance_points = 1.50 # Minimum $1.50 SL on Gold
    params.max_sl_distance_points = 2.50 # Capped Maximum $2.50 SL (Limits max loss to ~$2.50!)
    params.enable_htf_filter = True      # Strictly trade with M15 macro trend
    params.enable_session_filter = False # Allow profitable Asian & Morning sessions (Pakistan 3:00 AM - 11:00 AM)

    # Trading Volume & Profit Lock Settings
    trade_lot_size = 0.01                # Micro-lot 0.01 for safe scaling and testing
    daily_profit_target_usd = 10.0       # Daily Profit Goal ($10.00 on 0.01 lot = 100 pips / 3-4 clean scalps)
    enable_daily_profit_lock = True      # Automatically locks profits and pauses for the day when target hit

    cb_config = CircuitBreakerConfig(
        bypass_noise_gate_for_demo=True,
        max_consecutive_losses=3,        # Pause after 3 consecutive losses
        max_daily_loss_usd=15.0,         # STRICT Daily Capital Shield: Stop trading if -$15 hit today!
        cooldown_after_loss_minutes=5
    )
    cb_manager = CircuitBreakerManager(config=cb_config)
    storage = BotStorage()
    mt5_bridge = MT5Bridge(symbol="XAUUSDm")
    news_filter = EconomicNewsFilter(target_currencies=["USD"], freeze_before_mins=15, freeze_after_mins=15)
    print("📡 Loading High-Impact Economic News Calendar (ForexFactory)...", flush=True)
    news_filter.fetch_calendar_events()
    next_ev = news_filter.get_next_upcoming_event()
    if next_ev:
        print(f"📅 Next High-Impact News: '{next_ev['title']}' at {next_ev['time_utc'].strftime('%Y-%m-%d %H:%M UTC')}", flush=True)
    else:
        print("📅 No immediate High-Impact USD events in calendar window.", flush=True)

    if not mt5_bridge.connect():
        print("❌ Could not connect to MetaTrader 5 terminal. Exiting.", flush=True)
        return

    acc = mt5_bridge.get_account_info()
    algo_allowed = mt5_bridge.is_algo_trading_enabled()

    print(f"✅ Connected to MT5 Account: {acc.login} | Mode: {acc.trade_mode} | Balance: ${acc.balance:,.2f}", flush=True)
    print(f"⚡ Target Symbol: {mt5_bridge.symbol} | Default Lot: {trade_lot_size} | Algo Allowed: {algo_allowed}", flush=True)
    print(f"🔒 Daily Profit Target: ${daily_profit_target_usd:.2f} (Lock Active: {enable_daily_profit_lock})", flush=True)
    print("⚡ Auto-Scanner active. Streaming live ticks every 3 seconds...\n", flush=True)

    last_evaluated_time = 0
    last_loss_time = 0
    last_target_print_time = 0
    last_toxic_print_time = 0
    last_session_print_time = 0
    start_session_time = int(time.time())
    processed_deal_tickets = set()
    be_moved_tickets = set()

    session_realized_pnl = 0.0
    session_consecutive_losses = 0

    try:
        while True:
            time.sleep(3)

            # 1. Fetch live open positions and apply 70% Break-Even with Spread Cushion
            open_positions = mt5_bridge.get_open_positions()
            sym_info = mt5_bridge.get_symbol_info()
            spread = max(0.20, min(0.60, float(sym_info.spread_usd or 0.25))) if sym_info else 0.25

            for pos in open_positions:
                ticket = pos["ticket"]
                direction = pos["direction"]
                entry_p = pos["entry_price"]
                current_p = pos["current_price"]
                sl = pos["sl"]
                tp = pos["tp"]

                # Move to Break-Even ONLY when trade reaches 70% toward TP (Gives full breathing room!)
                if ticket not in be_moved_tickets and tp > 0 and sl > 0:
                    if direction == "BUY":
                        target_dist = tp - entry_p
                        current_gain = current_p - entry_p
                        if current_gain >= target_dist * 0.70 and sl < entry_p:
                            new_sl = round(entry_p + spread + 0.10, 2)
                            if mt5_bridge.modify_position_sl(ticket, new_sl):
                                be_moved_tickets.add(ticket)
                                print(f"🔒 [BREAK-EVEN SHIELD] BUY Order #{ticket} reached 70% toward TP (+${current_gain:.2f})! SL locked to Entry + Spread Cushion (${new_sl:.2f}). Trade is 100% Risk-Free!", flush=True)

                    elif direction == "SELL":
                        target_dist = entry_p - tp
                        current_gain = entry_p - current_p
                        if current_gain >= target_dist * 0.70 and (sl > entry_p or sl == 0):
                            new_sl = round(entry_p - (spread + 0.10), 2)
                            if mt5_bridge.modify_position_sl(ticket, new_sl):
                                be_moved_tickets.add(ticket)
                                print(f"🔒 [BREAK-EVEN SHIELD] SELL Order #{ticket} reached 70% toward TP (+${current_gain:.2f})! SL locked to Entry - Spread Cushion (${new_sl:.2f}). Trade is 100% Risk-Free!", flush=True)

            # 2. Check deals closed today (anchored to 00:00:00 UTC)
            today_realized_pnl = 0.0
            if hasattr(mt5_bridge, "get_closed_deals"):
                today_midnight_utc = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
                closed_deals = mt5_bridge.get_closed_deals(from_timestamp=today_midnight_utc)
                for deal in closed_deals:
                    ticket = deal["ticket"]
                    pnl = deal["profit"]
                    today_realized_pnl += pnl

                    if ticket not in processed_deal_tickets:
                        processed_deal_tickets.add(ticket)
                        exit_p = deal["close_price"]
                        storage.update_closed_trade(ticket, exit_p, pnl, exit_reason="MT5 Deal Closed")
                        cb_manager.record_trade_outcome(net_pnl_usd=pnl, current_balance=acc.balance)

                        session_realized_pnl += pnl
                        if pnl < 0:
                            session_consecutive_losses += 1
                            last_loss_time = time.time()
                            if session_consecutive_losses >= 2:
                                print(f"🛑 [CIRCUIT PAUSE] {session_consecutive_losses} consecutive losses detected! Market appears choppy/whipsawing. Bot is PAUSING for 45 minutes to protect capital.", flush=True)
                            else:
                                print(f"⚠️ [TRADE CLOSED - LOSS] Deal #{ticket} closed at -${abs(pnl):.2f}. Today's Net PnL: ${today_realized_pnl:+.2f}. Cooling down for 5 mins.", flush=True)
                        else:
                            session_consecutive_losses = 0
                            print(f"🎉 [TRADE CLOSED - WIN] Deal #{ticket} closed at +${pnl:.2f} profit! Today's Net PnL: ${today_realized_pnl:+.2f}", flush=True)

            # 3. Fetch live M1 bars
            bars = mt5_bridge.get_rates(count=150)
            if not bars or len(bars) < 35:
                continue

            latest_bar = bars[-1]
            opens = [b.open for b in bars]
            highs = [b.high for b in bars]
            lows = [b.low for b in bars]
            closes = [b.close for b in bars]
            times = [b.time for b in bars]
            volumes = [b.tick_volume for b in bars]

            curr_idx = len(closes) - 1

            # 4. Fetch M15 bars for Macro Trend Alignment and Overextension
            htf_trend = "NEUTRAL"
            htf_reason = "HTF Filter Disabled"
            htf_ema = 0.0
            try:
                htf_data = mt5_bridge.fetch_htf_bars(count=80, timeframe="M15")
                if htf_data and len(htf_data["closes"]) >= 50:
                    htf_trend, htf_ema, htf_reason = evaluate_htf_trend(htf_data["closes"], period=50)
            except Exception as e:
                htf_trend = "NEUTRAL"
                htf_reason = f"HTF fetch error: {str(e)}"

            # 5. Session Killzone Status
            in_killzone, killzone_name = is_in_killzone()

            # 6. Evaluate 5-Step Checklist on M1
            checklist = evaluate_checklist_at_bar(
                opens, highs, lows, closes, times, volumes, curr_idx, params
            )
            long_st = checklist["LONG"]
            short_st = checklist["SHORT"]

            atr_vals = calculate_atr(highs, lows, closes, period=14)
            curr_atr = atr_vals[-1] if atr_vals else 1.0

            now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")

            # 7. Print Diagnostic Output on M1 Candle Close
            if latest_bar.time != last_evaluated_time:
                last_evaluated_time = latest_bar.time

                buy_passed_count = sum([long_st.vwap_pass, long_st.crossover_pass, long_st.ob_pass, long_st.pullback_pass, long_st.confirmation_pass])
                sell_passed_count = sum([short_st.vwap_pass, short_st.crossover_pass, short_st.ob_pass, short_st.pullback_pass, short_st.confirmation_pass])

                pos_status = f"{len(open_positions)} OPEN ({open_positions[0]['direction']})" if open_positions else "0 OPEN"

                is_news_f, news_stat_msg, _ = news_filter.is_news_freeze_active()
                news_disp = "🚨 FREEZE ACTIVE (" + news_stat_msg + ")" if is_news_f else "🟢 CLEAR"

                print(
                    f"\n🕯️ [{now_str} UTC | M1 CLOSE] Price: ${closes[-1]:.2f} | ATR: ${curr_atr:.2f} | Today PnL: ${today_realized_pnl:+.2f} (Goal: ${daily_profit_target_usd:.2f}) | Session: {killzone_name}\n"
                    f"   ├─ 🧭 M15 Trend: {htf_trend} ({htf_reason})\n"
                    f"   ├─ 📰 News Shield: {news_disp}\n"
                    f"   ├─ 🟢 BUY Setup ({buy_passed_count}/5): VWAP={long_st.vwap_pass} | Cross={long_st.crossover_pass} | OB={long_st.ob_pass} | Pullback={long_st.pullback_pass} | Candle={long_st.confirmation_pass}\n"
                    f"   ├─ 🔴 SELL Setup ({sell_passed_count}/5): VWAP={short_st.vwap_pass} | Cross={short_st.crossover_pass} | OB={short_st.ob_pass} | Pullback={short_st.pullback_pass} | Candle={short_st.confirmation_pass}\n"
                    f"   └─ 🛡️ Active Positions: {pos_status}",
                    flush=True
                )

            # ================= STRICT RISK SHIELDS =================

            # Shield 0: Daily Profit Target Lock (Protects Banked Profits at $10.00 Goal)
            effective_daily_pnl = max(session_realized_pnl, today_realized_pnl)
            if enable_daily_profit_lock and effective_daily_pnl >= daily_profit_target_usd:
                if (time.time() - last_target_print_time) > 300:
                    last_target_print_time = time.time()
                    print(f"🏆 [DAILY TARGET LOCKED] Today's Net Profit (+${effective_daily_pnl:.2f}) reached goal of ${daily_profit_target_usd:.2f}! Trading locked for today to protect capital.", flush=True)
                continue

            # Shield 1: Single Active Position Guard
            if len(open_positions) >= 1:
                continue

            # Shield 2a: 2 Consecutive Losses -> Extended 45-Minute Breather to protect capital
            if session_consecutive_losses >= 2:
                time_since_loss = time.time() - last_loss_time
                if time_since_loss < 2700:  # 45 minutes = 2700 seconds
                    rem_mins = int((2700 - time_since_loss) / 60)
                    continue

            # Shield 2b: Standard 5-Minute Post-Loss Cooling Period
            if (time.time() - last_loss_time) < (cb_config.cooldown_after_loss_minutes * 60):
                continue

            # Shield 3: Dead-Market Anti-Chop Filter (Gold M1 ATR < $0.70 indicates flat range trap)
            if curr_atr < 0.70:
                continue

            # Shield 4: Golden Trading Session Filter (London 05:00-09:30 UTC & US 16:00-20:30 UTC)
            if params.enable_session_filter and not in_killzone:
                if (time.time() - last_session_print_time) > 600:
                    last_session_print_time = time.time()
                    print(f"⏸️ [SESSION REST] {killzone_name}. Active Golden Windows: 05:00-09:30 UTC (London) & 16:00-20:30 UTC (US Flow). Bot resting safely.", flush=True)
                continue

            # Shield 4b: High-Risk Whipsaw Hours Shield (10:00-15:00 UTC US Open / London Close chop)
            if getattr(params, "avoid_toxic_hours", True):
                current_utc_hour = datetime.now(timezone.utc).hour
                if current_utc_hour in [10, 12, 13, 14, 15]:
                    if (time.time() - last_toxic_print_time) > 600:
                        last_toxic_print_time = time.time()
                        print(f"⏸️ [CHOP SHIELD] Hour {current_utc_hour:02d}:00 UTC is in the High-Risk Whipsaw Zone (historical -$180 loss window). Pausing entries until clean market flow.", flush=True)
                    continue

            # Shield 5: Circuit Breakers (Max consecutive losses / daily loss)
            can_trade, reason = cb_manager.can_open_trade(
                is_demo_account=acc.is_demo,
                algo_trading_enabled=mt5_bridge.is_algo_trading_enabled(),
                current_balance=acc.balance
            )
            if not can_trade:
                continue

            # Shield 6: Automated High-Impact Economic News Shield (NFP, CPI, FOMC, etc.)
            is_news_freeze, news_reason, _ = news_filter.is_news_freeze_active()
            if is_news_freeze:
                if (time.time() - last_loss_time) > 60:
                    # Print once per minute to avoid spamming
                    print(f"🛑 [NEWS SHIELD BLOCKED] {news_reason}", flush=True)
                continue

            # ================= EXECUTE BUY ORDER =================
            # Must satisfy all 5 M1 checklist items + M15 HTF Bullish alignment
            if long_st.all_passed:
                if params.enable_htf_filter and htf_trend == "BEARISH":
                    print(f"⚠️ [FILTER BLOCKED] M1 BUY Signal skipped: M15 Macro Trend is BEARISH (Counter-trend protection)", flush=True)
                    continue

                print(f"\n🎯 >>> ALL CONFLUENCES ALIGNED: EXECUTING BUY ORDER AT ${sym_info.ask:.2f} <<<", flush=True)
                print(f"   SL: ${long_st.suggested_sl:.2f} (Risk: ${long_st.risk_points:.2f}) | TP: ${long_st.suggested_tp:.2f} (Reward: ${long_st.reward_points:.2f})", flush=True)
                
                res = mt5_bridge.send_order(
                    direction="BUY",
                    volume=trade_lot_size,
                    sl_price=long_st.suggested_sl,
                    tp_price=long_st.suggested_tp,
                    magic_number=cb_config.magic_number,
                    comment="ProScalper_BUY"
                )
                ok, ticket, msg = res if (isinstance(res, tuple) and len(res) == 3) else (False, 0, str(res))
                if ok:
                    print(f"✅ {msg}\n", flush=True)
                    storage.record_trade({
                        "order_id": ticket,
                        "symbol": mt5_bridge.symbol,
                        "direction": "BUY",
                        "volume": trade_lot_size,
                        "entry_price": long_st.close_price,
                        "sl": long_st.suggested_sl,
                        "tp": long_st.suggested_tp,
                        "status": "OPEN",
                        "opened_at": datetime.now(timezone.utc).isoformat()
                    })
                    time.sleep(60)
                else:
                    print(f"❌ Order Failed: {msg}\n", flush=True)

            # ================= EXECUTE SELL ORDER =================
            # Must satisfy all 5 M1 checklist items + M15 HTF Bearish alignment
            elif short_st.all_passed:
                if params.enable_htf_filter and htf_trend == "BULLISH":
                    print(f"⚠️ [FILTER BLOCKED] M1 SELL Signal skipped: M15 Macro Trend is BULLISH (Counter-trend protection)", flush=True)
                    continue

                print(f"\n🎯 >>> ALL CONFLUENCES ALIGNED: EXECUTING SELL ORDER AT ${sym_info.bid:.2f} <<<", flush=True)
                print(f"   SL: ${short_st.suggested_sl:.2f} (Risk: ${short_st.risk_points:.2f}) | TP: ${short_st.suggested_tp:.2f} (Reward: ${short_st.reward_points:.2f})", flush=True)

                res = mt5_bridge.send_order(
                    direction="SELL",
                    volume=trade_lot_size,
                    sl_price=short_st.suggested_sl,
                    tp_price=short_st.suggested_tp,
                    magic_number=cb_config.magic_number,
                    comment="ProScalper_SELL"
                )
                ok, ticket, msg = res if (isinstance(res, tuple) and len(res) == 3) else (False, 0, str(res))
                if ok:
                    print(f"✅ {msg}\n", flush=True)
                    storage.record_trade({
                        "order_id": ticket,
                        "symbol": mt5_bridge.symbol,
                        "direction": "SELL",
                        "volume": trade_lot_size,
                        "entry_price": short_st.close_price,
                        "sl": short_st.suggested_sl,
                        "tp": short_st.suggested_tp,
                        "status": "OPEN",
                        "opened_at": datetime.now(timezone.utc).isoformat()
                    })
                    time.sleep(60)
                else:
                    print(f"❌ Order Failed: {msg}\n", flush=True)

    except KeyboardInterrupt:
        print("\n🛑 Auto-trading engine stopped by user.", flush=True)
        mt5_bridge.disconnect()


if __name__ == "__main__":
    run_live_auto_trading()
