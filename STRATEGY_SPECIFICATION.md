# EMA9 + VWAP Cross Strategy (Gold Scalping Adaptation) - Specification

## 1. Strategy Overview
The **EMA9 + VWAP Cross Strategy (Gold Scalping Adaptation)** is a trend-following scalping framework built for **XAUUSD (Gold)** on the **5-Minute (M5)** timeframe.
It pairs institutional baseline value (session-reset VWAP) with short-term price momentum (9-period EMA), using an adaptive trend-following exit rule based on candle range expansion.

---

## 2. Market & Session Configuration
- **Instrument**: XAUUSD / XAUUSDm (Gold)
- **Timeframe**: M5 (5-minute candles)
- **Contract Size**: 100 oz (Standard XAUUSD)
- **Position Sizing**: Fixed 0.02 Lot size
- **Active Trading Sessions (Server Time)**:
  - **Asian Session**: `00:00 – 08:00` server time
  - **London Session**: `12:00 – 17:00` server time
- **Excluded Sessions**:
  - `London_Pre (08:00 – 12:00)`: Excluded based on backtest performance
  - `NY / Overlap (17:00 – 24:00)`: Excluded based on high chop & spread expansion

---

## 3. Core Indicators
1. **9-Period EMA (Exponential Moving Average)**:
   - Calculated on candle **Close** prices.
2. **VWAP (Volume Weighted Average Price)**:
   - Session-based VWAP, resets daily at **00:00 server time**.
   - Cumulative formula: $\frac{\sum (Typical Price \times Volume)}{\sum Volume}$ where $Typical Price = \frac{High + Low + Close}{3}$.
3. **ATR(14) (Average True Range)**:
   - Standard 14-period lookback used exclusively for setting the initial protective Stop-Loss.

---

## 4. Entry Rules

### Long (Buy) Entry:
1. **Fresh Cross**: The 9 EMA line crosses above the VWAP line:
   - $EMA9_{i-1} \le VWAP_{i-1}$ AND $EMA9_i > VWAP_i$
2. **Close Confirmation**: The current candle's Close is strictly above the 9 EMA:
   - $Close_i > EMA9_i$
3. **Session Filter**: Candle server time must fall in the Asian (`00:00–08:00`) or London (`12:00–17:00`) window.
4. **Execution**: Enter at the candle's Close price with **0.02 Lot**.

### Short (Sell) Entry:
1. **Fresh Cross**: The 9 EMA line crosses below the VWAP line:
   - $EMA9_{i-1} \ge VWAP_{i-1}$ AND $EMA9_i < VWAP_i$
2. **Close Confirmation**: The current candle's Close is strictly below the 9 EMA:
   - $Close_i < EMA9_i$
3. **Session Filter**: Candle server time must fall in the Asian (`00:00–08:00`) or London (`12:00–17:00`) window.
4. **Execution**: Enter at the candle's Close price with **0.02 Lot**.

---

## 5. Exit Rules

### 1. Protective Stop-Loss (Safety Floor)
- Calculated and sent with the order at the time of entry:
  - **Long SL**: $Entry\ Price - (1.5 \times ATR_{14})$
  - **Short SL**: $Entry\ Price + (1.5 \times ATR_{14})$

### 2. Take-Profit / Trend Exit (Primary Exit Mechanism)
- **No fixed profit target**: Positions are kept active to ride the trend until a dynamic reversal trigger fires.
- At the close of every M5 candle, the bot evaluates the distance between candle Close and EMA9 against that candle's own High-Low range:
  - **Long Exit Condition**:
    $$(EMA9 - Close) \ge 0.20 \times (Candle\ High - Candle\ Low)$$
  - **Short Exit Condition**:
    $$(Close - EMA9) \ge 0.20 \times (Candle\ High - Candle\ Low)$$
- **Whichever comes first** (Protective SL or the Trend Reversal Exit) closes the trade immediately at market.

---

## 6. Execution Files
- **Live Trading Bot**: `trading_bot/run_live_auto_bot.py`
  - Run command: `python trading_bot/run_live_auto_bot.py --symbol XAUUSDm`
- **MT5 Backtester**: `trading_bot/run_ema9_vwap_backtest.py`
  - Run command: `python trading_bot/run_ema9_vwap_backtest.py --days 30 --symbol XAUUSDm`
