# backups/

Dated snapshots of the two SQLite databases, so trade history and bot
settings survive moving between machines (e.g. laptop → office laptop).

## Why this exists

`live_trades.sqlite` (the live engine's trade log + saved sidebar config) is
**intentionally git-ignored** at the repo root — it's a working file the app
writes to on every trade, and continuously committing a changing binary on
every tick isn't useful history. Instead, snapshot it here **on purpose**,
right before you push and switch machines.

`trading_bot_data.sqlite` is the older, already-committed DB at the repo
root (from before `live_trades.sqlite` existed) — it's backed up here too
for completeness, though it's not actively written to anymore.

## Before switching machines

```bash
# from the repo root
mkdir -p backups
cp live_trades.sqlite "backups/live_trades_$(date +%Y-%m-%d).sqlite"
git add backups/ && git commit -m "Backup live trade DB before switching machines" && git push
```

## On the other machine, after `git pull`

```bash
# restore the most recent snapshot as the active live DB
cp backups/live_trades_<latest-date>.sqlite live_trades.sqlite
```

Then run the app as usual (see `HANDOFF.md` → "How to run") — the dashboard
and engine will pick up right where you left off: same trade history, same
saved Strategy Parameters / Safety & Circuit Breaker settings.

## What's inside each SQLite file

Both DBs share the same schema (`trading_bot/storage.py` → `BotStorage`):

| Table | Contents |
|---|---|
| `trades` | one row per order: entry/exit price, SL/TP, lot, net P&L, R-multiple, session tag (`ASIA`/`LONDON`/`OVERLAP`/`NEWYORK`/`LATE`), exit reason |
| `settings` | key/value store — currently `strategy_config` and `safety_config` (the sidebar values, JSON-encoded), auto-saved on every change |
| `bot_logs` | reserved for structured event logging (unused so far — the live log lives in-memory in `LiveTradingEngine.log_lines`, not this table) |
