import React, { useState } from "react";
import { BacktestResultData, BacktestMetricsData } from "../types";
import { NoiseGateCard } from "./NoiseGateCard";
import { Play, TrendingUp, DollarSign, Percent, BarChart2, CheckCircle2, XCircle, ArrowUpRight, ArrowDownRight, Layers, RefreshCw } from "lucide-react";

interface BacktestVisualizerProps {
  backtestResult: BacktestResultData | null;
  onRunBacktest: (params: any) => void;
  isRunning: boolean;
}

export const BacktestVisualizer: React.FC<BacktestVisualizerProps> = ({
  backtestResult,
  onRunBacktest,
  isRunning
}) => {
  const [barsCount, setBarsCount] = useState(1500);
  const [emaFast, setEmaFast] = useState(9);
  const [emaSlow, setEmaSlow] = useState(21);
  const [obLookback, setObLookback] = useState(5);
  const [maxPullback, setMaxPullback] = useState(15);
  const [pullbackAtr, setPullbackAtr] = useState(1.0);
  const [rrRatio, setRrRatio] = useState(2.0);
  const [spreadPoints, setSpreadPoints] = useState(0.25);
  const [tradeFilter, setTradeFilter] = useState<"ALL" | "IS" | "OOS">("ALL");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onRunBacktest({
      bars_count: barsCount,
      ema_fast_period: emaFast,
      ema_slow_period: emaSlow,
      ob_swing_lookback: obLookback,
      max_pullback_bars: maxPullback,
      pullback_atr_mult: pullbackAtr,
      rr_ratio: rrRatio,
      spread_points: spreadPoints
    });
  };

  const renderMetricsColumn = (title: string, m: BacktestMetricsData, isOos: boolean) => (
    <div className={`p-4 rounded-xl border ${
      isOos ? "bg-cyan-950/20 border-cyan-800/60" : "bg-slate-900/60 border-slate-800"
    }`}>
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
        <h4 className="text-xs font-bold text-white uppercase tracking-wider">{title}</h4>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
          m.noise_gate_passed ? "bg-emerald-950 border border-emerald-700 text-emerald-300" : "bg-rose-950 border border-rose-800 text-rose-300"
        }`}>
          {m.noise_gate_passed ? "GATE PASSED" : "GATE FAILED"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <span className="text-slate-400 block text-[11px]">Total Trades</span>
          <span className="font-bold text-slate-100 font-mono text-sm">{m.total_trades}</span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Win Rate</span>
          <span className={`font-bold font-mono text-sm ${m.win_rate_pct >= 50 ? "text-emerald-400" : "text-rose-400"}`}>
            {m.win_rate_pct.toFixed(1)}%
          </span>
        </div>

        <div>
          <span className="text-slate-400 block text-[11px]">Profit Factor</span>
          <span className="font-bold text-slate-100 font-mono text-sm">{m.profit_factor.toFixed(2)}</span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Expectancy</span>
          <span className={`font-bold font-mono text-sm ${m.expectancy_r >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {m.expectancy_r >= 0 ? `+${m.expectancy_r.toFixed(2)}R` : `${m.expectancy_r.toFixed(2)}R`}
          </span>
        </div>

        <div>
          <span className="text-slate-400 block text-[11px]">Net PnL (USD)</span>
          <span className={`font-bold font-mono text-sm ${m.total_net_pnl_usd >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            ${m.total_net_pnl_usd >= 0 ? `+${m.total_net_pnl_usd.toFixed(2)}` : m.total_net_pnl_usd.toFixed(2)}
          </span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Max Drawdown</span>
          <span className="font-bold text-rose-400 font-mono text-sm">
            ${m.max_drawdown_usd.toFixed(2)} ({m.max_drawdown_pct.toFixed(1)}%)
          </span>
        </div>

        <div>
          <span className="text-slate-400 block text-[11px]">Payoff Ratio</span>
          <span className="font-bold text-slate-200 font-mono text-sm">{m.payoff_ratio.toFixed(2)}</span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Max Consec Losses</span>
          <span className="font-bold text-slate-200 font-mono text-sm">{m.max_consecutive_losses}</span>
        </div>
      </div>
    </div>
  );

  const filteredTrades = backtestResult
    ? backtestResult.trades.filter((t) => {
        if (tradeFilter === "IS") return !t.is_out_of_sample;
        if (tradeFilter === "OOS") return t.is_out_of_sample;
        return true;
      })
    : [];

  return (
    <div className="space-y-6">
      {/* Parameter Control Panel */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">Causal Backtest Configuration</h3>
            <p className="text-xs text-slate-400">Zero lookahead: Bar i signal &rarr; Bar i+1 Open fill with spread and commissions.</p>
          </div>
          <button
            onClick={handleSubmit}
            disabled={isRunning}
            className="px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center space-x-2 transition-all shadow-md shadow-amber-950/40 disabled:opacity-50 cursor-pointer"
          >
            {isRunning ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Simulating...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                <span>Run Causal Backtest</span>
              </>
            )}
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 text-xs">
          <div>
            <label className="text-slate-400 block mb-1 font-medium">Bars Count</label>
            <input
              type="number"
              value={barsCount}
              onChange={(e) => setBarsCount(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-medium">Fast EMA</label>
            <input
              type="number"
              value={emaFast}
              onChange={(e) => setEmaFast(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-medium">Slow EMA</label>
            <input
              type="number"
              value={emaSlow}
              onChange={(e) => setEmaSlow(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-medium">OB Lookback</label>
            <input
              type="number"
              value={obLookback}
              onChange={(e) => setObLookback(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-medium">Max PB Bars</label>
            <input
              type="number"
              value={maxPullback}
              onChange={(e) => setMaxPullback(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-medium">PB ATR Mult</label>
            <input
              type="number"
              step="0.1"
              value={pullbackAtr}
              onChange={(e) => setPullbackAtr(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-medium">R:R Ratio</label>
            <input
              type="number"
              step="0.5"
              value={rrRatio}
              onChange={(e) => setRrRatio(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-medium">Spread ($)</label>
            <input
              type="number"
              step="0.05"
              value={spreadPoints}
              onChange={(e) => setSpreadPoints(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono"
            />
          </div>
        </div>
      </div>

      {backtestResult && (
        <>
          {/* Noise Gate Statistical Significance Card */}
          <NoiseGateCard metrics={backtestResult.overall} />

          {/* Performance Comparison: In-Sample vs Out-of-Sample vs Overall */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {renderMetricsColumn("📘 In-Sample Split (75% Training)", backtestResult.in_sample, false)}
            {renderMetricsColumn("📙 Out-of-Sample Split (25% Holdout)", backtestResult.out_of_sample, true)}
            {renderMetricsColumn("🌐 Overall Full Dataset", backtestResult.overall, false)}
          </div>

          {/* Equity Curve Visualizer */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">Equity Curve Simulation</h3>
              <div className="text-xs font-mono text-slate-400">
                Initial: <strong className="text-slate-200">${backtestResult.initial_balance.toFixed(2)}</strong> &rarr; Final: <strong className={backtestResult.final_balance >= backtestResult.initial_balance ? "text-emerald-400" : "text-rose-400"}>${backtestResult.final_balance.toFixed(2)}</strong>
              </div>
            </div>

            {/* Custom SVG Equity Curve */}
            {backtestResult.equity_curve.length > 0 && (
              <div className="h-44 w-full bg-slate-950 rounded-lg p-3 relative border border-slate-800/80">
                {(() => {
                  const curve = backtestResult.equity_curve;
                  const balances = curve.map((c) => c.balance);
                  const minBal = Math.min(...balances) - 50;
                  const maxBal = Math.max(...balances) + 50;
                  const balRange = maxBal - minBal || 1;

                  const width = 800;
                  const height = 150;

                  const points = curve
                    .map((c, i) => {
                      const x = (i / (curve.length - 1)) * width;
                      const y = height - ((c.balance - minBal) / balRange) * height;
                      return `${x},${y}`;
                    })
                    .join(" ");

                  const splitX = (backtestResult.split_index / (backtestResult.trades.length > 0 ? backtestResult.trades[backtestResult.trades.length - 1].exit_bar : 1)) * width;

                  return (
                    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
                      {/* Zero baseline */}
                      <line
                        x1={0}
                        y1={height - ((backtestResult.initial_balance - minBal) / balRange) * height}
                        x2={width}
                        y2={height - ((backtestResult.initial_balance - minBal) / balRange) * height}
                        stroke="#475569"
                        strokeDasharray="4,4"
                        strokeWidth="1"
                      />

                      {/* Equity Polyline */}
                      <polyline
                        fill="none"
                        stroke={backtestResult.final_balance >= backtestResult.initial_balance ? "#10b981" : "#f43f5e"}
                        strokeWidth="2"
                        points={points}
                      />
                    </svg>
                  );
                })()}
              </div>
            )}
          </div>

          {/* Trade Log Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800 mb-3">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">Causal Trade Execution Log</h3>
                <p className="text-xs text-slate-400">Total {filteredTrades.length} trades executed with causal tick fills.</p>
              </div>

              {/* Filter Pills */}
              <div className="flex items-center space-x-1 text-xs">
                <button
                  onClick={() => setTradeFilter("ALL")}
                  className={`px-3 py-1 rounded ${
                    tradeFilter === "ALL" ? "bg-amber-500 text-slate-950 font-bold" : "bg-slate-800 text-slate-400"
                  }`}
                >
                  All Trades ({backtestResult.trades.length})
                </button>
                <button
                  onClick={() => setTradeFilter("IS")}
                  className={`px-3 py-1 rounded ${
                    tradeFilter === "IS" ? "bg-amber-500 text-slate-950 font-bold" : "bg-slate-800 text-slate-400"
                  }`}
                >
                  In-Sample (75%)
                </button>
                <button
                  onClick={() => setTradeFilter("OOS")}
                  className={`px-3 py-1 rounded ${
                    tradeFilter === "OOS" ? "bg-amber-500 text-slate-950 font-bold" : "bg-slate-800 text-slate-400"
                  }`}
                >
                  Out-of-Sample (25%)
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-2 px-3">#</th>
                    <th className="py-2 px-3">Side</th>
                    <th className="py-2 px-3">Entry (Bar+1)</th>
                    <th className="py-2 px-3">SL / TP</th>
                    <th className="py-2 px-3">Exit Price</th>
                    <th className="py-2 px-3">Reason</th>
                    <th className="py-2 px-3">Duration</th>
                    <th className="py-2 px-3">R-Mult</th>
                    <th className="py-2 px-3">Net PnL ($)</th>
                    <th className="py-2 px-3">Split</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredTrades.map((t) => {
                    const isWin = t.net_pnl_usd > 0;
                    return (
                      <tr key={t.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-2 px-3 text-slate-500">{t.id}</td>
                        <td className="py-2 px-3">
                          <span className={`font-bold px-1.5 py-0.5 rounded text-[10px] ${
                            t.direction === "BUY" ? "bg-emerald-950 text-emerald-400 border border-emerald-800" : "bg-rose-950 text-rose-400 border border-rose-800"
                          }`}>
                            {t.direction}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          <span className="text-slate-200">${t.entry_price.toFixed(2)}</span>
                          <span className="text-[10px] text-slate-500 block">bar #{t.entry_bar}</span>
                        </td>
                        <td className="py-2 px-3 text-[11px]">
                          <span className="text-rose-400">${t.stop_loss.toFixed(2)}</span> / <span className="text-emerald-400">${t.take_profit.toFixed(2)}</span>
                        </td>
                        <td className="py-2 px-3 text-slate-300">${t.exit_price.toFixed(2)}</td>
                        <td className="py-2 px-3">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                            t.exit_reason === "TAKE_PROFIT"
                              ? "bg-emerald-950 text-emerald-300"
                              : t.exit_reason === "STOP_LOSS"
                              ? "bg-rose-950 text-rose-300"
                              : "bg-slate-800 text-slate-400"
                          }`}>
                            {t.exit_reason}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-400">{t.duration_bars} bars</td>
                        <td className={`py-2 px-3 font-bold ${isWin ? "text-emerald-400" : "text-rose-400"}`}>
                          {t.pnl_r_multiple >= 0 ? `+${t.pnl_r_multiple.toFixed(2)}R` : `${t.pnl_r_multiple.toFixed(2)}R`}
                        </td>
                        <td className={`py-2 px-3 font-bold ${isWin ? "text-emerald-400" : "text-rose-400"}`}>
                          ${t.net_pnl_usd >= 0 ? `+${t.net_pnl_usd.toFixed(2)}` : t.net_pnl_usd.toFixed(2)}
                        </td>
                        <td className="py-2 px-3">
                          <span className={`px-1.5 py-0.5 rounded text-[9px] ${
                            t.is_out_of_sample ? "bg-cyan-950 text-cyan-400 border border-cyan-800" : "bg-slate-800 text-slate-400"
                          }`}>
                            {t.is_out_of_sample ? "OOS" : "IS"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
