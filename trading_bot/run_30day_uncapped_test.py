"""
30-Day Forward Backtest Simulation (No Daily Profit Cap)
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from trading_bot.run_uncapped_demo_backtest import run_uncapped_demo_simulation

if __name__ == "__main__":
    run_uncapped_demo_simulation(30)
