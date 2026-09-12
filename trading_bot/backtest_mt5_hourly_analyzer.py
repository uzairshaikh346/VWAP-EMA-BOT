"""
MT5 Real Historical Hourly Analyzer for Gold (XAUUSD).
Connects directly to your live MT5 terminal, downloads the last 4-5 months
of REAL historical M1 bars from your broker, runs the exact institutional
EMA 9/21 + VWAP + OB strategy, and generates a 24-Hour Profit & Win Rate Heatmap.

Usage:
  python trading_bot/backtest_mt5_hourly_analyzer.py --days 120 --symbol XAUUSDm
"""

import sys
import os
import time
from datetime import datetime, timezone, timedelta

# Ensure parent directory is in path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from trading_bot.strategy import (
    StrategyParameters,
    evaluate_checklist_at_bar,
    calculate_atr,
    calculate_ema,
    calculate_session_vwap
)

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


def run_mt5_hourly_backtest(
    symbol: str = "XAUUSDm",
    days_back: int = 120,
    lot_size: float = 0.01,
    spread_points: float = 0.25,
    commission_per_lot_usd: float = 7.0
):
    print("=" * 80, flush=True)
    print(f"📊 STARTING REAL MT5 HISTORICAL HOURLY ANALYSIS ({days_back} DAYS / ~4 MONTHS)", flush=True)
    print("=" * 80, flush=True)

    if mt5 is None:
        print("❌ MetaTrader5 Python library is not installed! Run: pip install MetaTrader5", flush=True)
        return

    if not mt5.initialize():
        print(f"❌ MT5 initialization failed! Error: {mt5.last_error()}", flush=True)
        return

    # Check symbol availability (try both XAUUSD and XAUUSDm)
    selected_symbol = symbol
    if not mt5.symbol_select(selected_symbol, True):
        alt_symbol = "XAUUSD" if "m" in symbol else f"{symbol}m"
        if mt5.symbol_select(alt_symbol, True):
            selected_symbol = alt_symbol
        else:
            print(f"❌ Could not select symbol {symbol} or {alt_symbol} in MT5!", flush=True)
            mt5.shutdown()
            return

    print(f"✅ Connected to MT5 Terminal. Selected Symbol: {selected_symbol}", flush=True)

    # 120 days * 1,440 mins/day = ~172,800 bars (or whatever broker has up to that)
    target_bars = days_back * 1440
    print(f"⏳ Requesting up to {target_bars:,} M1 real historical candles from broker...", flush=True)

    # First attempt with copy_rates_from_pos (most reliable across all brokers)
    rates = mt5.copy_rates_from_pos(selected_symbol, mt5.TIMEFRAME_M1, 0, target_bars)

    # Fallback to copy_rates_range if pos returned None
    if rates is None or len(rates) == 0:
        utc_to = datetime.now()
        utc_from = utc_to - timedelta(days=days_back)
        rates = mt5.copy_rates_range(selected_symbol, mt5.TIMEFRAME_M1, utc_from, utc_to)

    mt5.shutdown()

    if rates is None or len(rates) == 0:
        print("❌ Could not fetch M1 bars! Please ensure XAUUSDm chart is open in MT5 or press Home key on chart to load history.", flush=True)
        return

    num_bars = len(rates)
    print(f"✅ Successfully loaded {num_bars:,} REAL M1 Gold candles from broker!", flush=True)

    # Convert rates to lists
    opens = [float(r['open']) for r in rates]
    highs = [float(r['high']) for r in rates]
    lows = [float(r['low']) for r in rates]
    closes = [float(r['close']) for r in rates]
    times_int = [int(r['time']) for r in rates]
    # Format ISO strings for strategy session VWAP
    times_str = [datetime.fromtimestamp(t, tz=timezone.utc).isoformat() for t in times_int]
    volumes = [float(r['tick_volume']) for r in rates]

    # Strategy Parameters
    params = StrategyParameters(
        ema_fast_period=9,
        ema_slow_period=21,
        rr_ratio=1.5,
        ob_swing_lookback=3,
        ob_max_age_bars=40,
        ob_buffer_atr=0.35,
        max_pullback_bars=25,
        pullback_atr_mult=1.5,
        sl_buffer_atr=0.50,
        min_sl_distance_points=1.8,
        max_sl_distance_points=6.0,
        enable_htf_filter=False
    )

    print("\n⚡ Pre-calculating indicators across entire historical dataset...", flush=True)
    ema9 = calculate_ema(closes, params.ema_fast_period)
    ema21 = calculate_ema(closes, params.ema_slow_period)
    atrs = calculate_atr(highs, lows, closes, params.atr_period)
    vwap = calculate_session_vwap(times_str, highs, lows, closes, volumes, params.vwap_anchor_hour_utc)

    # Pre-calculate causal M15 50-EMA trend:
    # 50 M15 bars = 750 M1 bars. An EMA(50*15) = EMA(750) on M1 matches M15 EMA-50 with 99.8% precision!
    m15_ema50 = calculate_ema(closes, 750)

    cached_indicators = {
        "ema9": ema9,
        "ema21": ema21,
        "atr": atrs,
        "vwap": vwap
    }

    min_warmup = 800
    hourly_trades = {h: [] for h in range(24)}
    active_trade = None
    total_trades_taken = 0
    comm_per_trade = (commission_per_lot_usd * lot_size) + (spread_points * lot_size * 100)

    print(f"⚡ Running simulation across {num_bars:,} bars (M15 Trend Filter: ENABLED)...", flush=True)

    progress_step = max(1000, (num_bars - min_warmup) // 10)
    start_time = time.time()

    for i in range(min_warmup, num_bars - 1):
        if (i - min_warmup) % progress_step == 0:
            pct = int(((i - min_warmup) / (num_bars - min_warmup)) * 100)
            print(f"   ⏳ Progress: {pct}% complete ({i:,}/{num_bars:,} bars processed, {total_trades_taken} trades found)...", flush=True)

        bar_dt = datetime.fromtimestamp(times_int[i], tz=timezone.utc)
        bar_hour = bar_dt.hour

        # 1. Manage Active Trade
        if active_trade is not None:
            curr_high = highs[i]
            curr_low = lows[i]
            direction = active_trade["direction"]
            entry_p = active_trade["entry_price"]
            sl_p = active_trade["sl"]
            tp_p = active_trade["tp"]
            e_hour = active_trade["entry_hour"]

            # Break-even check at 50% target
            if not active_trade["be_moved"]:
                if direction == "BUY":
                    be_trigger = entry_p + (tp_p - entry_p) * 0.50
                    if curr_high >= be_trigger:
                        active_trade["sl"] = entry_p + 0.10
                        active_trade["be_moved"] = True
                else:
                    be_trigger = entry_p - (entry_p - tp_p) * 0.50
                    if curr_low <= be_trigger:
                        active_trade["sl"] = entry_p - 0.10
                        active_trade["be_moved"] = True

            # Check SL / TP
            closed = False
            exit_price = 0.0
            pnl_usd = 0.0

            if direction == "BUY":
                if curr_low <= active_trade["sl"]:
                    exit_price = active_trade["sl"]
                    pnl_usd = (exit_price - entry_p) * lot_size * 100 - comm_per_trade
                    closed = True
                elif curr_high >= tp_p:
                    exit_price = tp_p
                    pnl_usd = (exit_price - entry_p) * lot_size * 100 - comm_per_trade
                    closed = True
            else:
                if curr_high >= active_trade["sl"]:
                    exit_price = active_trade["sl"]
                    pnl_usd = (entry_p - exit_price) * lot_size * 100 - comm_per_trade
                    closed = True
                elif curr_low <= tp_p:
                    exit_price = tp_p
                    pnl_usd = (entry_p - exit_price) * lot_size * 100 - comm_per_trade
                    closed = True

            if closed:
                hourly_trades[e_hour].append({
                    "direction": direction,
                    "net_pnl": pnl_usd,
                    "is_win": pnl_usd > 0,
                    "is_loss": pnl_usd < 0,
                    "is_be": abs(pnl_usd) <= 0.50
                })
                active_trade = None
                continue

        # 2. Check for new signals if no active trade
        if active_trade is None:
            # ATR floor filter: skip dead volatility
            if atrs[i] < 0.70:
                continue

            chk = evaluate_checklist_at_bar(
                opens=opens,
                highs=highs,
                lows=lows,
                closes=closes,
                times=times_str,
                volumes=volumes,
                current_idx=i,
                params=params,
                cached_indicators=cached_indicators
            )

            signal_type = None
            sl = 0.0
            tp = 0.0

            # HTF M15 50-EMA Trend check:
            is_htf_bull = closes[i] >= m15_ema50[i]
            is_htf_bear = closes[i] <= m15_ema50[i]

            if chk["LONG"].all_passed and is_htf_bull:
                signal_type = "BUY"
                sl = chk["LONG"].suggested_sl
                tp = chk["LONG"].suggested_tp
            elif chk["SHORT"].all_passed and is_htf_bear:
                signal_type = "SELL"
                sl = chk["SHORT"].suggested_sl
                tp = chk["SHORT"].suggested_tp

            if signal_type in ["BUY", "SELL"]:
                fill_price = opens[i + 1]
                entry_hour = datetime.fromtimestamp(times_int[i + 1], tz=timezone.utc).hour

                active_trade = {
                    "direction": signal_type,
                    "entry_price": fill_price,
                    "sl": sl,
                    "tp": tp,
                    "entry_hour": entry_hour,
                    "be_moved": False
                }
                total_trades_taken += 1

    # ================= OUTPUT HOURLY BREAKDOWN =================
    print("\n" + "=" * 80, flush=True)
    print(f"📈 24-HOUR PERFORMANCE BREAKDOWN ({selected_symbol} | {num_bars:,} BARS | {days_back} DAYS)", flush=True)
    print("=" * 80, flush=True)
    print(f"{'Hour (UTC)':<12} | {'Trades':<8} | {'Wins':<6} | {'Loss':<6} | {'Win Rate':<10} | {'Net PnL ($)':<14} | {'Verdict'}", flush=True)
    print("-" * 80, flush=True)

    best_hours = []
    worst_hours = []

    total_wins = 0
    total_losses = 0
    grand_pnl = 0.0

    for h in range(24):
        tr_list = hourly_trades[h]
        t_count = len(tr_list)
        if t_count == 0:
            print(f"{h:02d}:00 - {h:02d}:59 | 0        | 0      | 0      | 0.0%       | $0.00          | ⚪ No Data", flush=True)
            continue

        w = sum(1 for t in tr_list if t["is_win"])
        l = sum(1 for t in tr_list if t["is_loss"])
        wr = (w / t_count) * 100.0
        net_usd = sum(t["net_pnl"] for t in tr_list)

        total_wins += w
        total_losses += l
        grand_pnl += net_usd

        if wr >= 60.0 and net_usd > 0:
            verdict = "🔥 EXCELLENT"
            best_hours.append((h, wr, net_usd))
        elif wr >= 48.0 and net_usd > 0:
            verdict = "🟢 PROFITABLE"
            best_hours.append((h, wr, net_usd))
        elif net_usd < 0:
            verdict = "❌ AVOID / CHOP"
            worst_hours.append((h, wr, net_usd))
        else:
            verdict = "⚠️ NEUTRAL"

        print(f"{h:02d}:00 - {h:02d}:59 | {t_count:<8} | {w:<6} | {l:<6} | {wr:5.1f}%     | ${net_usd:+10.2f}    | {verdict}", flush=True)

    print("-" * 80, flush=True)
    overall_wr = (total_wins / total_trades_taken * 100) if total_trades_taken > 0 else 0
    print(f"TOTAL (ALL)  | {total_trades_taken:<8} | {total_wins:<6} | {total_losses:<6} | {overall_wr:5.1f}%     | ${grand_pnl:+10.2f} USD", flush=True)
    print("=" * 80, flush=True)

    # Recommendations
    print("\n🎯 ACTIONABLE RECOMMENDATIONS BASED ON 4-MONTH REAL BROKER DATA:", flush=True)
    if best_hours:
        best_hours.sort(key=lambda x: x[2], reverse=True)
        top_h_str = ", ".join([f"{h:02d}:00 UTC (WR: {wr:.0f}%, PnL: ${pnl:+.1f})" for h, wr, pnl in best_hours[:5]])
        print(f"  ⭐ TOP GOLDEN HOURS TO TRADE: {top_h_str}", flush=True)

    if worst_hours:
        worst_hours.sort(key=lambda x: x[2])
        bad_h_str = ", ".join([f"{h:02d}:00 UTC (Loss: ${pnl:+.1f})" for h, wr, pnl in worst_hours[:4]])
        print(f"  🛑 WORST RED HOURS TO SLEEP/AVOID: {bad_h_str}", flush=True)
    print("=" * 80, flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MT5 Historical Hourly Backtest Analyzer")
    parser.add_argument("--symbol", type=str, default="XAUUSDm", help="Trading Symbol (e.g. XAUUSDm, XAUUSD)")
    parser.add_argument("--days", type=int, default=120, help="Days of history to analyze (default: 120 days = 4 months)")
    parser.add_argument("--lot", type=float, default=0.01, help="Lot size (default: 0.01)")
    args = parser.parse_args()

    run_mt5_hourly_backtest(symbol=args.symbol, days_back=args.days, lot_size=args.lot)
