"""
Background-thread wrapper around the live auto-trading loop.

This is the SAME trading logic that used to live only in the standalone
`run_live_auto_bot.py` script. It's wrapped in a class that runs on a daemon
thread with a stop switch, and exposes its live status + log lines, so the
Streamlit dashboard can start/stop it with a button instead of you having to
run a second terminal window.

`run_live_auto_bot.py` still works stand-alone (it just drives this same
engine from the CLI) if you ever want to run the bot headless without the
dashboard at all.
"""

import threading
import time
import collections
from datetime import datetime, timezone
from typing import Optional

from trading_bot.mt5_bridge import MT5Bridge
from trading_bot.strategy import (
    StrategyParameters,
    evaluate_checklist_at_bar,
    calculate_atr,
    calculate_adx,
    evaluate_htf_trend,
    is_in_killzone,
    classify_session,
)
from trading_bot.circuit_breakers import CircuitBreakerConfig, CircuitBreakerManager
from trading_bot.storage import BotStorage
from trading_bot.news_filter import EconomicNewsFilter


class LiveTradingEngine:
    """Runs the institutional scalper loop on a background daemon thread."""

    def __init__(self, symbol: str = "XAUUSDm", db_path: str = "live_trades.sqlite"):
        self.symbol = symbol
        self.db_path = db_path

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.running = False
        self.error: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.log_lines = collections.deque(maxlen=300)

        # Live snapshot the dashboard polls each rerun - cheap dict reads, no locking needed
        # since each field is written by the engine thread and only ever read by the UI thread.
        self.status = {
            "connected": False,
            "account_login": None,
            "balance": 0.0,
            "today_pnl": 0.0,
            "session_pnl": 0.0,
            "session_code": "",
            "session_label": "",
            "htf_trend": "NEUTRAL",
            "htf_reason": "",
            "buy_passed": 0,
            "sell_passed": 0,
            "open_positions": 0,
            "last_price": 0.0,
            "atr": 0.0,
            "adx": 0.0,
            "news_freeze": False,
            "news_reason": "",
            "last_update": None,
        }

    # ---- status helpers -----------------------------------------------

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        for line in str(msg).split("\n"):
            self.log_lines.append(f"[{ts}] {line}")
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            pass  # console codepage can't render emoji - the dashboard log still gets the line

    # ---- lifecycle ------------------------------------------------------

    def start(self):
        with self._lock:
            if self.is_running():
                return False, "Engine is already running."
            self._stop_event.clear()
            self.error = None
            self._thread = threading.Thread(target=self._run, daemon=True, name="LiveTradingEngine")
            self._thread.start()
            self.started_at = datetime.now(timezone.utc)
            return True, "Engine starting..."

    def stop(self):
        with self._lock:
            if not self.is_running():
                self.running = False
                return False, "Engine is not running."
            self._stop_event.set()
            return True, "Stop signal sent - engine will halt within a few seconds."

    def _sleep(self, seconds: float):
        """Sleep in short slices so a stop request is picked up quickly instead of
        blocking for the full duration."""
        end = time.time() + seconds
        while time.time() < end and not self._stop_event.is_set():
            time.sleep(min(0.5, max(0.0, end - time.time())))

    # ---- main loop --------------------------------------------------------

    def _run(self):
        self.running = True
        mt5_bridge = MT5Bridge(symbol=self.symbol)
        try:
            self._log("=" * 85)
            self._log("🚀 STARTING INSTITUTIONAL PRO SCALPER ENGINE (XAUUSD M1)")
            self._log("🛡️ ACTIVE CONFLUENCES: M15 Trend Align | Break-Even Shield | Smart ATR Buffer")
            self._log("=" * 85)

            # Institutional-Grade Parameters (Optimized Quick Scalper for Gold M1)
            params = StrategyParameters()
            params.max_pullback_bars = 30
            params.ob_buffer_atr = 0.35
            params.pullback_atr_mult = 1.6
            params.rr_ratio = 1.25
            params.sl_lookback_bars = 4
            params.sl_buffer_atr = 0.25
            params.min_sl_distance_points = 1.50
            params.max_sl_distance_points = 2.50
            params.enable_htf_filter = True
            params.enable_session_filter = False
            params.avoid_toxic_hours = False  # TEST PHASE: London/Overlap recorded, not blocked

            trade_lot_size = 0.01
            daily_profit_target_usd = 10.0
            enable_daily_profit_lock = True

            cb_config = CircuitBreakerConfig(
                bypass_noise_gate_for_demo=True,
                max_consecutive_losses=3,
                max_daily_loss_usd=15.0,
                cooldown_after_loss_minutes=5,
            )
            cb_manager = CircuitBreakerManager(config=cb_config)
            storage = BotStorage(self.db_path)

            self._log("📡 Loading High-Impact Economic News Calendar (ForexFactory)...")
            news_filter = EconomicNewsFilter(target_currencies=["USD"], freeze_before_mins=15, freeze_after_mins=15)
            news_filter.fetch_calendar_events()
            next_ev = news_filter.get_next_upcoming_event()
            if next_ev:
                self._log(f"📅 Next High-Impact News: '{next_ev['title']}' at {next_ev['time_utc'].strftime('%Y-%m-%d %H:%M UTC')}")
            else:
                self._log("📅 No immediate High-Impact USD events in calendar window.")

            ok, conn_msg = mt5_bridge.connect()
            if not ok:
                self._log(f"❌ Could not connect to MetaTrader 5 terminal: {conn_msg}")
                self.error = conn_msg
                return

            acc = mt5_bridge.get_account_info()
            algo_allowed = mt5_bridge.is_algo_trading_enabled()
            self.status["connected"] = True
            self.status["account_login"] = acc.login
            self.status["balance"] = acc.balance

            self._log(f"✅ Connected to MT5 Account: {acc.login} | Mode: {acc.trade_mode} | Balance: ${acc.balance:,.2f}")
            self._log(f"⚡ Target Symbol: {mt5_bridge.symbol} | Default Lot: {trade_lot_size} | Algo Allowed: {algo_allowed}")
            self._log(f"🔒 Daily Profit Target: ${daily_profit_target_usd:.2f} (Lock Active: {enable_daily_profit_lock})")
            self._log("⚡ Auto-Scanner active. Streaming live ticks every 3 seconds...")

            last_evaluated_time = 0
            last_loss_time = 0
            last_target_print_time = 0
            last_toxic_print_time = 0
            processed_deal_tickets = set()
            be_moved_tickets = set()
            session_realized_pnl = 0.0
            session_consecutive_losses = 0

            while not self._stop_event.is_set():
                self._sleep(3)
                if self._stop_event.is_set():
                    break

                # 1. Open positions + 70% Break-Even Shield
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

                    if ticket not in be_moved_tickets and tp > 0 and sl > 0:
                        if direction == "BUY":
                            target_dist = tp - entry_p
                            current_gain = current_p - entry_p
                            if current_gain >= target_dist * 0.70 and sl < entry_p:
                                new_sl = round(entry_p + spread + 0.10, 2)
                                if mt5_bridge.modify_position_sl(ticket, new_sl):
                                    be_moved_tickets.add(ticket)
                                    self._log(f"🔒 [BREAK-EVEN SHIELD] BUY #{ticket} reached 70% toward TP (+${current_gain:.2f})! SL locked to ${new_sl:.2f}.")
                        elif direction == "SELL":
                            target_dist = entry_p - tp
                            current_gain = entry_p - current_p
                            if current_gain >= target_dist * 0.70 and (sl > entry_p or sl == 0):
                                new_sl = round(entry_p - (spread + 0.10), 2)
                                if mt5_bridge.modify_position_sl(ticket, new_sl):
                                    be_moved_tickets.add(ticket)
                                    self._log(f"🔒 [BREAK-EVEN SHIELD] SELL #{ticket} reached 70% toward TP (+${current_gain:.2f})! SL locked to ${new_sl:.2f}.")

                # 2. Deals closed today (anchored 00:00 UTC)
                today_realized_pnl = 0.0
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
                                self._log(f"🛑 [CIRCUIT PAUSE] {session_consecutive_losses} consecutive losses! Pausing 45 minutes to protect capital.")
                            else:
                                self._log(f"⚠️ [TRADE CLOSED - LOSS] Deal #{ticket} closed at -${abs(pnl):.2f}. Today PnL: ${today_realized_pnl:+.2f}. Cooling down 5 mins.")
                        else:
                            session_consecutive_losses = 0
                            self._log(f"🎉 [TRADE CLOSED - WIN] Deal #{ticket} closed at +${pnl:.2f}! Today PnL: ${today_realized_pnl:+.2f}")

                self.status["today_pnl"] = today_realized_pnl
                self.status["session_pnl"] = session_realized_pnl
                self.status["open_positions"] = len(open_positions)
                self.status["balance"] = acc.balance

                # 3. Live M1 bars
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

                # 4. M15 HTF trend alignment
                htf_trend = "NEUTRAL"
                htf_reason = "HTF Filter Disabled"
                try:
                    htf_data = mt5_bridge.fetch_htf_bars(count=80, timeframe="M15")
                    if htf_data and len(htf_data["closes"]) >= 50:
                        htf_trend, _htf_ema, htf_reason = evaluate_htf_trend(htf_data["closes"], period=50)
                except Exception as e:
                    htf_trend = "NEUTRAL"
                    htf_reason = f"HTF fetch error: {str(e)}"

                # 5. Session status
                in_killzone, killzone_name = is_in_killzone()
                sess_code, sess_label = classify_session()

                # 6. 5-step checklist
                checklist = evaluate_checklist_at_bar(opens, highs, lows, closes, times, volumes, curr_idx, params)
                long_st = checklist["LONG"]
                short_st = checklist["SHORT"]

                atr_vals = calculate_atr(highs, lows, closes, period=14)
                curr_atr = atr_vals[-1] if atr_vals else 1.0

                adx_vals = calculate_adx(highs, lows, closes, period=params.adx_period)
                curr_adx = adx_vals[-1] if adx_vals else 25.0

                is_news_f, news_stat_msg, _ = news_filter.is_news_freeze_active()

                buy_passed_count = sum([long_st.vwap_pass, long_st.crossover_pass, long_st.ob_pass, long_st.pullback_pass, long_st.confirmation_pass])
                sell_passed_count = sum([short_st.vwap_pass, short_st.crossover_pass, short_st.ob_pass, short_st.pullback_pass, short_st.confirmation_pass])

                self.status.update({
                    "session_code": sess_code,
                    "session_label": sess_label,
                    "htf_trend": htf_trend,
                    "htf_reason": htf_reason,
                    "buy_passed": buy_passed_count,
                    "sell_passed": sell_passed_count,
                    "last_price": closes[-1],
                    "atr": curr_atr,
                    "adx": curr_adx,
                    "news_freeze": is_news_f,
                    "news_reason": news_stat_msg,
                    "last_update": datetime.now(timezone.utc),
                })

                now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")

                # 7. Diagnostic line on M1 candle close
                if latest_bar.time != last_evaluated_time:
                    last_evaluated_time = latest_bar.time
                    pos_status = f"{len(open_positions)} OPEN ({open_positions[0]['direction']})" if open_positions else "0 OPEN"
                    news_disp = "🚨 FREEZE ACTIVE (" + news_stat_msg + ")" if is_news_f else "🟢 CLEAR"

                    self._log(
                        f"\n🕯️ [{now_str} UTC | M1 CLOSE] Price: ${closes[-1]:.2f} | ATR: ${curr_atr:.2f} | ADX: {curr_adx:.1f} | Today PnL: ${today_realized_pnl:+.2f} (Goal: ${daily_profit_target_usd:.2f}) | Session: {sess_code} [{killzone_name}]\n"
                        f"   ├─ 🧭 M15 Trend: {htf_trend} ({htf_reason})\n"
                        f"   ├─ 📰 News Shield: {news_disp}\n"
                        f"   ├─ 🟢 BUY Setup ({buy_passed_count}/5): VWAP={long_st.vwap_pass} | Cross={long_st.crossover_pass} | OB={long_st.ob_pass} | Pullback={long_st.pullback_pass} | Candle={long_st.confirmation_pass}\n"
                        f"   ├─ 🔴 SELL Setup ({sell_passed_count}/5): VWAP={short_st.vwap_pass} | Cross={short_st.crossover_pass} | OB={short_st.ob_pass} | Pullback={short_st.pullback_pass} | Candle={short_st.confirmation_pass}\n"
                        f"   └─ 🛡️ Active Positions: {pos_status}"
                    )

                # ================= STRICT RISK SHIELDS =================

                # Shield 0: Daily Profit Target Lock
                effective_daily_pnl = max(session_realized_pnl, today_realized_pnl)
                if enable_daily_profit_lock and effective_daily_pnl >= daily_profit_target_usd:
                    if (time.time() - last_target_print_time) > 300:
                        last_target_print_time = time.time()
                        self._log(f"🏆 [DAILY TARGET LOCKED] Today's Net Profit (+${effective_daily_pnl:.2f}) reached goal of ${daily_profit_target_usd:.2f}! Trading locked for today.")
                    continue

                # Shield 1: Single Active Position Guard
                if len(open_positions) >= 1:
                    continue

                # Shield 2a: 2 Consecutive Losses -> 45-minute breather
                if session_consecutive_losses >= 2:
                    if (time.time() - last_loss_time) < 2700:
                        continue

                # Shield 2b: Standard 5-minute post-loss cooldown
                if (time.time() - last_loss_time) < (cb_config.cooldown_after_loss_minutes * 60):
                    continue

                # Shield 3: Dead-market anti-chop filter
                if curr_atr < 0.70:
                    continue

                # Shield 4: Golden session filter (off by default - see params.enable_session_filter)
                if params.enable_session_filter and not in_killzone:
                    continue

                # Shield 4b: Toxic-hours chop shield (off during the current test phase - see
                # params.avoid_toxic_hours; London/Overlap trades are recorded, not blocked)
                if getattr(params, "avoid_toxic_hours", True):
                    current_utc_hour = datetime.now(timezone.utc).hour
                    if current_utc_hour in [10, 11, 12, 13, 14, 15]:
                        if (time.time() - last_toxic_print_time) > 600:
                            last_toxic_print_time = time.time()
                            self._log(f"⏸️ [CHOP SHIELD] Hour {current_utc_hour:02d}:00 UTC is in the High-Risk Whipsaw Zone. Pausing entries.")
                        continue

                # Shield 5: Circuit breakers (max consecutive losses / daily loss)
                can_trade, reason = cb_manager.can_open_trade(
                    is_demo_account=acc.is_demo,
                    algo_trading_enabled=mt5_bridge.is_algo_trading_enabled(),
                    current_balance=acc.balance,
                )
                if not can_trade:
                    continue

                # Shield 6: High-impact economic news shield
                if is_news_f:
                    continue

                # ================= EXECUTE BUY ORDER =================
                if long_st.all_passed:
                    if params.enable_htf_filter and htf_trend == "BEARISH":
                        self._log("⚠️ [FILTER BLOCKED] M1 BUY Signal skipped: M15 Macro Trend is BEARISH (Counter-trend protection)")
                        continue

                    self._log(f"\n🎯 >>> ALL CONFLUENCES ALIGNED: EXECUTING BUY ORDER AT ${sym_info.ask:.2f} <<<")
                    self._log(f"   SL: ${long_st.suggested_sl:.2f} (Risk: ${long_st.risk_points:.2f}) | TP: ${long_st.suggested_tp:.2f} (Reward: ${long_st.reward_points:.2f})")

                    res = mt5_bridge.send_order(
                        direction="BUY",
                        volume=trade_lot_size,
                        sl_price=long_st.suggested_sl,
                        tp_price=long_st.suggested_tp,
                        magic_number=cb_config.magic_number,
                        comment="ProScalper_BUY",
                    )
                    order_ok, ticket, msg = res if (isinstance(res, tuple) and len(res) == 3) else (False, 0, str(res))
                    if order_ok:
                        self._log(f"✅ {msg}")
                        sess_code2, sess_label2 = classify_session()
                        self._log(f"   🗺️ Session tag: {sess_label2}")
                        storage.record_trade({
                            "order_id": ticket,
                            "symbol": mt5_bridge.symbol,
                            "direction": "BUY",
                            "volume": trade_lot_size,
                            "entry_price": long_st.close_price,
                            "sl": long_st.suggested_sl,
                            "tp": long_st.suggested_tp,
                            "status": "OPEN",
                            "session": sess_code2,
                            "opened_at": datetime.now(timezone.utc).isoformat(),
                        })
                        self._sleep(60)
                    else:
                        self._log(f"❌ Order Failed: {msg}")

                # ================= EXECUTE SELL ORDER =================
                elif short_st.all_passed:
                    if params.enable_htf_filter and htf_trend == "BULLISH":
                        self._log("⚠️ [FILTER BLOCKED] M1 SELL Signal skipped: M15 Macro Trend is BULLISH (Counter-trend protection)")
                        continue

                    self._log(f"\n🎯 >>> ALL CONFLUENCES ALIGNED: EXECUTING SELL ORDER AT ${sym_info.bid:.2f} <<<")
                    self._log(f"   SL: ${short_st.suggested_sl:.2f} (Risk: ${short_st.risk_points:.2f}) | TP: ${short_st.suggested_tp:.2f} (Reward: ${short_st.reward_points:.2f})")

                    res = mt5_bridge.send_order(
                        direction="SELL",
                        volume=trade_lot_size,
                        sl_price=short_st.suggested_sl,
                        tp_price=short_st.suggested_tp,
                        magic_number=cb_config.magic_number,
                        comment="ProScalper_SELL",
                    )
                    order_ok, ticket, msg = res if (isinstance(res, tuple) and len(res) == 3) else (False, 0, str(res))
                    if order_ok:
                        self._log(f"✅ {msg}")
                        sess_code2, sess_label2 = classify_session()
                        self._log(f"   🗺️ Session tag: {sess_label2}")
                        storage.record_trade({
                            "order_id": ticket,
                            "symbol": mt5_bridge.symbol,
                            "direction": "SELL",
                            "volume": trade_lot_size,
                            "entry_price": short_st.close_price,
                            "sl": short_st.suggested_sl,
                            "tp": short_st.suggested_tp,
                            "status": "OPEN",
                            "session": sess_code2,
                            "opened_at": datetime.now(timezone.utc).isoformat(),
                        })
                        self._sleep(60)
                    else:
                        self._log(f"❌ Order Failed: {msg}")

        except Exception as e:
            self.error = str(e)
            self._log(f"❌ Engine crashed: {e}")
        finally:
            self.running = False
            self.status["connected"] = False
            self._log("🛑 Auto-trading engine stopped.")
            try:
                mt5_bridge.disconnect()
            except Exception:
                pass


# ---- process-wide singleton -------------------------------------------
# One engine instance per Python process regardless of how many Streamlit
# browser sessions/tabs are open, so we never accidentally run two live
# trading loops (and place double orders) against the same MT5 account.
_singleton: Optional[LiveTradingEngine] = None
_singleton_lock = threading.Lock()


def get_engine(symbol: str = "XAUUSDm", db_path: str = "live_trades.sqlite") -> LiveTradingEngine:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = LiveTradingEngine(symbol=symbol, db_path=db_path)
        return _singleton
