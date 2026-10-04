"""
MT5 Symbol Scanner and Inspector:
Scans your connected MetaTrader 5 broker terminal and displays the exact symbol names
used for US Indices (NQ / Nasdaq, ES / S&P500), Metals (Gold / Silver), and Forex pairs.

Usage:
  python trading_bot/list_mt5_symbols.py
  python trading_bot/list_mt5_symbols.py --search USTEC
  python trading_bot/list_mt5_symbols.py --search 500
"""

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from trading_bot.mt5_bridge import MT5Bridge, MT5_AVAILABLE

if MT5_AVAILABLE:
    import MetaTrader5 as mt5


def scan_symbols(search_query: str = ""):
    print("=" * 90, flush=True)
    print("🔍 METATRADER 5 BROKER SYMBOL DETECTOR", flush=True)
    print("=" * 90, flush=True)

    bridge = MT5Bridge()
    connected, conn_msg = bridge.connect()
    if not connected:
        print(f"❌ Connection to MT5 failed: {conn_msg}", flush=True)
        return

    print("✅ Connected to MT5 Terminal!\n", flush=True)

    if not MT5_AVAILABLE:
        print("ℹ️ Running in simulation environment (no Windows MT5 terminal found).", flush=True)
        print("   Default CFD symbols supported: USTECm / US100m (NQ), US500m (ES), XAUUSDm (Gold).", flush=True)
        return

    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        print(f"❌ Failed to fetch symbols from broker: {mt5.last_error()}", flush=True)
        return

    print(f"📊 Total Broker Symbols Available: {len(all_symbols):,}\n", flush=True)

    if search_query:
        print(f"🔎 Searching for '{search_query}' across broker catalog:")
        matched = [s for s in all_symbols if search_query.upper() in s.name.upper()]
        if not matched:
            print(f"   ⚠️ No symbol found containing '{search_query}'.")
        else:
            print(f"{'Symbol Name':<16} | {'Path':<28} | {'Spread':<8} | {'Contract Size':<14} | {'Digits'}")
            print("-" * 80)
            for s in matched[:30]:
                print(f"{s.name:<16} | {s.path:<28} | {s.spread:<8} | {s.trade_contract_size:<14} | {s.digits}")
        print("=" * 90, flush=True)
        return

    # Categorized scan for NQ, ES, and Gold
    categories = {
        "NQ / Nasdaq 100 Candidates": ["USTEC", "US100", "NAS100", "USTECH", "NQ", "NDX", "TECH100"],
        "ES / S&P 500 Candidates": ["US500", "SPX500", "SP500", "USA500", "ES", "SPX"],
        "Gold (XAUUSD) Candidates": ["XAUUSD", "GOLD"]
    }

    for cat_name, keywords in categories.items():
        print(f"📌 {cat_name}:")
        found = []
        for s in all_symbols:
            for kw in keywords:
                if kw in s.name.upper():
                    found.append(s)
                    break
        
        if found:
            print(f"   {'Symbol Name':<16} | {'Path':<26} | {'Spread':<8} | {'Contract Size':<14} | {'Visible'}")
            print("   " + "-" * 76)
            for s in found:
                vis = "✅ Shown" if s.visible else "⚪ Hidden"
                print(f"   {s.name:<16} | {s.path:<26} | {s.spread:<8} | {s.trade_contract_size:<14} | {vis}")
        else:
            print("   ⚠️ No matching symbol found automatically. Use --search to look up your broker's name.")
        print()

    print("=" * 90, flush=True)
    print("💡 TIP: In Exness, NQ is usually 'USTEC' or 'USTECm', and ES is 'US500' or 'US500m'.")
    print("   In IC Markets / FTMO, NQ is 'NAS100' or 'USTEC', and ES is 'US500' or 'SPX500'.")
    print("=" * 90, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan MT5 broker terminal for symbols (NQ, ES, Gold, etc.)")
    parser.add_argument("--search", type=str, default="", help="Search query (e.g. USTEC, 500, NAS)")
    args = parser.parse_args()

    scan_symbols(args.search)
