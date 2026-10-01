import React, { useState } from "react";
import { BarData, OrderBlockData } from "../types";
import { Layers, Eye, EyeOff, TrendingUp, Info } from "lucide-react";

interface LiveChartProps {
  bars: BarData[];
  orderBlocks: OrderBlockData[];
}

export const LiveChart: React.FC<LiveChartProps> = ({ bars, orderBlocks }) => {
  const [showEma9, setShowEma9] = useState(true);
  const [showEma21, setShowEma21] = useState(true);
  const [showVwap, setShowVwap] = useState(true);
  const [showOBs, setShowOBs] = useState(true);
  const [hoveredBarIndex, setHoveredBarIndex] = useState<number | null>(null);

  if (!bars || bars.length === 0) {
    return <div className="p-8 text-center text-slate-400">No chart data available.</div>;
  }

  const displayBars = bars.slice(-80); // Last 80 bars for crisp visibility
  const minPrice = Math.min(...displayBars.map((b) => Math.min(b.low, b.vwap, b.ema21))) - 0.5;
  const maxPrice = Math.max(...displayBars.map((b) => Math.max(b.high, b.vwap, b.ema21))) + 0.5;
  const priceRange = maxPrice - minPrice || 1;

  const svgWidth = 900;
  const svgHeight = 420;
  const chartPadding = { top: 20, right: 65, bottom: 35, left: 10 };
  const plotWidth = svgWidth - chartPadding.left - chartPadding.right;
  const plotHeight = svgHeight - chartPadding.top - chartPadding.bottom;

  const getX = (index: number) => chartPadding.left + (index / (displayBars.length - 1)) * plotWidth;
  const getY = (price: number) => chartPadding.top + plotHeight - ((price - minPrice) / priceRange) * plotHeight;

  // Price grid lines (5 levels)
  const priceSteps = 6;
  const gridPrices = Array.from({ length: priceSteps }, (_, i) => minPrice + (i / (priceSteps - 1)) * priceRange);

  const hoveredBar = hoveredBarIndex !== null && hoveredBarIndex < displayBars.length ? displayBars[hoveredBarIndex] : displayBars[displayBars.length - 1];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
      {/* Header with Tooltip summary & Layer Toggles */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">XAU/USD 1-Minute Live Chart</h3>
            <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
              M1 TIMEFRAME
            </span>
          </div>
          {hoveredBar && (
            <div className="flex items-center space-x-3 text-xs font-mono mt-1 text-slate-300">
              <span>O: <strong className="text-white">${hoveredBar.open.toFixed(2)}</strong></span>
              <span>H: <strong className="text-emerald-400">${hoveredBar.high.toFixed(2)}</strong></span>
              <span>L: <strong className="text-rose-400">${hoveredBar.low.toFixed(2)}</strong></span>
              <span>C: <strong className={hoveredBar.close >= hoveredBar.open ? "text-emerald-400" : "text-rose-400"}>${hoveredBar.close.toFixed(2)}</strong></span>
              <span>Vol: <strong className="text-slate-200">{hoveredBar.volume}</strong></span>
              <span className="text-slate-500">|</span>
              <span className="text-amber-400">EMA9: ${hoveredBar.ema9.toFixed(2)}</span>
              <span className="text-cyan-400">EMA21: ${hoveredBar.ema21.toFixed(2)}</span>
              <span className="text-purple-400">VWAP: ${hoveredBar.vwap.toFixed(2)}</span>
            </div>
          )}
        </div>

        {/* Toggle Pills */}
        <div className="flex items-center space-x-2 text-xs">
          <button
            onClick={() => setShowEma9(!showEma9)}
            className={`px-2.5 py-1 rounded border transition-colors flex items-center space-x-1.5 ${
              showEma9 ? "bg-amber-950/60 border-amber-700 text-amber-300" : "bg-slate-800 border-slate-700 text-slate-500"
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span>EMA 9</span>
          </button>

          <button
            onClick={() => setShowEma21(!showEma21)}
            className={`px-2.5 py-1 rounded border transition-colors flex items-center space-x-1.5 ${
              showEma21 ? "bg-cyan-950/60 border-cyan-700 text-cyan-300" : "bg-slate-800 border-slate-700 text-slate-500"
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            <span>EMA 21</span>
          </button>

          <button
            onClick={() => setShowVwap(!showVwap)}
            className={`px-2.5 py-1 rounded border transition-colors flex items-center space-x-1.5 ${
              showVwap ? "bg-purple-950/60 border-purple-700 text-purple-300" : "bg-slate-800 border-slate-700 text-slate-500"
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-purple-400" />
            <span>VWAP</span>
          </button>

          <button
            onClick={() => setShowOBs(!showOBs)}
            className={`px-2.5 py-1 rounded border transition-colors flex items-center space-x-1.5 ${
              showOBs ? "bg-slate-800 border-slate-600 text-slate-200" : "bg-slate-800 border-slate-700 text-slate-500"
            }`}
          >
            <Layers className="w-3 h-3 text-slate-400" />
            <span>Order Blocks</span>
          </button>
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="relative w-full overflow-hidden rounded-lg bg-slate-950 border border-slate-800/80">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-auto cursor-crosshair select-none"
          onMouseLeave={() => setHoveredBarIndex(null)}
        >
          <defs>
            <linearGradient id="bullObGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.08" />
            </linearGradient>
            <linearGradient id="bearObGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.08" />
            </linearGradient>
          </defs>

          {/* Price Grid Horizontal Lines */}
          {gridPrices.map((price, idx) => {
            const y = getY(price);
            return (
              <g key={idx}>
                <line
                  x1={chartPadding.left}
                  y1={y}
                  x2={svgWidth - chartPadding.right}
                  y2={y}
                  stroke="#1e293b"
                  strokeDasharray="3,3"
                  strokeWidth="1"
                />
                <text
                  x={svgWidth - chartPadding.right + 6}
                  y={y + 3}
                  fill="#64748b"
                  fontSize="9"
                  fontFamily="monospace"
                >
                  ${price.toFixed(2)}
                </text>
              </g>
            );
          })}

          {/* Active Order Block Zones */}
          {showOBs &&
            orderBlocks.map((ob, idx) => {
              if (!ob.is_active) return null;
              const yHigh = getY(ob.zone_high);
              const yLow = getY(ob.zone_low);
              const height = Math.max(2, Math.abs(yLow - yHigh));
              const isBull = ob.direction === "BULLISH";

              return (
                <g key={idx}>
                  <rect
                    x={chartPadding.left}
                    y={Math.min(yHigh, yLow)}
                    width={plotWidth}
                    height={height}
                    fill={isBull ? "url(#bullObGrad)" : "url(#bearObGrad)"}
                    stroke={isBull ? "#10b981" : "#f43f5e"}
                    strokeWidth="1"
                    strokeDasharray="4,4"
                    opacity="0.6"
                  />
                  <text
                    x={chartPadding.left + 8}
                    y={Math.min(yHigh, yLow) + 12}
                    fill={isBull ? "#34d399" : "#fb7185"}
                    fontSize="9"
                    fontWeight="bold"
                    fontFamily="monospace"
                  >
                    {ob.direction} OB [${ob.zone_low.toFixed(2)} - ${ob.zone_high.toFixed(2)}]
                  </text>
                </g>
              );
            })}

          {/* Indicator Polyline: EMA 9 (Amber) */}
          {showEma9 && (
            <polyline
              fill="none"
              stroke="#fbbf24"
              strokeWidth="1.75"
              points={displayBars.map((b, i) => `${getX(i)},${getY(b.ema9)}`).join(" ")}
            />
          )}

          {/* Indicator Polyline: EMA 21 (Cyan) */}
          {showEma21 && (
            <polyline
              fill="none"
              stroke="#22d3ee"
              strokeWidth="1.75"
              points={displayBars.map((b, i) => `${getX(i)},${getY(b.ema21)}`).join(" ")}
            />
          )}

          {/* Indicator Polyline: VWAP (Purple) */}
          {showVwap && (
            <polyline
              fill="none"
              stroke="#c084fc"
              strokeWidth="2.25"
              strokeDasharray="6,3"
              points={displayBars.map((b, i) => `${getX(i)},${getY(b.vwap)}`).join(" ")}
            />
          )}

          {/* Candlesticks */}
          {displayBars.map((b, i) => {
            const x = getX(i);
            const yOpen = getY(b.open);
            const yClose = getY(b.close);
            const yHigh = getY(b.high);
            const yLow = getY(b.low);
            const isBull = b.close >= b.open;
            const color = isBull ? "#10b981" : "#f43f5e";
            const candleWidth = Math.max(3, Math.min(8, (plotWidth / displayBars.length) * 0.7));

            return (
              <g
                key={i}
                onMouseEnter={() => setHoveredBarIndex(i)}
                className="hover:opacity-80 transition-opacity"
              >
                {/* Wick */}
                <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth="1.25" />
                {/* Body */}
                <rect
                  x={x - candleWidth / 2}
                  y={Math.min(yOpen, yClose)}
                  width={candleWidth}
                  height={Math.max(1.5, Math.abs(yClose - yOpen))}
                  fill={isBull ? "#10b981" : "#f43f5e"}
                  rx="0.5"
                />
              </g>
            );
          })}

          {/* Hover Crosshair */}
          {hoveredBarIndex !== null && hoveredBarIndex < displayBars.length && (
            <g>
              <line
                x1={getX(hoveredBarIndex)}
                y1={chartPadding.top}
                x2={getX(hoveredBarIndex)}
                y2={svgHeight - chartPadding.bottom}
                stroke="#94a3b8"
                strokeWidth="1"
                strokeDasharray="2,2"
              />
            </g>
          )}

          {/* Time axis labels */}
          {displayBars
            .filter((_, i) => i % 15 === 0)
            .map((b, i) => {
              const originalIndex = i * 15;
              const x = getX(originalIndex);
              const timeStr = b.time.includes("T") ? b.time.split("T")[1].slice(0, 5) : b.time;
              return (
                <text
                  key={i}
                  x={x}
                  y={svgHeight - 12}
                  fill="#64748b"
                  fontSize="9"
                  fontFamily="monospace"
                  textAnchor="middle"
                >
                  {timeStr}
                </text>
              );
            })}
        </svg>
      </div>

      {/* Legend footer */}
      <div className="flex flex-wrap items-center justify-between text-xs text-slate-400 pt-1">
        <div className="flex items-center space-x-4">
          <span className="flex items-center space-x-1">
            <span className="w-3 h-0.5 bg-amber-400 inline-block" />
            <span>Fast EMA (9)</span>
          </span>
          <span className="flex items-center space-x-1">
            <span className="w-3 h-0.5 bg-cyan-400 inline-block" />
            <span>Slow EMA (21)</span>
          </span>
          <span className="flex items-center space-x-1">
            <span className="w-3 h-0.5 bg-purple-400 inline-block" />
            <span>Session VWAP (00:00 UTC)</span>
          </span>
          <span className="flex items-center space-x-1">
            <span className="w-3 h-2 bg-emerald-500/40 border border-emerald-500/60 inline-block" />
            <span>Bullish OB</span>
          </span>
          <span className="flex items-center space-x-1">
            <span className="w-3 h-2 bg-rose-500/40 border border-rose-500/60 inline-block" />
            <span>Bearish OB</span>
          </span>
        </div>
        <span className="text-[11px] text-slate-500">Live ticks sync every M1 close</span>
      </div>
    </div>
  );
};
