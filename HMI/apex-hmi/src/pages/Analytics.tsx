import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/auth-context";
import HealthScore from "@/components/pews/HealthScore";
import WarningPanel from "@/components/pews/WarningPanel";
import StatusSummary from "@/components/pews/StatusSummary";
import TrendSidePanel from "@/components/pews/TrendSidePanel";

const API = "http://localhost:6001";
const POLL_MS = 60_000;

export interface PewsWarning {
  id: number;
  time: string;
  tag_id: string;
  warning_level: number;
  warning_type: string;
  current_value: number | null;
  avg_value: number | null;
  deviation_pct: number | null;
  threshold_value: number | null;
  message: string;
}

export interface PewsStatus {
  baseline_count: number;
  oldest_baseline: string | null;
  newest_baseline: string | null;
  warning_summary: Record<string, number>;   // level → count
  total_active_warnings: number;
}

export default function Analytics() {
  const { token } = useAuth();
  const headers = { Authorization: `Bearer ${token}` };

  const [warnings, setWarnings]     = useState<PewsWarning[]>([]);
  const [status, setStatus]         = useState<PewsStatus | null>(null);
  const [loading, setLoading]       = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [error, setError]           = useState<string | null>(null);
  const [activeTab, setActiveTab]   = useState<"pews" | "bi">("pews");

  // When bi tab is clicked, open HistoricalTrends in a new window instead of
  // rendering a placeholder here.
  const openBiWindow = () => {
    window.open(
      "http://localhost:6004",
      "HistoricalTrends",
      "width=1440,height=900,resizable=yes,scrollbars=yes"
    );
  };

  const fetchAll = useCallback(async () => {
    try {
      const [wRes, sRes] = await Promise.all([
        fetch(`${API}/api/pews/warnings`, { headers }),
        fetch(`${API}/api/pews/status`,   { headers }),
      ]);
      const wData = await wRes.json();
      const sData = await sRes.json();
      if (wData.success) setWarnings(wData.warnings);
      if (sData.success) setStatus(sData);
      setError(null);
    } catch (e: unknown) {
      setError((e as Error).message ?? "Network error");
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, [token]);

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(timer);
  }, [fetchAll]);

  const handleAck = async (id: number) => {
    try {
      await fetch(`${API}/api/pews/warnings/${id}/ack`, {
        method: "POST",
        headers,
      });
      setWarnings(prev => prev.filter(w => w.id !== id));
      if (status) {
        setStatus(prev => prev
          ? { ...prev, total_active_warnings: Math.max(0, prev.total_active_warnings - 1) }
          : prev
        );
      }
    } catch (e) {
      console.error("Ack failed", e);
    }
  };

  // Compute health score from warning_summary
  const healthScore = (() => {
    if (!status || !warnings.length) return 100;
    const weights: Record<number, number> = { 1: 1, 2: 3, 3: 7, 4: 15 };
    const total = status.baseline_count || 1;
    const penalty = Object.entries(status.warning_summary).reduce(
      (acc, [lvl, cnt]) => acc + (weights[Number(lvl)] ?? 1) * cnt,
      0
    );
    return Math.max(0, Math.round(100 - (penalty / total) * 10));
  })();

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      {/* ── Tab bar ── */}
      <div className="flex items-center gap-1 px-4 pt-4 border-b border-gray-700 bg-gray-950">
        <div className="flex gap-1 flex-1">
          {(["pews"] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-5 py-2.5 text-sm font-semibold rounded-t transition ${
                activeTab === tab
                  ? "bg-gray-900 border border-b-gray-900 border-gray-700 text-white"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              ⚠ Early Warnings
            </button>
          ))}
          {/* BI opens an external window — not an in-page tab */}
          <button
            onClick={openBiWindow}
            className="px-5 py-2.5 text-sm font-semibold rounded-t transition text-gray-500 hover:text-orange-400"
            title="Opens HistoricalTrends BI in a new window"
          >
            📊 BI Analytics ↗
          </button>
        </div>
        {activeTab === "pews" && (
          <div className="flex items-center gap-3 text-xs text-gray-500 pb-1">
            <HealthScore score={healthScore} />
            {lastRefresh && <span>Refreshed: {lastRefresh.toLocaleTimeString()}</span>}
            <button onClick={fetchAll}
              className="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded text-gray-300 transition">
              ↻ Refresh
            </button>
          </div>
        )}
      </div>

      {/* ── PEWS Tab ── */}
      {activeTab === "pews" && (
        <div className="flex flex-1 overflow-hidden">
          {/* Main area */}
          <div className="flex-1 p-4 overflow-y-auto">
            {error && (
              <div className="mb-4 p-3 bg-red-900/40 border border-red-700 rounded text-red-300 text-sm">⚠ {error}</div>
            )}
            {loading ? (
              <div className="flex items-center justify-center h-64 text-gray-500">Loading…</div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
                <div className="lg:col-span-3">
                  <WarningPanel warnings={warnings} onAck={handleAck} />
                </div>
                <div className="lg:col-span-2">
                  <StatusSummary status={status} />
                </div>
              </div>
            )}
          </div>
          {/* Predictive trend side panel */}
          <TrendSidePanel />
        </div>
      )}

      {/* ── BI Analytics Tab — uses refactored BI API (PostgreSQL only) ── */}
      {activeTab === "bi" && (
        <div className="flex-1 flex flex-col p-6 overflow-y-auto">
          <div className="max-w-7xl mx-auto w-full space-y-6">
            {/* Header */}
            <div className="bg-gradient-to-r from-blue-900/40 to-purple-900/40 p-6 rounded-lg border border-blue-700/50">
              <h2 className="text-2xl font-bold text-white mb-2">📊 BI Analytics & Forecasting</h2>
              <p className="text-gray-300">
                Real-time predictive analytics powered by PostgreSQL historian data.
                Select a tag from the HMI to view its forecast.
              </p>
            </div>

            {/* Info Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gray-900/60 p-5 rounded-lg border border-gray-700">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-10 h-10 bg-blue-500/20 rounded-lg flex items-center justify-center">
                    <span className="text-2xl">📈</span>
                  </div>
                  <h3 className="text-lg font-semibold text-white">Forecast Models</h3>
                </div>
                <p className="text-gray-400 text-sm">4 advanced models: Linear Regression, Holt-Winters, FFT, ARIMA</p>
              </div>

              <div className="bg-gray-900/60 p-5 rounded-lg border border-gray-700">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-10 h-10 bg-green-500/20 rounded-lg flex items-center justify-center">
                    <span className="text-2xl">⏱️</span>
                  </div>
                  <h3 className="text-lg font-semibold text-white">Real-Time Data</h3>
                </div>
                <p className="text-gray-400 text-sm">Live data from PostgreSQL historian (no Parquet files)</p>
              </div>

              <div className="bg-gray-900/60 p-5 rounded-lg border border-gray-700">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center">
                    <span className="text-2xl">🎯</span>
                  </div>
                  <h3 className="text-lg font-semibold text-white">Accuracy Tracking</h3>
                </div>
                <p className="text-gray-400 text-sm">Minute-average accuracy with honest error metrics</p>
              </div>
            </div>

            {/* Instructions */}
            <div className="bg-gray-900/60 p-6 rounded-lg border border-gray-700">
              <h3 className="text-xl font-semibold text-white mb-4">How to Use BI Analytics</h3>
              <div className="space-y-3 text-gray-300">
                <div className="flex items-start gap-3">
                  <span className="text-blue-400 font-bold text-lg">1.</span>
                  <p>Go back to the main HMI dashboard (click back arrow or navigate to Home)</p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-blue-400 font-bold text-lg">2.</span>
                  <p>Select any tag from the tag list or asset hierarchy</p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-blue-400 font-bold text-lg">3.</span>
                  <p>Click the <span className="px-2 py-1 bg-blue-600 rounded text-xs font-mono">📈 BI Analytics</span> button in the tag details panel</p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-blue-400 font-bold text-lg">4.</span>
                  <p>View the full-page forecast with 2-hour history + 30-minute prediction horizon</p>
                </div>
              </div>
            </div>

            {/* Features List */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-gray-900/60 p-6 rounded-lg border border-gray-700">
                <h4 className="text-lg font-semibold text-white mb-3">✨ Features</h4>
                <ul className="space-y-2 text-gray-300">
                  <li className="flex items-center gap-2">
                    <span className="text-green-400">✓</span>
                    <span>Multi-model ensemble forecasting</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-green-400">✓</span>
                    <span>Automatic best model selection by MAE</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-green-400">✓</span>
                    <span>Confidence intervals (95% CI)</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-green-400">✓</span>
                    <span>Envelope shaping prevents divergence</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-green-400">✓</span>
                    <span>Persistent accuracy log (minute-based)</span>
                  </li>
                </ul>
              </div>

              <div className="bg-gray-900/60 p-6 rounded-lg border border-gray-700">
                <h4 className="text-lg font-semibold text-white mb-3">🔧 Technical Details</h4>
                <ul className="space-y-2 text-gray-300 text-sm">
                  <li><strong>Data Source:</strong> historian_raw.historian_timeseries (PostgreSQL)</li>
                  <li><strong>History Window:</strong> 2 hours (120 minutes)</li>
                  <li><strong>Forecast Horizon:</strong> 30 minutes ahead</li>
                  <li><strong>Resolution:</strong> 1-minute resampling</li>
                  <li><strong>Holdout Split:</strong> 75% train / 25% test</li>
                  <li><strong>Update Frequency:</strong> Frozen until horizon expires (~30 min)</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
