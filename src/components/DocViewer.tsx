import React from "react";
import { BookOpen, CheckCircle2, ShieldCheck, Terminal, Cpu, Clock } from "lucide-react";

export const DocViewer: React.FC = () => {
  return (
    <div className="space-y-6 text-slate-300 text-xs leading-relaxed">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
        <div>
          <h2 className="text-base font-bold text-white mb-1">📖 Strategy Blueprint: Triple Filter EMA 9/21 + VWAP Scalper</h2>
          <p className="text-slate-400">Formal specifications and ambiguous rule resolutions for XAU/USD 1-Minute Scalping.</p>
        </div>

        {/* 5-Step Logic Table */}
        <div className="space-y-4">
          <h3 className="text-sm font-bold text-amber-400">1. Causal 5-Step Execution Sequence</h3>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
              <span className="text-[10px] font-bold text-amber-400 block mb-1">STEP 1</span>
              <strong className="text-slate-200 block mb-1">Session VWAP</strong>
              <p className="text-[11px] text-slate-400">Anchored at 00:00 UTC daily rollover. Longs strictly &gt; VWAP; Shorts strictly &lt; VWAP.</p>
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
              <span className="text-[10px] font-bold text-cyan-400 block mb-1">STEP 2</span>
              <strong className="text-slate-200 block mb-1">EMA 9/21 Cross</strong>
              <p className="text-[11px] text-slate-400">EMA9 crosses EMA21. Setup expires if no entry confirms within 15 bars post-cross.</p>
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
              <span className="text-[10px] font-bold text-purple-400 block mb-1">STEP 3</span>
              <strong className="text-slate-200 block mb-1">Order Block</strong>
              <p className="text-[11px] text-slate-400">Causal BOS breaks recent swing pivot. Price reacts off active OB zone (low-to-high candle).</p>
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
              <span className="text-[10px] font-bold text-emerald-400 block mb-1">STEP 4</span>
              <strong className="text-slate-200 block mb-1">Pullback Zone</strong>
              <p className="text-[11px] text-slate-400">Price pulls back to within 1.0 ATR of EMA9 or EMA21 before resuming trend.</p>
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
              <span className="text-[10px] font-bold text-rose-400 block mb-1">STEP 5</span>
              <strong className="text-slate-200 block mb-1">Candle Trigger</strong>
              <p className="text-[11px] text-slate-400">Confirmed Engulfing, Hammer Pinbar, or Expansion body $\ge$ 0.35 ATR at bar close.</p>
            </div>
          </div>
        </div>

        {/* Ambiguous Rules Resolutions */}
        <div className="space-y-3 pt-2">
          <h3 className="text-sm font-bold text-amber-400">2. Ambiguous Rules Resolutions</h3>
          <div className="space-y-2">
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
              <strong className="text-slate-200">Order Block Definition:</strong> The last opposite-colored candle immediately preceding a causal Break of Structure (BOS) move. The BOS requires a candle close beyond the most recent confirmed 5-bar pivot.
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
              <strong className="text-slate-200">Pullback Toward EMAs:</strong> Maximum wait time of 15 bars post-crossover. Price low (Longs) or high (Shorts) must enter within 1.0 &times; ATR(14) of either EMA line.
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
              <strong className="text-slate-200">Stop-Loss Placement:</strong> Placed causally behind the lowest low (Long) or highest high (Short) of the previous 10 bars with a 0.25 &times; ATR buffer, clamped between $1.00 min and $8.00 max distance on Gold.
            </div>
          </div>
        </div>

        {/* Local Running Instructions */}
        <div className="space-y-3 pt-2">
          <h3 className="text-sm font-bold text-amber-400">3. Local Desktop MetaTrader 5 Execution</h3>
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-2 font-mono text-[11px]">
            <p className="text-slate-300"># 1. Install dependencies</p>
            <p className="text-amber-300 bg-slate-900 p-2 rounded">pip install -r requirements.txt</p>
            <p className="text-slate-300"># 2. Run unit tests</p>
            <p className="text-amber-300 bg-slate-900 p-2 rounded">python trading_bot/run_tests.py</p>
            <p className="text-slate-300"># 3. Run backtest CLI & noise gate</p>
            <p className="text-amber-300 bg-slate-900 p-2 rounded">python trading_bot/run_backtest.py</p>
            <p className="text-slate-300"># 4. Launch Streamlit live desktop dashboard</p>
            <p className="text-amber-300 bg-slate-900 p-2 rounded">streamlit run trading_bot/streamlit_app.py</p>
          </div>
        </div>
      </div>
    </div>
  );
};
