# Project Handoff

**Purpose of this file:** a single, growing source of truth for this project that travels *with the repo* — so a Claude Code session on a different machine (or a future session on this one) has full context without re-deriving it. Claude's own memory (`~/.claude/projects/.../memory/`) is local to one machine and does not follow you to the office laptop; this file does, once pushed.

**How this file should grow:** the reference sections (1-8) describe the *current state* and get edited in place as things change. Section 9, **Session Log**, is append-only — every work session adds one dated entry there instead of rewriting history. If something in sections 1-8 turns out to be wrong or stale, fix it in place and note the correction in that day's session log entry.

---

## 1. What this project is

A local, semi-automated scalping bot for **XAU/USD (Gold)** on MetaTrader 5, M1 timeframe. Two parts:

- **Strategy engine** — a 5-step causal checklist (session-anchored VWAP trend filter → EMA 9/21 crossover → causal Order Block reaction → pullback to EMA → confirmation candlestick), zero-lookahead backtester with Monte Carlo noise-gate, and a live auto-trading loop with several risk shields (daily profit lock, circuit breakers, session/news/chop filters).
- **Streamlit dashboard** — live checklist view, backtest runner, trade history with P&L, and Start/Stop control for the live engine.

Currently running against a **DEMO** account only, in an active **live-test phase** (see §5) — not yet validated for real money.

## 2. Architecture / file map

```
trading_bot/
  strategy.py          Indicators (EMA/VWAP/ATR/ADX), Order Blocks, 5-step checklist,
                        classify_session() (Asia/London/Overlap/NY/Late tagging)
  backtest.py           Causal backtest engine, Monte Carlo noise gate
  circuit_breakers.py   CircuitBreakerConfig/Manager — daily loss & consecutive-loss guards
  mt5_bridge.py         MetaTrader5 connector (falls back to a simulator off-Windows)
  storage.py            BotStorage — SQLite: trades / settings / bot_logs tables
  news_filter.py        ForexFactory high-impact news freeze window
  data_feed.py           Synthetic gold data generator, used by the Backtest tab
  live_engine.py         LiveTradingEngine — the actual live trading loop, runs on a
                         background daemon thread, process-wide singleton (get_engine())
  run_live_auto_bot.py   Thin CLI wrapper around live_engine.py, for no-UI/headless use only
  streamlit_app.py       The dashboard — imports live_engine.get_engine(), everything else
  tests/                 15 unit tests (run_tests.py) — indicators, backtest, circuit breakers
.streamlit/config.toml   Dark theme + gold accent (paired with CSS tokens in streamlit_app.py)
backups/                 Dated SQLite snapshots — see backups/README.md
live_trades.sqlite       Live trade history + saved dashboard config (git-ignored, see §4)
trading_bot_data.sqlite  Older, already-committed DB from before live_trades.sqlite existed
```

**Key design point:** `run_live_auto_bot.py` and `streamlit_app.py` both drive the *same* `LiveTradingEngine` instance (a singleton keyed by process). You never need two terminals — one command (`streamlit run trading_bot/streamlit_app.py`) starts MT5 + dashboard, and a ▶ **Start Bot** button in the dashboard starts the actual trading loop on a background thread inside that same process.

## 3. How to run

```bash
python -m streamlit run trading_bot/streamlit_app.py
```

Opens at **http://localhost:8501**. MT5 auto-launches (via `mt5.initialize()`) the moment a browser tab actually loads the page — a headless server start alone doesn't trigger it. The auto-bot is **off by default**; press ▶ Start Bot (top of the page, or the Engine tab) to begin trading.

- **MT5 terminal:** `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe` (this machine only — will differ on the office laptop, needs its own MT5 EXNESS install + demo login).
- **Account:** login `472544446`, server `Exness-MT5Trial16`, **DEMO**, ~$100-103 balance, leverage 1:2000.
- **Symbol:** `XAUUSDm` (note the Exness `m` suffix — plain `XAUUSD` doesn't exist on this broker).
- **Python:** 3.14, no venv — all deps (`pandas`, `numpy`, `streamlit`, `MetaTrader5`, `plotly`, `scipy`) installed globally. `pip install -r requirements.txt` on a fresh machine.
- **Gotcha:** if you ever run `run_live_auto_bot.py` standalone (not through the dashboard) in a plain Windows console, set `PYTHONUTF8=1` first — the emoji-heavy log lines crash on the default cp1252 console codec otherwise. The dashboard path doesn't need this (its `_log()` swallows the encode error).

## 4. Data & backups

Two SQLite DBs, same schema (`trades` / `settings` / `bot_logs`, see `storage.py`):

- **`live_trades.sqlite`** — the one that matters. Every trade the live engine (or a manual-override button) places, plus the dashboard's saved sidebar config (`strategy_config`, `safety_config` — see §5's caveat). **Git-ignored** — it's a working file the app writes to constantly, not something to churn through commit history automatically.
- **`trading_bot_data.sqlite`** — older DB, already tracked in git, holds 6 legacy trades from Aug 31-Sep 1 (2026) predating the live-store split. Not actively written to anymore.

**`backups/`** — dated snapshots you commit *on purpose* before switching machines. Full instructions in `backups/README.md`. Short version:

```bash
cp live_trades.sqlite "backups/live_trades_$(date +%Y-%m-%d).sqlite"
git add backups/ && git commit -m "backup" && git push
# on the other machine, after git pull:
cp backups/live_trades_<latest>.sqlite live_trades.sqlite
```

## 5. Live trading configuration — and an important gap

The **live engine's** actual trading parameters are hardcoded in `LiveTradingEngine._run()` (`trading_bot/live_engine.py`):

| Setting | Value |
|---|---|
| Lot size | 0.01 |
| Risk:Reward | 1.25 |
| SL distance clamp | $1.50 – $2.50 |
| Daily profit lock | $10 (auto-pauses for the day once hit) |
| Max daily loss | $15 |
| Max consecutive losses | 3 (→ 45-min pause after 2 in a row, standard 5-min cooldown after any loss) |
| M15 HTF trend filter | ON (won't buy into a bearish M15, won't sell into a bullish M15) |
| Session/killzone filter | OFF |
| Toxic-hours chop shield (10:00-16:00 UTC) | **OFF** — see below |
| Magic number | 9212001 |

**⚠️ Known gap:** the dashboard sidebar's "Strategy Parameters" and "Safety & Circuit Breakers" sections *do* persist to `live_trades.sqlite` (`settings` table, auto-saved on change — this was a deliberate fix, see §9 2026-09-11) — but they currently only feed the **Checklist tab's display/manual-order suggestions** and the **Backtest tab**. They are **not** read by `LiveTradingEngine`, which uses its own hardcoded block above. Changing the sidebar sliders does **not** change what the live auto-bot actually risks. If/when the live engine should respect the sidebar config, that's a real follow-up task — wire `live_engine.py`'s `params`/`cb_config` construction to read `storage.get_setting("strategy_config"/"safety_config")` the same way the dashboard now does.

**London/Overlap session test (started 2026-09-10):** the user observed heavy losses specifically when the London session opens. Rather than permanently block it, the chop-shield (`avoid_toxic_hours`) that used to skip UTC 10:00-16:00 was turned **off**, and every trade now gets a `session` tag (`ASIA`/`LONDON`/`OVERLAP`/`NEWYORK`/`LATE`, via `classify_session()` in `strategy.py`). The dashboard's History tab has a per-session P&L breakdown table specifically to review this after a few weeks and decide keep-vs-reblock. User is in **Karachi (UTC+5)** — London session there is 13:00-18:00 PKT, the London/NY overlap 18:00-21:00 PKT.

## 6. Dashboard / UI

Redesigned 2026-09-11 to a dark, "premium/sleek" look (previous default Streamlit styling was explicitly called out as bad):

- **`.streamlit/config.toml`**: dark theme, muted-gold accent (`#D4A24E`), `toolbarMode = "minimal"`.
- **CSS design tokens** (`_CSS` constant, top of `streamlit_app.py`): one small palette reused everywhere — metric cards (fixed `height:100px` so cards with/without a delta badge don't end up different heights — a real bug that was hit and fixed), pass/fail chips, status pill, monospace console-styled log textarea.
- **5 tabs:** Checklist, Backtest, Market, History, Engine.
- **Real-time updates via `st.fragment`:** the header (status pill/Start-Stop/balance/P&L/positions/session) refreshes every 5s, and the History tab every 8s, *without* a full-page rerun. This replaced an earlier `time.sleep()+st.rerun()` loop that was causing a visible duplicate/ghost render of the whole page — don't reintroduce that pattern; always use `@st.fragment(run_every=N)` for anything that needs to self-update.
- Manual order buttons and per-tab explanatory text are tucked into collapsed `st.expander`s by design — the user explicitly wants low information density, "no extra info layer."

An unrelated GitHub skill the user asked about, `ui-ux-pro-max-skill` (nextlevelbuilder), is **not installed** in this Claude Code environment (checked the plugin registry directly — nothing there). The redesign was done by hand instead. If the user wants that specific tool available later, it needs installing as a plugin first.

## 7. A second strategy that may or may not still exist

Local Claude memory (from a session on **2026-09-06**, this machine) describes a second strategy, **CRT+TBS** (Candle Range Theory + Turtle Soup, an H1 liquidity-sweep swing setup), added via a new `trading_bot/strategies/` registry package (`BaseStrategy` interface, `vwap_ema_scalper.py` + `crt_tbs.py` adapters, backtest.py made strategy-agnostic, a dashboard strategy picker, an MQL5 EA port, sweep/backtest CLI tools).

**This does not exist on any branch of this repo** (`main`, `NEW_BRANCH`, `Pure-implement` all checked 2026-09-11 — no `strategies/` folder, no `crt_tbs.py`, no `mql5/`). Either that work lived in a different local clone/worktree that's since gone, or it was never committed. Don't assume it's there — verify before referencing it. If the user wants it back, it likely needs to be redone or located elsewhere.

## 8. Git / repo state

- **Remote:** `https://github.com/uzairshaikh346/VWAP-EMA-BOT.git`
- **Local git user:** `CodeWithUmair` — **does not have push access** to this repo (tried, got `403: Permission to uzairshaikh346/VWAP-EMA-BOT.git denied to CodeWithUmair`). Commits can be made locally but **pushing is blocked** until one of: CodeWithUmair is added as a collaborator, credentials for `uzairshaikh346` are used instead, or the user forks the repo. **Check this first** before assuming a push will work.
- **Branches:** `main` (default), `NEW_BRANCH` (active development branch, currently checked out — has the engine/dashboard merge, session tagging, UI redesign, sidebar persistence, real-time fragments — see §9), `Pure-implement` (remote only, not investigated).
- Both `trading_bot_data.sqlite` and (compiled) `__pycache__/*.pyc` files are tracked in git — that's the pre-existing repo convention, `.gitignore` (added 2026-09-10) only stops *new* junk (`live_trades.sqlite`, future `__pycache__`, `venv/`, `.env`) from being added, it doesn't untrack what's already tracked.

## 9. Session log

*(Newest first. One entry per work session — what changed, why, anything left open.)*

### 2026-09-11 — Real-time UI, config persistence, backups + this handoff doc
- Fixed dashboard not reflecting new trades/balance without a manual browser refresh: header strip and History tab are now `st.fragment(run_every=...)` blocks (5s / 8s) instead of static once-per-load renders.
- Root-caused and fixed a duplicate/ghost full-page render glitch — it was an earlier `time.sleep()+st.rerun()` auto-refresh loop; replaced with the fragment pattern above.
- Fixed the 6 header metric cards having inconsistent heights (Streamlit only adds a delta line to cards that have one) — forced a fixed `height:100px` on `[data-testid="stMetric"]`.
- Removed a duplicated Start/Stop button + duplicated status metrics from the Engine tab (they're already in the persistent header).
- Sidebar "Strategy Parameters" / "Safety & Circuit Breakers" now persist to `live_trades.sqlite`'s `settings` table (auto-saved on change, seeded on load) instead of resetting to hardcoded defaults every restart — **but see the §5 gap: this still doesn't feed the live engine's actual trading params.**
- Fixed 8 `use_container_width` deprecation warnings (→ `width="stretch"/"content"`).
- Created `backups/` (+ README) and took the first dated snapshot of both SQLite DBs.
- Wrote this file.
- **Open:** git push to `origin/NEW_BRANCH` still blocked on permissions (§8) — local commits exist but aren't on GitHub yet as of this entry.

### 2026-09-10 — Engine/dashboard merge, UI redesign, London session test
- Split `trading_bot/run_live_auto_bot.py`'s trading loop out into `trading_bot/live_engine.py` (`LiveTradingEngine`, background daemon thread, singleton via `get_engine()`), so the dashboard can Start/Stop it with a button — one command now runs everything, where before it needed a second terminal. `run_live_auto_bot.py` became a thin CLI wrapper around the same engine.
- Added `classify_session()`, turned off the `avoid_toxic_hours` chop-shield that was blocking the London session (10:00-16:00 UTC), added per-trade session tagging + a History-tab session breakdown, so London can be evaluated with data instead of blocked outright. See §5.
- Full dashboard redesign: dark/gold theme, `.streamlit/config.toml`, CSS design tokens, consolidated status strip, collapsed sidebar/manual-order sections. See §6.
- Added `.gitignore` (previously didn't exist).
- Split trade storage into `live_trades.sqlite` (new, git-ignored) vs the old committed `trading_bot_data.sqlite`, so old/unrelated trades stop showing as "yours."
- Fixed a live bug in the ported connect logic: the old `if not mt5_bridge.connect():` check could never actually fail (the method returns a tuple, always truthy) — a real connection failure would have gone undetected.
- **Open at end of session:** git push blocked (403, see §8) — same issue still open as of the 2026-09-11 entry above.

### Earlier (dates not confirmed from this machine's memory)
- Original strategy/backtest/circuit-breaker/mt5-bridge/dashboard scaffold (5-step causal checklist, zero-lookahead backtest with Monte Carlo noise gate, demo-only guardrails).
- News filter, TP/SL calculation tuning, "Profit Locked" iterations (per git log — `85e63ff`, `93a3378`, `0934284`, `e208f15`, `3fdae30`).
- Per local memory only (**unverified in this repo, see §7**): a second CRT+TBS strategy added via a `trading_bot/strategies/` package.

## 10. Open items

- [ ] Resolve git push permissions (§8) so `NEW_BRANCH` commits actually reach GitHub.
- [ ] Decide whether to wire the live engine to read sidebar-saved `strategy_config`/`safety_config` instead of its hardcoded params (§5).
- [ ] Review the London/Overlap session data (History tab → Performance by Trading Session) after a few weeks and decide keep-vs-reblock (§5).
- [ ] Locate or redo the CRT+TBS second-strategy work if it's actually wanted (§7).
- [ ] Set up MT5 + demo login on the office laptop (this repo's MT5 path/account are this machine's install only, §3).
