"""
Streamlit Desktop Live Dashboard for XAU/USD Triple Filter Scalper Bot.
Run locally with: streamlit run trading_bot/streamlit_app.py
"""

import os
import sys
from datetime import datetime, timezone
import json

import pandas as pd

# Dedicated SQLite store for the live auto-bot session (kept separate from the
# committed backtest DB `trading_bot_data.sqlite` so only *your* live trades show here).
LIVE_DB_PATH = "live_trades.sqlite"

# Ensure project root is on path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    import streamlit as st
except ImportError:
    st = None

from trading_bot.strategy import (
    StrategyParameters,
    evaluate_checklist_at_bar,
    calculate_ema,
    calculate_session_vwap,
    calculate_atr,
    calculate_sl_tp,
    detect_order_blocks_causal,
    classify_session
)
from trading_bot.backtest import run_causal_backtest
from trading_bot.circuit_breakers import CircuitBreakerConfig, CircuitBreakerManager
from trading_bot.storage import BotStorage
from trading_bot.mt5_bridge import MT5Bridge
from trading_bot.data_feed import generate_realistic_gold_data
from trading_bot.live_engine import get_engine


# ============================================================================
# DESIGN SYSTEM
# One small, consistent token set (colors / spacing / radius) reused across
# every widget override below, so the whole app reads as one product instead
# of a stack of default Streamlit blocks. Paired with .streamlit/config.toml.
# ============================================================================
_CSS = """
<style>
:root{
  --bg:#0B0E14; --bg-card:#121722; --bg-card-2:#161c29;
  --border: rgba(255,255,255,.08);
  --text:#E8ECF3; --text-muted:#8C94A6;
  --accent:#D4A24E; --accent-soft: rgba(212,162,78,.14);
  --success:#34C77B; --success-soft: rgba(52,199,123,.13);
  --danger:#F0576B; --danger-soft: rgba(240,87,107,.13);
  --radius: 12px;
}

.block-container{ padding-top:2rem !important; padding-bottom:3rem !important; max-width:1180px; }
footer{ visibility:hidden; height:0; }
[data-testid="stDecoration"]{ background:linear-gradient(90deg,var(--accent),transparent); }

h1,h2,h3,h4{ letter-spacing:-0.01em; font-weight:650 !important; }

/* ---- header ---- */
.app-title{ font-size:1.45rem; font-weight:700; line-height:1.2; color:var(--text); }
.app-sub{ display:block; font-size:.8rem; color:var(--text-muted); font-weight:500; margin-top:.15rem; }

/* ---- status pill ---- */
.pill-wrap{ text-align:center; padding-top:.55rem; }
.pill{ display:inline-flex; align-items:center; gap:.4rem; padding:.32rem .8rem; border-radius:999px; font-size:.8rem; font-weight:650; }
.pill-run{ background:var(--success-soft); color:var(--success); }
.pill-stop{ background:rgba(140,148,166,.14); color:var(--text-muted); }
.pill-err{ background:var(--danger-soft); color:var(--danger); }

/* ---- pass/fail chips ---- */
.setup-head{ font-size:1.02rem; font-weight:700; margin-bottom:.5rem; }
.setup-head.buy{ color:var(--success); }
.setup-head.sell{ color:var(--danger); }
.chip{ display:inline-block; padding:.3rem .65rem; margin:0 .3rem .35rem 0; border-radius:999px; font-size:.76rem; font-weight:650; }
.chip-pass{ background:var(--success-soft); color:var(--success); }
.chip-fail{ background:rgba(140,148,166,.10); color:var(--text-muted); }

/* ---- metric cards ---- */
[data-testid="stMetric"]{
  background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius);
  padding:.8rem 1rem .65rem; height:100px; overflow:hidden;
  display:flex; flex-direction:column; justify-content:center;
}
[data-testid="stMetricLabel"]{ color:var(--text-muted) !important; font-size:.7rem; text-transform:uppercase; letter-spacing:.06em; }
[data-testid="stMetricValue"]{ font-size:1.3rem; font-weight:700; }
[data-testid="stMetricDelta"]{ font-size:.76rem; }

/* ---- buttons ---- */
.stButton>button{ border-radius:9px; font-weight:650; border:1px solid var(--border); }
.stButton>button[kind="primary"]{ background:var(--accent); border-color:var(--accent); color:#171207; }
.stButton>button[kind="primary"]:hover{ filter:brightness(1.08); }
.stDownloadButton>button{ border-radius:9px; font-weight:600; }

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"]{ gap:2px; border-bottom:1px solid var(--border); }
.stTabs [data-baseweb="tab"]{ height:38px; padding:0 14px; color:var(--text-muted); font-weight:600; font-size:.85rem; }
.stTabs [aria-selected="true"]{ color:var(--text) !important; }

/* ---- sidebar ---- */
[data-testid="stSidebar"]{ border-right:1px solid var(--border); }
[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }

/* ---- expanders as cards ---- */
[data-testid="stExpander"]{ border:1px solid var(--border); border-radius:var(--radius); background:var(--bg-card); }

/* ---- dataframes ---- */
[data-testid="stDataFrame"]{ border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; }

/* ---- alerts, quieter ---- */
[data-testid="stAlert"]{ border-radius:var(--radius); border:1px solid var(--border); }

/* ---- captions, muted and compact ---- */
[data-testid="stCaptionContainer"]{ color:var(--text-muted) !important; }

/* ---- engine log: real console look, monospace so tree chars line up ---- */
[data-testid="stTextArea"] textarea{
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
  font-size:.78rem !important; line-height:1.5;
  background:#0d1017 !important; color:#c9d1e0 !important;
  border-radius:var(--radius) !important; border-color:var(--border) !important;
}
</style>
"""


def _inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def _status_pill(engine) -> str:
    if engine.is_running():
        cls, text = "pill-run", "● Running"
    elif engine.error:
        cls, text = "pill-err", "● Crashed"
    else:
        cls, text = "pill-stop", "● Stopped"
    return f'<div class="pill-wrap"><span class="pill {cls}">{text}</span></div>'


def _chip(label: str, passed: bool) -> str:
    cls = "chip-pass" if passed else "chip-fail"
    icon = "✓" if passed else "·"
    return f'<span class="chip {cls}">{icon} {label}</span>'


@st.fragment(run_every=5) if st is not None else (lambda f: f)
def _render_header(mt5_bridge, engine, cb_manager):
    """Title + auto-bot status/toggle + account/price/P&L/session strip.
    Its own fragment (re-executes every 5s) so a trade the engine just placed -
    or the broker just closed on its side - shows up here within a few
    seconds instead of needing a manual page refresh."""
    hc1, hc2, hc3 = st.columns([4, 1.5, 1.5])
    with hc1:
        st.markdown(
            '<div class="app-title">🏆 XAU/USD Scalper</div>'
            '<span class="app-sub">EMA 9/21 · VWAP · Order Blocks · M1</span>',
            unsafe_allow_html=True
        )
    with hc2:
        st.markdown(_status_pill(engine), unsafe_allow_html=True)
    with hc3:
        if engine.is_running():
            if st.button("⏹ Stop Bot", key="btn_stop_engine_top", width="stretch"):
                ok_stop, msg_stop = engine.stop()
                st.toast(msg_stop)
                st.rerun()
        else:
            if st.button("▶ Start Bot", key="btn_start_engine_top", width="stretch", type="primary"):
                ok_start, msg_start = engine.start()
                st.toast(msg_start)
                st.rerun()

    if engine.error:
        st.error(f"Engine error: {engine.error}")

    acc = mt5_bridge.get_account_info()
    if hasattr(mt5_bridge, "is_algo_trading_enabled"):
        algo_enabled = mt5_bridge.is_algo_trading_enabled()
    elif hasattr(mt5_bridge, "is_algo_trading_allowed"):
        algo_enabled = mt5_bridge.is_algo_trading_allowed()
    else:
        algo_enabled = True
    sym_info = mt5_bridge.get_symbol_info()
    sess_code_now, _sess_label_now = classify_session()

    today_pnl_display = engine.status.get("today_pnl") if engine.status.get("last_update") else cb_manager.state.daily_pnl_usd

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Account", acc.trade_mode, "Demo" if acc.is_demo else "LIVE — blocked")
    m2.metric("Balance", f"${acc.balance:,.2f}")
    m3.metric(mt5_bridge.symbol, f"${sym_info.bid:,.2f}", f"spread ${sym_info.spread_usd:.2f}")
    m4.metric("Today P&L", f"${today_pnl_display:+,.2f}")
    m5.metric("Positions", engine.status.get("open_positions", 0))
    m6.metric("Session", engine.status.get("session_code") or sess_code_now)

    return acc, sym_info, algo_enabled, sess_code_now


@st.fragment(run_every=8) if st is not None else (lambda f: f)
def _render_trade_history(storage, magic_num):
    """Trade log + P&L table. Its own fragment (re-executes every 8s) so a
    newly opened/closed trade appears without a manual page refresh."""
    st.caption(
        f"Store: `{storage.db_path}`  ·  Magic #{magic_num}  ·  "
        "a row appears the moment the engine opens a position; exit price & P&L fill in on close."
    )

    raw_trades = storage.get_all_trades(1000)

    if not raw_trades:
        st.info("No trades recorded yet in this store. Start the Auto-Bot, or use Manual Override, to see history here.")
        return

    df = pd.DataFrame(raw_trades)
    for col in ["net_pnl_usd", "pnl_r_multiple", "entry_price", "stop_loss",
                "take_profit", "exit_price", "lot_size"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["net_pnl_usd"] = df["net_pnl_usd"].fillna(0.0)

    def _is_closed(x):
        return x is not None and not pd.isna(x) and float(x) != 0.0
    df["status"] = df["exit_price"].apply(lambda x: "CLOSED" if _is_closed(x) else "OPEN")

    df = df.sort_values("id")  # oldest -> newest for cumulative math
    df["cumulative_pnl_usd"] = 0.0
    closed_mask = df["status"] == "CLOSED"
    df.loc[closed_mask, "cumulative_pnl_usd"] = df.loc[closed_mask, "net_pnl_usd"].cumsum()
    df["cumulative_pnl_usd"] = df["cumulative_pnl_usd"].ffill().fillna(0.0)

    closed = df[closed_mask]
    wins = closed[closed["net_pnl_usd"] > 0]
    losses = closed[closed["net_pnl_usd"] < 0]
    total_pnl = float(closed["net_pnl_usd"].sum())
    win_rate = (len(wins) / len(closed) * 100.0) if len(closed) else 0.0
    gross_win = float(wins["net_pnl_usd"].sum())
    gross_loss = abs(float(losses["net_pnl_usd"].sum()))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0.0
    avg_win = float(wins["net_pnl_usd"].mean()) if len(wins) else 0.0
    avg_loss = float(losses["net_pnl_usd"].mean()) if len(losses) else 0.0
    best = float(closed["net_pnl_usd"].max()) if len(closed) else 0.0
    worst = float(closed["net_pnl_usd"].min()) if len(closed) else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Trades", len(df), f"{int((df['status'] == 'OPEN').sum())} open")
    k2.metric("Win Rate", f"{win_rate:.1f}%", f"{len(wins)}W / {len(losses)}L")
    k3.metric("Net P&L", f"${total_pnl:+,.2f}")
    k4.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor else "—")
    k5.metric("Closed", len(closed))

    with st.expander("More stats"):
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Avg Win", f"${avg_win:+,.2f}")
        e2.metric("Avg Loss", f"${avg_loss:+,.2f}")
        e3.metric("Best", f"${best:+,.2f}")
        e4.metric("Worst", f"${worst:+,.2f}")
        st.caption(f"Gross Win ${gross_win:,.2f}  ·  Gross Loss ${gross_loss:,.2f}")

    if len(closed) >= 1:
        st.markdown("**Cumulative Realized P&L ($)**")
        st.line_chart(closed.set_index("id")["cumulative_pnl_usd"], height=200)

    # ---- Per-session P&L breakdown (Asia vs London vs Overlap vs New York) ----
    with st.expander("🗺️ Performance by Trading Session", expanded=True):
        st.caption("London/Overlap are recorded, not blocked, during the test phase — check back after a few weeks.")
        SESSION_ORDER = ["ASIA", "LONDON", "OVERLAP", "NEWYORK", "LATE"]
        SESSION_LABEL = {
            "ASIA": "Asian 00-08 UTC (PKT 05-13)",
            "LONDON": "London 08-13 UTC (PKT 13-18)",
            "OVERLAP": "London/NY 13-16 UTC (PKT 18-21)",
            "NEWYORK": "New York 16-22 UTC (PKT 21-03)",
            "LATE": "Late 22-00 UTC (PKT 03-05)",
        }
        df["session"] = df["session"].fillna("UNTAGGED")
        sess_rows = []
        for code in SESSION_ORDER + sorted(set(df["session"]) - set(SESSION_ORDER)):
            grp = df[df["session"] == code]
            if grp.empty:
                continue
            g_closed = grp[grp["status"] == "CLOSED"]
            g_wins = g_closed[g_closed["net_pnl_usd"] > 0]
            g_pnl = float(g_closed["net_pnl_usd"].sum())
            sess_rows.append({
                "Session": SESSION_LABEL.get(code, code),
                "Trades": len(grp),
                "Closed": len(g_closed),
                "Win %": round(len(g_wins) / len(g_closed) * 100, 1) if len(g_closed) else 0.0,
                "Net P&L ($)": round(g_pnl, 2),
                "Avg / Trade ($)": round(g_closed["net_pnl_usd"].mean(), 2) if len(g_closed) else 0.0,
            })
        if sess_rows:
            sess_df = pd.DataFrame(sess_rows)
            st.dataframe(
                sess_df.style.map(
                    lambda v: ("color: #34C77B; font-weight: 600" if isinstance(v, (int, float)) and v > 0
                               else "color: #F0576B; font-weight: 600" if isinstance(v, (int, float)) and v < 0
                               else ""),
                    subset=["Net P&L ($)", "Avg / Trade ($)"],
                ),
                width="stretch", hide_index=True,
            )
        else:
            st.caption("No closed trades yet to break down by session.")

    view = df.sort_values("id", ascending=False)

    def _clean_ts(series):
        return (series.fillna("").astype(str)
                .str.replace("T", " ", regex=False).str.slice(0, 19))

    disp = pd.DataFrame({
        "Ticket": view["ticket"],
        "Dir": view["direction"],
        "Session": view["session"],
        "Status": view["status"],
        "Entry Time (UTC)": _clean_ts(view["entry_time"]),
        "Entry": view["entry_price"].round(3),
        "SL": view["stop_loss"].round(3),
        "TP": view["take_profit"].round(3),
        "Lot": view["lot_size"],
        "Exit Time (UTC)": _clean_ts(view["exit_time"]),
        "Exit": view["exit_price"].round(3),
        "Net P&L ($)": view["net_pnl_usd"].round(2),
        "R": view["pnl_r_multiple"].round(2),
        "Cum P&L ($)": view["cumulative_pnl_usd"].round(2),
        "Reason": view["exit_reason"].fillna(""),
    })

    def _color_pnl(v):
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return ""
        if fv > 0:
            return "color: #34C77B; font-weight: 600"
        if fv < 0:
            return "color: #F0576B; font-weight: 600"
        return "color: #8C94A6"

    styled = disp.style.map(_color_pnl, subset=["Net P&L ($)", "Cum P&L ($)", "R"])
    st.dataframe(styled, width="stretch", hide_index=True, height=400)

    st.download_button(
        "⬇️ Download CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"live_trades_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        key="btn_download_trades",
    )

    with st.expander("🐞 Raw rows (debug JSON)"):
        st.json(raw_trades[:50])


@st.fragment(run_every=5) if st is not None else (lambda f: f)
def _render_engine_live(engine):
    """Auto-updating diagnostics + log panel. Runs as an isolated Streamlit
    fragment (re-executes itself every 5s) instead of the old blocking
    time.sleep()+st.rerun() loop, which was forcing full-page reruns often
    enough to catch the browser mid-reconcile and render a duplicate/ghost
    frame of the whole page."""
    if engine.status.get("last_update"):
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Price", f"${engine.status.get('last_price', 0.0):.2f}")
        d2.metric("ATR", f"${engine.status.get('atr', 0.0):.2f}")
        d3.metric("ADX", f"{engine.status.get('adx', 0.0):.1f}")
        d4.metric("M15 Trend", engine.status.get("htf_trend", "—"))
        d5.metric("Updated", engine.status.get("last_update").strftime("%H:%M:%S"))

        chips = "".join([
            _chip(f"BUY {engine.status.get('buy_passed', 0)}/5", engine.status.get("buy_passed", 0) == 5),
            _chip(f"SELL {engine.status.get('sell_passed', 0)}/5", engine.status.get("sell_passed", 0) == 5),
        ])
        st.markdown(chips, unsafe_allow_html=True)

        if engine.status.get("news_freeze"):
            st.warning(f"📰 News shield active: {engine.status.get('news_reason', '')}")
    else:
        st.info("Setup diagnostics appear here a few seconds after you press Start.")

    st.markdown("**Live log**  <span style='font-size:.75rem;color:var(--text-muted);'>· updates every 5s</span>", unsafe_allow_html=True)
    log_text = "\n".join(engine.log_lines) if engine.log_lines else "(no log lines yet — press Start)"
    st.text_area("Engine log", value=log_text, height=380,
                 disabled=True, key="engine_log_area", label_visibility="collapsed")


def main():
    if st is None:
        print("Streamlit is not installed. Install via: pip install streamlit")
        return

    st.set_page_config(
        page_title="XAU/USD Scalper",
        page_icon="🏆",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    _inject_css()

    # Initialize persistence and managers in session state
    if "storage" not in st.session_state:
        st.session_state.storage = BotStorage(LIVE_DB_PATH)
    if "cb_manager" not in st.session_state:
        cb_cfg = CircuitBreakerConfig(bypass_noise_gate_for_demo=True)
        st.session_state.cb_manager = CircuitBreakerManager(config=cb_cfg)
    if "mt5_bridge" not in st.session_state or not hasattr(st.session_state.mt5_bridge, "get_rates"):
        st.session_state.mt5_bridge = MT5Bridge(symbol="XAUUSDm")
        st.session_state.mt5_bridge.connect()

    storage = st.session_state.storage
    cb_manager = st.session_state.cb_manager
    # Ensure noise gate bypass is always active for demo testing
    cb_manager.config.bypass_noise_gate_for_demo = True
    mt5_bridge = st.session_state.mt5_bridge

    # ================= HEADER: title + auto-bot status/toggle + live status strip =================
    # One background thread per process runs the live trading loop (see
    # trading_bot/live_engine.py) - start/stop it here instead of running a
    # separate script. Rendered as a fragment (see _render_header) that
    # re-executes itself every 5s, so a trade shows up here within seconds
    # instead of needing a manual page refresh.
    engine = get_engine(symbol="XAUUSDm", db_path=LIVE_DB_PATH)
    acc, sym_info, algo_enabled, sess_code_now = _render_header(mt5_bridge, engine, cb_manager)

    # SIDEBAR: Parameters & Safety Controls, persisted to the `settings` table in
    # live_trades.sqlite (bot config) so they survive a restart instead of resetting
    # to hardcoded defaults every time.
    saved_strategy = storage.get_setting("strategy_config", {}) or {}
    saved_safety = storage.get_setting("safety_config", {}) or {}

    st.sidebar.markdown("### ⚙️ Controls")
    st.sidebar.caption("Saved automatically — persists across restarts.")
    with st.sidebar.expander("Strategy Parameters", expanded=False):
        ema_fast = st.number_input("EMA Fast Period", 3, 50, int(saved_strategy.get("ema_fast_period", 9)))
        ema_slow = st.number_input("EMA Slow Period", 5, 200, int(saved_strategy.get("ema_slow_period", 21)))
        vwap_options = [0, 7, 13]
        saved_vwap = saved_strategy.get("vwap_anchor_hour_utc", 0)
        vwap_hour = st.selectbox("VWAP Reset (UTC Hour)", vwap_options,
                                  index=vwap_options.index(saved_vwap) if saved_vwap in vwap_options else 0,
                                  help="00:00 UTC Daily Open")
        ob_swing_lb = st.number_input("OB Swing Lookback (Pivots)", 2, 20, int(saved_strategy.get("ob_swing_lookback", 3)))
        ob_max_age = st.number_input("OB Max Age (Bars)", 10, 100, int(saved_strategy.get("ob_max_age_bars", 60)))
        max_pb_bars = st.number_input("Max Pullback Bars Post-Cross", 3, 50, int(saved_strategy.get("max_pullback_bars", 35)))
        pb_atr_mult = st.slider("Pullback Proximity (x ATR)", 0.2, 3.0, float(saved_strategy.get("pullback_atr_mult", 1.8)), 0.1)
        rr_ratio = st.number_input("Risk:Reward Ratio", 1.0, 5.0, float(saved_strategy.get("rr_ratio", 1.5)), 0.5)
        sl_lookback = st.number_input("SL Swing Lookback", 3, 30, int(saved_strategy.get("sl_lookback_bars", 8)))
        sl_buffer = st.slider("SL Buffer (x ATR)", 0.0, 1.0, float(saved_strategy.get("sl_buffer_atr", 0.20)), 0.05)

    params = StrategyParameters(
        ema_fast_period=ema_fast,
        ema_slow_period=ema_slow,
        vwap_anchor_hour_utc=vwap_hour,
        ob_swing_lookback=ob_swing_lb,
        ob_max_age_bars=ob_max_age,
        max_pullback_bars=max_pb_bars,
        pullback_atr_mult=pb_atr_mult,
        rr_ratio=rr_ratio,
        sl_lookback_bars=sl_lookback,
        sl_buffer_atr=sl_buffer
    )

    current_strategy_cfg = {
        "ema_fast_period": ema_fast, "ema_slow_period": ema_slow, "vwap_anchor_hour_utc": vwap_hour,
        "ob_swing_lookback": ob_swing_lb, "ob_max_age_bars": ob_max_age, "max_pullback_bars": max_pb_bars,
        "pullback_atr_mult": pb_atr_mult, "rr_ratio": rr_ratio, "sl_lookback_bars": sl_lookback,
        "sl_buffer_atr": sl_buffer,
    }
    if current_strategy_cfg != saved_strategy:
        storage.set_setting("strategy_config", current_strategy_cfg)

    with st.sidebar.expander("Safety & Circuit Breakers", expanded=False):
        max_daily_loss = st.number_input("Max Daily Loss ($)", 50.0, 1000.0, float(saved_safety.get("max_daily_loss_usd", 200.0)))
        max_consec_losses = st.number_input("Max Consec Losses", 1, 10, int(saved_safety.get("max_consecutive_losses", 3)))
        magic_num = st.number_input("Magic Number", 100000, 9999999, int(saved_safety.get("magic_number", 9212001)))

    cb_manager.config.max_daily_loss_usd = max_daily_loss
    cb_manager.config.max_consecutive_losses = max_consec_losses
    cb_manager.config.magic_number = magic_num

    current_safety_cfg = {
        "max_daily_loss_usd": max_daily_loss, "max_consecutive_losses": max_consec_losses,
        "magic_number": magic_num,
    }
    if current_safety_cfg != saved_safety:
        storage.set_setting("safety_config", current_safety_cfg)

    st.sidebar.button("🔄 Refresh Market Data", key="btn_refresh_market_data", width="stretch",
                       on_click=st.rerun)

    # 1. Fetch LIVE Rates directly from MT5
    raw_bars = mt5_bridge.get_rates(count=150)
    opens = [b.open for b in raw_bars]
    highs = [b.high for b in raw_bars]
    lows = [b.low for b in raw_bars]
    closes = [b.close for b in raw_bars]
    times = [b.time for b in raw_bars]
    volumes = [b.tick_volume for b in raw_bars]

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Checklist", "📊 Backtest", "📈 Market", "📜 History", "🤖 Engine"
    ])

    # Evaluate current bar checklist on LIVE MT5 data
    curr_idx = len(closes) - 1
    checklist = evaluate_checklist_at_bar(
        opens, highs, lows, closes,
        times, volumes, curr_idx, params
    )
    long_st = checklist["LONG"]
    short_st = checklist["SHORT"]

    with tab1:
        if not cb_manager.state.noise_gate_verified:
            st.caption(f"ℹ️ Demo bypass active — noise gate not required to trade (p={cb_manager.state.noise_gate_p_value:.4f}).")
        else:
            st.caption(f"✅ Noise gate passed (p={cb_manager.state.noise_gate_p_value:.4f}).")

        def _render_setup(col, setup, label, css_cls):
            with col:
                st.markdown(f'<div class="setup-head {css_cls}">{label} · ${setup.close_price:.2f}</div>', unsafe_allow_html=True)
                chips = "".join([
                    _chip("VWAP", setup.vwap_pass),
                    _chip("Cross", setup.crossover_pass),
                    _chip("OB", setup.ob_pass),
                    _chip("Pullback", setup.pullback_pass),
                    _chip("Candle", setup.confirmation_pass),
                ])
                st.markdown(chips, unsafe_allow_html=True)

                if setup.all_passed:
                    st.success(f"All 5 criteria met — Entry ${setup.suggested_entry:.2f} · SL ${setup.suggested_sl:.2f} · TP ${setup.suggested_tp:.2f}")
                else:
                    st.caption(f"SL ${setup.suggested_sl:.2f}  ·  TP ({params.rr_ratio}R) ${setup.suggested_tp:.2f}")

                with st.expander("Why?"):
                    st.caption(f"**VWAP** — {setup.vwap_detail}")
                    st.caption(f"**Crossover** — {setup.crossover_detail}")
                    st.caption(f"**Order Block** — {setup.ob_detail}")
                    st.caption(f"**Pullback** — {setup.pullback_detail}")
                    st.caption(f"**Candle** ({setup.pattern_name}) — {setup.confirmation_detail}")

        c_long, c_short = st.columns(2)
        _render_setup(c_long, long_st, "🟢 BUY", "buy")
        _render_setup(c_short, short_st, "🔴 SELL", "sell")

        cb_manager.config.bypass_noise_gate_for_demo = True
        can_trade, reason = cb_manager.can_open_trade(
            is_demo_account=acc.is_demo if hasattr(acc, "is_demo") else True,
            algo_trading_enabled=algo_enabled,
            current_balance=acc.balance
        )

        with st.expander("⚡ Manual Order Override", expanded=False):
            st.caption("Places a one-off order at the strategy's current SL/TP — independent of the Auto-Bot toggle above.")
            col_b1, col_b2, col_b3 = st.columns(3)

            with col_b1:
                if st.button("🚀 BUY Now", key="btn_trigger_buy_order_main", type="primary", width="stretch"):
                    ok, ticket, msg = mt5_bridge.send_order(
                        direction="BUY",
                        volume=0.10,
                        sl_price=long_st.suggested_sl,
                        tp_price=long_st.suggested_tp,
                        magic_number=magic_num,
                        comment="TripleFilter_BUY"
                    )
                    if ok:
                        st.success(msg)
                        storage.record_trade({
                            "order_id": ticket,
                            "symbol": mt5_bridge.symbol,
                            "direction": "BUY",
                            "volume": 0.10,
                            "entry_price": long_st.close_price,
                            "sl": long_st.suggested_sl,
                            "tp": long_st.suggested_tp,
                            "status": "OPEN",
                            "session": classify_session()[0],
                            "opened_at": datetime.now(timezone.utc).isoformat()
                        })
                    else:
                        st.error(msg)

            with col_b2:
                if st.button("🔻 SELL Now", key="btn_trigger_sell_order_main", width="stretch"):
                    ok, ticket, msg = mt5_bridge.send_order(
                        direction="SELL",
                        volume=0.10,
                        sl_price=short_st.suggested_sl,
                        tp_price=short_st.suggested_tp,
                        magic_number=magic_num,
                        comment="TripleFilter_SELL"
                    )
                    if ok:
                        st.success(msg)
                        storage.record_trade({
                            "order_id": ticket,
                            "symbol": mt5_bridge.symbol,
                            "direction": "SELL",
                            "volume": 0.10,
                            "entry_price": short_st.close_price,
                            "sl": short_st.suggested_sl,
                            "tp": short_st.suggested_tp,
                            "status": "OPEN",
                            "session": classify_session()[0],
                            "opened_at": datetime.now(timezone.utc).isoformat()
                        })
                    else:
                        st.error(msg)

            with col_b3:
                if cb_manager.state.is_consec_loss_tripped or cb_manager.state.is_daily_loss_tripped:
                    if st.button("🔄 Reset Circuit Breakers", key="btn_reset_circuit_breakers_main", width="stretch"):
                        cb_manager.manual_reset_consecutive_losses()
                        st.success("Circuit breakers reset!")
                        st.rerun()

            if not can_trade:
                st.warning(f"Guardrail active: {reason}")

    with tab2:
        st.caption("Zero-lookahead backtest, In-Sample (75%) vs Out-of-Sample (25%), 100-shuffle Monte Carlo noise test.")

        bt_bars = st.slider("Historical Bars to Test", 500, 3000, 1500, 100, key="slider_bt_bars")
        if st.button("▶️ Run Backtest & Gate Check", key="btn_run_full_backtest", type="primary"):
            with st.spinner("Running causal simulation and permutation tests..."):
                bt_data = generate_realistic_gold_data(num_bars=bt_bars, seed=101)
                res = run_causal_backtest(
                    bt_data["opens"], bt_data["highs"], bt_data["lows"], bt_data["closes"],
                    bt_data["times"], bt_data["volumes"], params,
                    initial_balance=10000.0, split_ratio=0.75, spread_points=sym_info.spread_usd,
                    num_noise_shuffles=100
                )
                st.session_state.bt_result = res
                cb_manager.set_noise_gate_status(
                    res.overall_metrics.noise_gate_passed,
                    res.overall_metrics.noise_p_value
                )

        if "bt_result" in st.session_state:
            res = st.session_state.bt_result

            m_is = res.in_sample_metrics
            m_oos = res.out_of_sample_metrics
            m_all = res.overall_metrics

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**📘 In-Sample (75%)**")
                st.metric("Trades", m_is.total_trades)
                st.metric("Win Rate", f"{m_is.win_rate_pct:.1f}%")
                st.metric("Profit Factor", m_is.profit_factor)
                st.metric("Expectancy (R)", f"{m_is.expectancy_r:+.2f}R")
                st.metric("Net PnL", f"${m_is.total_net_pnl_usd:+,.2f}")
                st.metric("Max Drawdown", f"${m_is.max_drawdown_usd:,.2f} ({m_is.max_drawdown_pct:.1f}%)")

            with c2:
                st.markdown("**📙 Out-of-Sample (25%)**")
                st.metric("Trades", m_oos.total_trades)
                st.metric("Win Rate", f"{m_oos.win_rate_pct:.1f}%")
                st.metric("Profit Factor", m_oos.profit_factor)
                st.metric("Expectancy (R)", f"{m_oos.expectancy_r:+.2f}R")
                st.metric("Net PnL", f"${m_oos.total_net_pnl_usd:+,.2f}")
                st.metric("Max Drawdown", f"${m_oos.max_drawdown_usd:,.2f} ({m_oos.max_drawdown_pct:.1f}%)")

            with c3:
                st.markdown("**🌐 Overall**")
                st.metric("Trades", m_all.total_trades)
                st.metric("Win Rate", f"{m_all.win_rate_pct:.1f}%")
                st.metric("Profit Factor", m_all.profit_factor)
                st.metric("Expectancy (R)", f"{m_all.expectancy_r:+.2f}R")
                st.metric("Net PnL", f"${m_all.total_net_pnl_usd:+,.2f}")
                st.metric("Noise Gate p-value", f"{m_all.noise_p_value:.4f}")

            if m_all.noise_gate_passed:
                st.success(f"🎉 Strategy passed the noise gate (p = {m_all.noise_p_value:.4f} ≤ 0.05, Z = {m_all.z_score:.2f})")
            else:
                st.error(f"🛑 Strategy failed the noise gate (p = {m_all.noise_p_value:.4f} > 0.05) — edge not distinguishable from noise.")

    with tab3:
        st.caption("Latest indicator values on the live M1 feed.")
        ema9_vals = calculate_ema(closes, 9)
        ema21_vals = calculate_ema(closes, 21)
        vwap_vals = calculate_session_vwap(times, highs, lows, closes, volumes, params.vwap_anchor_hour_utc)

        with st.container(border=True):
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("Close", f"${closes[-1]:.2f}")
            i2.metric("EMA 9", f"${ema9_vals[-1]:.2f}")
            i3.metric("EMA 21", f"${ema21_vals[-1]:.2f}")
            i4.metric("VWAP", f"${vwap_vals[-1]:.2f}")

    with tab4:
        _render_trade_history(storage, magic_num)

    with tab5:
        # Status, balance, positions & session are already live in the header strip above,
        # and Start/Stop lives there too - this tab only shows what's unique to it: setup
        # diagnostics and the log.
        if engine.is_running() and engine.started_at:
            st.caption(f"Running since {engine.started_at.strftime('%H:%M:%S')} UTC")
        elif engine.error:
            st.caption(f"⚠️ Last error: {engine.error}")
        else:
            st.caption("Stopped — use ▶ Start Bot at the top of the page to begin trading.")

        _render_engine_live(engine)

if __name__ == "__main__":
    main()
