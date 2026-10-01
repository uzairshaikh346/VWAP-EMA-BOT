import React from "react";
import { BacktestMetricsData } from "../types";
import { ShieldCheck, ShieldAlert, HelpCircle, BarChart3, Binary, Flame } from "lucide-react";

interface NoiseGateCardProps {
  metrics: BacktestMetricsData | null;
}

export const NoiseGateCard: React.FC<NoiseGateCardProps> = ({ metrics }) => {
  if (!metrics) return null;

  const isPassed = metrics.noise_gate_passed;
  const pVal = metrics.noise_p_value;
  const realExp = metrics.expectancy_r;

  // Render Monte Carlo histogram
  const shuffled = metrics.shuffled_expectancies || [];
  const minVal = Math.min(...shuffled, realExp, -1.0);
  const maxVal = Math.max(...shuffled, realExp, 2.0);
  const range = maxVal - minVal || 1;

  const bucketsCount = 12;
  const bucketWidth = range / bucketsCount;
  const buckets = Array.from({ length: bucketsCount }, () => 0);

  shuffled.forEach((val) => {
    const bIdx = Math.min(bucketsCount - 1, Math.max(0, Math.floor((val - minVal) / bucketWidth)));
    buckets[bIdx]++;
  });

  const maxBucketCount = Math.max(...buckets, 1);

  return (
    <div className={`rounded-xl border p-5 transition-all ${
      isPassed
        ? "bg-emerald-950/20 border-emerald-700/60"
        : "bg-rose-950/20 border-rose-800/60"
    }`}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center font-bold ${
            isPassed ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
          }`}>
            {isPassed ? <ShieldCheck className="w-5 h-5" /> : <ShieldAlert className="w-5 h-5" />}
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              Mandatory Noise-Control Statistical Significance Gate
              <span className={`px-2.5 py-0.5 text-xs font-extrabold rounded ${
                isPassed
                  ? "bg-emerald-500 text-slate-950 shadow-sm"
                  : "bg-rose-500 text-white shadow-sm"
              }`}>
                {isPassed ? "PASSED (p <= 0.05)" : "FAILED (p > 0.05)"}
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              100-Iteration Monte Carlo Trade Sequence Permutation Test &bull; Null Hypothesis of Zero Edge
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4 text-xs font-mono">
          <div className="text-right">
            <span className="text-slate-400 block text-[10px]">EMPIRICAL P-VALUE</span>
            <span className={`font-bold text-sm ${isPassed ? "text-emerald-400" : "text-rose-400"}`}>
              {pVal.toFixed(4)}
            </span>
          </div>
          <div className="text-right">
            <span className="text-slate-400 block text-[10px]">Z-SCORE VS NULL</span>
            <span className="font-bold text-sm text-slate-200">{metrics.z_score.toFixed(2)}σ</span>
          </div>
          <div className="text-right">
            <span className="text-slate-400 block text-[10px]">REAL EXPECTANCY</span>
            <span className="font-bold text-sm text-amber-400">{realExp >= 0 ? `+${realExp.toFixed(2)}R` : `${realExp.toFixed(2)}R`}</span>
          </div>
        </div>
      </div>

      {/* Monte Carlo Visual Histogram */}
      <div className="mt-4">
        <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
          <span className="flex items-center gap-1 font-semibold text-slate-300">
            <BarChart3 className="w-3.5 h-3.5 text-amber-400" />
            Shuffled Expectancy Distribution (Null Model)
          </span>
          <span className="text-[11px] text-slate-500">
            Real strategy marker vs 100 reshuffled order sequences
          </span>
        </div>

        <div className="h-24 bg-slate-950 rounded-lg border border-slate-800/80 p-3 flex items-end justify-between gap-1.5 relative">
          {buckets.map((count, idx) => {
            const hPct = (count / maxBucketCount) * 100;
            const bValMin = minVal + idx * bucketWidth;
            const bValMax = bValMin + bucketWidth;
            const containsReal = realExp >= bValMin && realExp < bValMax;

            return (
              <div
                key={idx}
                className="flex-1 flex flex-col items-center justify-end h-full group relative"
              >
                <div
                  style={{ height: `${Math.max(6, hPct)}%` }}
                  className={`w-full rounded-t transition-all ${
                    containsReal
                      ? "bg-amber-400 shadow-md shadow-amber-500/50"
                      : "bg-slate-700/60 hover:bg-slate-600"
                  }`}
                />
                {/* Tooltip on hover */}
                <div className="absolute -top-7 left-1/2 -translate-x-1/2 hidden group-hover:block bg-slate-800 text-[10px] text-white px-1.5 py-0.5 rounded border border-slate-700 whitespace-nowrap z-10">
                  [{bValMin.toFixed(2)}R - {bValMax.toFixed(2)}R]: {count} runs
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex justify-between text-[10px] font-mono text-slate-500 mt-1 px-1">
          <span>{minVal.toFixed(2)}R (Worst Shuffled)</span>
          <span className="text-amber-400 font-bold">▲ Real Expectancy: {realExp.toFixed(2)}R</span>
          <span>+{maxVal.toFixed(2)}R (Best Shuffled)</span>
        </div>
      </div>

      {/* Safety Explanation */}
      <div className="mt-4 p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-300 space-y-1">
        <strong className="text-slate-200 block">Why the Noise Gate is Mandatory:</strong>
        <p>
          A high win-rate or positive profit factor on a small trade sample can easily be pure chance (statistical luck). The Monte Carlo permutation test repeatedly breaks trade sequence order to establish the null probability distribution. If p &gt; 0.05, the performance cannot be distinguished from coin-flip noise, and live auto-execution is strictly disabled until genuine edge is verified.
        </p>
      </div>
    </div>
  );
};
