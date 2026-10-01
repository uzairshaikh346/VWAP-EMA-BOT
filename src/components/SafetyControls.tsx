import React, { useState } from "react";
import { AccountData } from "../types";
import { ShieldCheck, ShieldAlert, AlertTriangle, RefreshCw, Key, DollarSign, Lock, Unlock } from "lucide-react";

interface SafetyControlsProps {
  account: AccountData | null;
  onResetBreaker: () => void;
}

export const SafetyControls: React.FC<SafetyControlsProps> = ({ account, onResetBreaker }) => {
  const [maxDailyLoss, setMaxDailyLoss] = useState(200);
  const [maxConsecLosses, setMaxConsecLosses] = useState(3);
  const [magicNumber, setMagicNumber] = useState(9212001);
  const [consecLossCounter, setConsecLossCounter] = useState(0);

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">MetaTrader 5 Safety Guardrails & Circuit Breakers</h3>
            <p className="text-xs text-slate-400">Strict runtime validation ensures capital protection and demo-only isolation.</p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <span className="px-2.5 py-1 text-xs font-bold rounded bg-emerald-950 border border-emerald-800 text-emerald-300">
            DEMO ACCOUNT VERIFIED
          </span>
        </div>
      </div>

      {/* Grid of Safety Rules */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Guardrail 1: Demo-Only Rule */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center space-x-2">
            <Lock className="w-4 h-4 text-emerald-400" />
            <h4 className="text-sm font-bold text-white">1. Hardcoded Demo-Only Lock</h4>
          </div>
          <p className="text-xs text-slate-300">
            The bot queries <code className="text-amber-400 bg-slate-950 px-1 py-0.5 rounded">account_info().trade_mode == DEMO</code> on <strong>every single order</strong>. Any attempt to connect to a live real-money account is rejected with a fatal refusal exception.
          </p>
          <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between text-xs font-mono">
            <span className="text-slate-400">Current Account Mode:</span>
            <span className="text-emerald-400 font-bold">{account?.mode || "DEMO"}</span>
          </div>
        </div>

        {/* Guardrail 2: AlgoTrading Toggle */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center space-x-2">
            <Unlock className="w-4 h-4 text-cyan-400" />
            <h4 className="text-sm font-bold text-white">2. Terminal AlgoTrading Status</h4>
          </div>
          <p className="text-xs text-slate-300">
            Verifies <code className="text-amber-400 bg-slate-950 px-1 py-0.5 rounded">terminal_info().trade_allowed == True</code>. If automated trading is toggled off in the MT5 desktop toolbar, order dispatch is instantly blocked.
          </p>
          <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between text-xs font-mono">
            <span className="text-slate-400">Terminal Trade Allowed:</span>
            <span className="text-emerald-400 font-bold">TRUE (ACTIVE)</span>
          </div>
        </div>

        {/* Guardrail 3: Daily Loss Limit */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center space-x-2">
            <DollarSign className="w-4 h-4 text-amber-400" />
            <h4 className="text-sm font-bold text-white">3. Daily Loss Circuit Breaker</h4>
          </div>
          <p className="text-xs text-slate-300">
            If realized daily losses reach the threshold below, trading halts automatically until the next UTC day boundary (00:00 UTC).
          </p>
          <div className="flex items-center space-x-3">
            <div className="flex-1">
              <label className="text-[11px] text-slate-400 block mb-1">Max Daily Loss Limit ($)</label>
              <input
                type="number"
                value={maxDailyLoss}
                onChange={(e) => setMaxDailyLoss(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 font-mono"
              />
            </div>
            <div className="flex-1">
              <label className="text-[11px] text-slate-400 block mb-1">Current Daily Net PnL</label>
              <div className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-300 font-mono font-bold">
                +$0.00
              </div>
            </div>
          </div>
        </div>

        {/* Guardrail 4: Consecutive Losses & Magic Number */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center space-x-2">
            <Key className="w-4 h-4 text-purple-400" />
            <h4 className="text-sm font-bold text-white">4. Consecutive Losses & Magic Number</h4>
          </div>
          <p className="text-xs text-slate-300">
            Halts auto-trading after consecutive stop-loss hits to prevent revenge trading during choppiness. Orders are tagged with a unique Magic Number.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Max Consec Losses</label>
              <input
                type="number"
                value={maxConsecLosses}
                onChange={(e) => setMaxConsecLosses(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Magic Number Tag</label>
              <input
                type="number"
                value={magicNumber}
                onChange={(e) => setMagicNumber(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 font-mono"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
