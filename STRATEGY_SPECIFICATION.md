# Institutional Gold Scalper (XAU/USD M1) - Strategy Specification

## 1. Strategy Overview & Philosophy
The **Institutional Gold Scalper** is a high-precision, quantitative trend-following momentum engine built specifically for **XAU/USD (Gold)** on the **1-Minute (M1)** timeframe.
It relies on **confluence of 3 market dimensions**:
1. **Macro Regime (M15 Trend Alignment)**: Ensuring trades flow with the higher-timeframe order flow.
2. **Institutional Baseline (Session VWAP)**: Measuring institutional value anchored to the daily 00:00 UTC open.
3. **Micro Execution (EMA 9/21 Pullback + Structural Order Block)**: Entering only when price tests high-probability liquidity zones with price-action candle confirmation.

---

## 2. Quantitative Confluence Rules (5-Step Entry Checklist)

Every trade must strictly satisfy **all 5 conditions** before an order is broadcasted to MT5:

```
[1. Macro & VWAP Bias] ➔ [2. Fresh EMA Crossover] ➔ [3. Order Block Retest] ➔ [4. Close-to-EMA Pullback] ➔ [5. Confirmation Candle]
```

### Step 1: Institutional Value & Direction (VWAP & M15 Alignment)
- **BUY Trades**: 
  - M1 Close > Session VWAP + $0.05
  - VWAP Slope (last 4 bars) >= -$0.10 (not sharply falling)
  - M15 Macro EMA 50 is Bullish or Neutral (counter-trend shorts strictly forbidden)
- **SELL Trades**:
  - M1 Close < Session VWAP - $0.05
  - VWAP Slope (last 4 bars) <= +0.10 (not sharply rising)
  - M15 Macro EMA 50 is Bearish or Neutral (counter-trend longs strictly forbidden)

### Step 2: Directional Momentum (EMA 9 & EMA 21)
- **Fast EMA (Period 9)** and **Slow EMA (Period 21)**.
- A fresh crossover must have occurred within the last **15 to 30 bars**.
- **Crucial Rule**: Once a crossover triggers a filled trade, that crossover event is **CONSUMED**. The bot is prohibited from multi-firing trades on the same expired crossover without a fresh cycle.

### Step 3: Institutional Order Block (OB Zone)
- Valid swing pivot pivots (3-bar fractal lookback) create high-probability liquidity zones.
- Price must actively touch or test within `0.35 * ATR` of the active unmitigated Order Block.

### Step 4: Proximity Pullback (Anti-Chasing Shield)
- Price must pull back close to the EMA 9/21 ribbon (`<= 1.5 * ATR` distance).
- **Anti-Exhaustion Filter**: If price has already extended more than `2.5 * ATR` away from EMA 9, the trade is **VETOED** (prevents buying the top or selling the bottom).

### Step 5: Micro Candlestick Confirmation
- Entry requires one of the following authentic price-action patterns on bar close:
  1. **Bullish / Bearish Engulfing** (Body strictly engulfs previous bar body).
  2. **Hammer / Pinbar** (Rejection wick >= 2.0x body height, nose wick <= 0.5x body height).
  3. **Strong Momentum Impulse** (Marubozu body >= 65% of total bar range).

---

## 3. Stop-Loss (SL) & Take-Profit (TP) Mechanics

### Stop-Loss Calculation
- **BUY**: `SL = Swing_Low (last 5 bars) - (0.25 * ATR)`
- **SELL**: `SL = Swing_High (last 5 bars) + (0.25 * ATR)`
- **Realistic Gold Boundaries**:
  - Minimum SL: **$1.80** (prevents broker spread stop-outs during spread widening).
  - Maximum SL: **$3.80** (allows natural swing structure breathing room on Gold at $4,300+).

### Take-Profit Calculation
- **Fixed Risk:Reward Ratio**: `1 : 1.50`
- `TP_Distance = Risk_Distance * 1.50`
- Minimum TP on Gold: **$2.70** (guarantees net positive payout after broker spread + commission).

### Dynamic 70% Break-Even (BE) Lock
- When price reaches **70% of the distance toward Take-Profit**:
  - `New_SL = Entry_Price ± (Spread + $0.10)`
  - The trade is locked into guaranteed 100% risk-free status, protecting accrued profits from sudden mean-reversion spikes.

---

## 4. Execution & Risk Circuit Breakers (Monday Forward-Test Calibration)

| Shield Name | Parameter | Action |
| :--- | :--- | :--- |
| **Daily Profit Target Lock** | `+$10.00 USD` (50 Pips @ 0.02 Lot) | Shuts down engine for the rest of the calendar day once goal is reached (Banked Profit Shield). |
| **Max Daily Capital Loss Limit** | `-$12.00 USD` (2 losses max) | Emergency circuit breaker trips, halts all trading until 00:00 UTC to protect account equity. |
| **Max Consecutive Losses** | `2 trades` | Enforces a mandatory 45-minute cooling breather to prevent revenge trading. |
| **Post-Loss Cooldown** | `15 minutes` | Zero trade entries allowed for 15 minutes immediately following a stop-out. |
| **Post-TP Cooldown** | `3 minutes` | Prevents instant re-entry / double-dipping at exhausted price levels. |
| **Max Broker Spread Guard** | `$0.40` (4.0 pips) | Rejects entries if broker spread widens beyond $0.40. |
| **High-Impact News Shield** | `±30 mins` | Pauses trading 30 minutes before and 30 minutes after high-impact USD economic events (NFP, CPI, FOMC). |
| **Golden Trading Sessions** | **London**: 07:00 - 12:00 UTC<br>**NY Afternoon**: 16:00 - 21:00 UTC | **PKT 12:00 PM - 05:00 PM** & **PKT 09:00 PM - 02:00 AM**.<br>US Open trap (12:00-16:00 UTC) & Asian slump 100% blocked. |

---

## 5. Lot Sizing & Money Management Guidelines

On Gold (XAU/USD), 1.0 lot = 100 oz of Gold. Therefore:
- **0.02 Lot (Forward-Test Standard)**:
  - $1.00 move in Gold = **$2.00 PnL**.
  - 50 Pips Target = **+$10.00 USD Profit**.
  - Average Stop-Loss ($2.50 to $3.00) = **-$5.00 to -$6.00 Risk per trade**.
  - Target achieve hone ke liye sirf **1 ya 2 clean trades** chahiye hoti hain!
- **Recommended Account Balance**:
  - **$200 - $500 Account**: Ideal for 0.02 Lot (risk per trade is only ~1.5% to 2.5% of equity).
  - **$1,000+ Account**: Can scale to 0.05 Lot (target $25/day) with identical mechanics.
