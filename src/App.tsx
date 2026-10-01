import React, { useState, useEffect } from "react";
import { Navbar } from "./components/Navbar";
import { SetupChecklist } from "./components/SetupChecklist";
import { LiveChart } from "./components/LiveChart";
import { BacktestVisualizer } from "./components/BacktestVisualizer";
import { SafetyControls } from "./components/SafetyControls";
import { UnitTestsRunner } from "./components/UnitTestsRunner";
import { DocViewer } from "./components/DocViewer";
import { MarketResponse, BacktestResultData } from "./types";

export function App() {
  const [activeTab, setActiveTab] = useState("checklist");
  const [marketData, setMarketData] = useState<MarketResponse | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResultData | null>(null);
  const [isLoadingMarket, setIsLoadingMarket] = useState(false);
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [orderNotice, setOrderNotice] = useState<string | null>(null);

  // Fetch live market data
  const fetchMarketData = async () => {
    setIsLoadingMarket(true);
    try {
      const res = await fetch("/api/market-data");
      const data = await res.json();
      setMarketData(data);
    } catch (e) {
      console.error("Failed to load market data:", e);
    } finally {
      setIsLoadingMarket(false);
    }
  };

  // Run backtest
  const handleRunBacktest = async (params: any) => {
    setIsBacktesting(true);
    try {
      const res = await fetch("/api/run-backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      const data = await res.json();
      setBacktestResult(data);
    } catch (e) {
      console.error("Failed to run backtest:", e);
    } finally {
      setIsBacktesting(false);
    }
  };

  // Dispatch demo order
  const handleDispatchOrder = async (direction: "BUY" | "SELL", sl: number, tp: number) => {
    try {
      const res = await fetch("/api/dispatch-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          direction,
          volume: 0.1,
          sl,
          tp,
          isDemo: true
        }),
      });
      const data = await res.json();
      setOrderNotice(data.message);
      setTimeout(() => setOrderNotice(null), 5000);
    } catch (e) {
      console.error("Failed to dispatch order:", e);
    }
  };

  useEffect(() => {
    fetchMarketData();
    handleRunBacktest({ bars_count: 1500 });
  }, []);

  const noiseGatePassed = backtestResult?.overall.noise_gate_passed ?? false;
  const noisePValue = backtestResult?.overall.noise_p_value ?? 1.0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-amber-500 selection:text-slate-950">
      <Navbar
        account={marketData?.account || null}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        noiseGatePassed={noiseGatePassed}
        noisePValue={noisePValue}
        onRefresh={fetchMarketData}
        isLoading={isLoadingMarket}
      />

      {orderNotice && (
        <div className="bg-emerald-500 text-slate-950 px-4 py-2 text-center text-xs font-bold shadow-md animate-bounce">
          {orderNotice}
        </div>
      )}

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === "checklist" && (
          <SetupChecklist
            longStatus={marketData?.checklist.LONG || null}
            shortStatus={marketData?.checklist.SHORT || null}
            account={marketData?.account || null}
            noiseGatePassed={noiseGatePassed}
            onDispatchOrder={handleDispatchOrder}
          />
        )}

        {activeTab === "chart" && (
          <LiveChart
            bars={marketData?.bars || []}
            orderBlocks={marketData?.order_blocks || []}
          />
        )}

        {activeTab === "backtest" && (
          <BacktestVisualizer
            backtestResult={backtestResult}
            onRunBacktest={handleRunBacktest}
            isRunning={isBacktesting}
          />
        )}

        {activeTab === "safety" && (
          <SafetyControls
            account={marketData?.account || null}
            onResetBreaker={() => {}}
          />
        )}

        {activeTab === "tests" && <UnitTestsRunner />}

        {activeTab === "docs" && <DocViewer />}
      </main>

      <footer className="border-t border-slate-900 bg-slate-950 py-4 text-center text-xs text-slate-600">
        XAU/USD Triple Filter Scalper Bot &bull; MetaTrader 5 & Streamlit Desktop Architecture &bull; Strict Causality Guaranteed
      </footer>
    </div>
  );
}

export default App;
