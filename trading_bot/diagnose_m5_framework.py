"""
M5 vs M1 Real Data Comparative Diagnostic
Tests why M1 failed on real broker data and demonstrates the M5/M15 Institutional Framework.
"""

import sys
import os
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

def calculate_ema(data: List[float], period: int) -> List[float]:
    if not data or len(data) < period:
        return []
    alpha = 2.0 / (period + 1)
    ema = [0.0] * len(data)
    ema[period - 1] = sum(data[:period]) / period
    for i in range(period, len(data)):
        ema[i] = (data[i] * alpha) + (ema[i - 1] * (1.0 - alpha))
    return ema

def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    n = len(closes)
    if n < period + 1:
        return [0.0] * n
    tr = [0.0] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    atr = [0.0] * n
    atr[period] = sum(tr[1:period + 1]) / period
    for i in range(period + 1, n):
        atr[i] = ((atr[i - 1] * (period - 1)) + tr[i]) / period
    return atr

def resample_to_m5(opens, highs, lows, closes, times_int, volumes):
    m5_opens, m5_highs, m5_lows, m5_closes, m5_times, m5_vols = [], [], [], [], [], []
    i = 0
    n = len(closes)
    while i < n:
        # Group 5 bars
        group_end = min(i + 5, n)
        b_o = opens[i]
        b_h = max(highs[i:group_end])
        b_l = min(lows[i:group_end])
        b_c = closes[group_end - 1]
        b_t = times_int[i]
        b_v = sum(volumes[i:group_end])
        m5_opens.append(b_o)
        m5_highs.append(b_h)
        m5_lows.append(b_l)
        m5_closes.append(b_c)
        m5_times.append(b_t)
        m5_vols.append(b_v)
        i += 5
    return m5_opens, m5_highs, m5_lows, m5_closes, m5_times, m5_vols
