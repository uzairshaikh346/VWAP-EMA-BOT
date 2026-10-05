"""
MetaTrader 5 Terminal Detector & Inspector.
Scans the VPS / PC for all running or installed MT5 terminals and displays:
  - Executable Path
  - Process ID
  - Currently Logged-in Account Number & Broker Server
  - Exact Ready-to-Run Bot Command for each terminal!

Usage:
  python trading_bot/detect_terminals.py
"""

import glob
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def find_running_mt5_processes():
    """Finds all running MT5 processes using PowerShell or WMIC."""
    terminals = []
    if sys.platform != "win32":
        return terminals

    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -Name terminal64,terminal -ErrorAction SilentlyContinue | Select-Object -Property Id, Path | ConvertTo-Csv -NoTypeInformation"
        ]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        lines = [line.strip().strip('"') for line in out.strip().splitlines() if line.strip()]
        if len(lines) > 1:
            for line in lines[1:]:
                parts = [p.strip().strip('"') for p in line.split('","')]
                if len(parts) >= 2:
                    pid, path = parts[0], parts[1]
                    if path and os.path.exists(path) and path not in [t["path"] for t in terminals]:
                        terminals.append({"pid": pid, "path": path, "running": True})
    except Exception:
        pass

    return terminals


def find_installed_mt5_terminals():
    """Scans common Program Files locations for terminal64.exe."""
    found = []
    patterns = [
        r"C:\Program Files\*\terminal64.exe",
        r"C:\Program Files (x86)\*\terminal64.exe",
        r"C:\MT5*\terminal64.exe",
        r"D:\*\terminal64.exe",
    ]
    for pattern in patterns:
        for p in glob.glob(pattern):
            if os.path.exists(p) and p not in found:
                found.append(p)
    return found


def inspect_all():
    print("=" * 95, flush=True)
    print("🔍 METATRADER 5 VPS TERMINAL DETECTOR & CONNECTIVITY ASSISTANT", flush=True)
    print("=" * 95, flush=True)

    running_terms = find_running_mt5_processes()
    installed_terms = find_installed_mt5_terminals()

    all_paths = []
    for t in running_terms:
        if t["path"] not in all_paths:
            all_paths.append(t["path"])
    for p in installed_terms:
        if p not in all_paths:
            all_paths.append(p)

    if not all_paths:
        print("\n⚠️ No running or installed MT5 terminals detected automatically.", flush=True)
        print("💡 Tip: If MT5 is installed in a custom location, specify it with:", flush=True)
        print('   python trading_bot/run_live_auto_bot.py --mt5-path "C:\\Path\\To\\terminal64.exe"\n', flush=True)
        return

    print(f"\nFound {len(all_paths)} MT5 Terminal(s) on this system:\n", flush=True)

    # Try importing MetaTrader5 to test accounts
    try:
        import MetaTrader5 as mt5
        has_mt5 = True
    except ImportError:
        has_mt5 = False

    for idx, path in enumerate(all_paths, 1):
        is_running = any(t["path"].lower() == path.lower() for t in running_terms)
        status_badge = "🟢 RUNNING" if is_running else "⚪ INSTALLED (Not running)"

        acc_info_str = "Unknown"
        acc_login = None
        server_name = None

        if has_mt5:
            try:
                if mt5.initialize(path=path):
                    acc = mt5.account_info()
                    if acc:
                        acc_login = acc.login
                        server_name = acc.server
                        trade_mode = "DEMO" if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "REAL"
                        acc_info_str = f"Login: #{acc.login} | Server: {acc.server} | Balance: ${acc.balance:,.2f} ({trade_mode})"
                    mt5.shutdown()
            except Exception as e:
                acc_info_str = f"Inspection failed: {e}"

        print(f"[{idx}] {status_badge}")
        print(f"    📂 Executable:  {path}")
        print(f"    👤 MT5 Account: {acc_info_str}")
        print("    🚀 Run Command For This Terminal:")
        if acc_login:
            print(f'       python trading_bot/run_live_auto_bot.py --symbol XAUUSDm --login {acc_login}')
        else:
            print(f'       python trading_bot/run_live_auto_bot.py --symbol XAUUSDm --mt5-path "{path}"')
        print("-" * 95, flush=True)

    print("\n💡 NOTE:")
    print("   Agar aap specific account se trade karna chahte hain, to command me:")
    print("   --login <Account_Number>   (maslan: --login 12345678)")
    print("   ya")
    print('   --mt5-path "<Path_To_terminal64.exe>"')
    print("   use karein. Bot sirf usi terminal aur account se connect hoga!\n", flush=True)


if __name__ == "__main__":
    inspect_all()
