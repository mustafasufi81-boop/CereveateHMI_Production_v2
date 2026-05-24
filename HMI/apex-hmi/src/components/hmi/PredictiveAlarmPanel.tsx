/**
 * PredictiveAlarmPanel
 * =====================
 * Displays the live state of the predictive pre-alarm engine:
 *   - Engine status card (running / cycle count / suspicious tag count)
 *   - Active pre-alarm list with acknowledge button
 *   - Tag configuration table (add / edit / disable)
 *   - Screener state table (per-tag slope + suspicious flag)
 *
 * All data is read from /api/predictive/* endpoints.
 * Engine control (start/stop/force cycle) is exposed to admin users.
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "@/context/auth-context";

const API = "http://localhost:6001";

// ── Types ─────────────────────────────────────────────────────────────────────

interface EngineStatus {
  running: boolean;
  cycle_count: number;
  last_cycle_at: string | null;
  last_error: string | null;
  suspicious_tags: string[];
  screener_cache_size: number;
  active_alarm_count: number;
}

interface PredAlarm {
  id: number;
  tag_id: string;
  direction: "HIGH" | "LOW" | "HIHI" | "LOLO";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  predicted_value: number | null;
  limit_value: number | null;
  eta_minutes: number | null;
  predicted_breach_at: string | null;
  model_used: string | null;
  raised_at: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  notes: string | null;
  suppressed_until: string | null;
}

interface TagConfig {
  tag_id: string;
  tag_description: string | null;
  unit: string | null;
  hi_hi_limit: number | null;
  hi_limit: number | null;
  lo_limit: number | null;
  lo_lo_limit: number | null;
  deadband: number;
  preferred_model: string;
  forecast_horizon_minutes: number;
  suppression_window_minutes: number;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface ScreenerRow {
  tag_id: string;
  is_suspicious: boolean;
  reason: string | null;
  slope: number | null;
  quality_score: number | null;
  n_points: number | null;
  last_screened: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const DIRECTION_COLOR: Record<string, string> = {
  HIHI: "#ef4444",
  HIGH: "#f97316",
  LOW:  "#3b82f6",
  LOLO: "#6366f1",
};

const CONFIDENCE_BADGE: Record<string, string> = {
  HIGH:   "bg-red-100 text-red-700",
  MEDIUM: "bg-yellow-100 text-yellow-700",
  LOW:    "bg-green-100 text-green-700",
};

const PRIORITY_LABEL: Record<number, string> = {
  1: "CRITICAL",
  2: "HIGH",
  3: "MEDIUM",
  4: "LOW",
  5: "BACKGROUND",
};

function fmtTs(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PredictiveAlarmPanel() {
  const { token } = useAuth();

  const [status,    setStatus]    = useState<EngineStatus | null>(null);
  const [alarms,    setAlarms]    = useState<PredAlarm[]>([]);
  const [tags,      setTags]      = useState<TagConfig[]>([]);
  const [screener,  setScreener]  = useState<ScreenerRow[]>([]);
  const [activeTab, setActiveTab] = useState<"alarms" | "tags" | "screener">("alarms");

  const [loading,   setLoading]   = useState(false);
  const [ackNote,   setAckNote]   = useState<Record<number, string>>({});
  const [error,     setError]     = useState<string | null>(null);

  // Tag form state
  const [showAddTag, setShowAddTag] = useState(false);
  const emptyForm = (): Partial<TagConfig> => ({
    tag_id: "", tag_description: "", unit: "",
    hi_hi_limit: undefined, hi_limit: undefined,
    lo_limit: undefined, lo_lo_limit: undefined,
    deadband: 0, preferred_model: "auto",
    forecast_horizon_minutes: 30,
    suppression_window_minutes: 60,
    priority: 3, enabled: true,
  });
  const [tagForm, setTagForm] = useState<Partial<TagConfig>>(emptyForm());

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch helpers ────────────────────────────────────────────────────────

  const authHeaders = useCallback(() => ({
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  }), [token]);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/predictive/status`, { headers: authHeaders() });
      const j   = await res.json();
      if (j.success) setStatus(j.data);
    } catch {/* silent */}
  }, [authHeaders]);

  const fetchAlarms = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/predictive/alarms?page_size=100`, { headers: authHeaders() });
      const j   = await res.json();
      if (j.success) setAlarms(j.data ?? []);
    } catch {/* silent */}
  }, [authHeaders]);

  const fetchTags = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/predictive/tags`, { headers: authHeaders() });
      const j   = await res.json();
      if (j.success) setTags(j.data ?? []);
    } catch {/* silent */}
  }, [authHeaders]);

  const fetchScreener = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/predictive/screener`, { headers: authHeaders() });
      const j   = await res.json();
      if (j.success) setScreener(j.data ?? []);
    } catch {/* silent */}
  }, [authHeaders]);

  const refreshAll = useCallback(async () => {
    await Promise.all([fetchStatus(), fetchAlarms(), fetchTags(), fetchScreener()]);
  }, [fetchStatus, fetchAlarms, fetchTags, fetchScreener]);

  // Auto-poll every 15 s
  useEffect(() => {
    refreshAll();
    pollRef.current = setInterval(refreshAll, 15_000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [refreshAll]);

  // ── Engine control ───────────────────────────────────────────────────────

  async function engineAction(action: "start" | "stop" | "cycle") {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API}/api/predictive/engine/${action}`, {
        method: "POST", headers: authHeaders(),
      });
      const j = await res.json();
      if (!j.success) setError(j.error ?? "Failed");
      await refreshAll();
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Acknowledge ──────────────────────────────────────────────────────────

  async function ackAlarm(id: number) {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API}/api/predictive/alarms/${id}/ack`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ notes: ackNote[id] ?? "" }),
      });
      const j = await res.json();
      if (!j.success) setError(j.error ?? "Failed");
      await fetchAlarms();
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Save tag config ──────────────────────────────────────────────────────

  async function saveTag(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API}/api/predictive/tags`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(tagForm),
      });
      const j = await res.json();
      if (!j.success) { setError(j.error ?? "Failed"); return; }
      setShowAddTag(false);
      setTagForm(emptyForm());
      await fetchTags();
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function disableTag(tag_id: string) {
    if (!confirm(`Disable monitoring for ${tag_id}?`)) return;
    setLoading(true);
    try {
      await fetch(`${API}/api/predictive/tags/${encodeURIComponent(tag_id)}`, {
        method: "DELETE", headers: authHeaders(),
      });
      await fetchTags();
    } finally {
      setLoading(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-4 p-4 text-sm text-gray-800">

      {/* ── Status Bar ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 items-center bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <span className={`h-3 w-3 rounded-full ${status?.running ? "bg-green-500 animate-pulse" : "bg-gray-400"}`} />
          <span className="font-semibold">
            Predictive Engine — {status?.running ? "Running" : "Stopped"}
          </span>
        </div>
        {status && (
          <>
            <span className="text-gray-500">Cycles: <b>{status.cycle_count}</b></span>
            <span className="text-gray-500">Suspicious: <b>{status.suspicious_tags.length}</b></span>
            <span className="text-gray-500">Active Alarms: <b className="text-red-600">{status.active_alarm_count}</b></span>
            {status.last_cycle_at && (
              <span className="text-gray-400 text-xs">Last cycle: {fmtTs(status.last_cycle_at)}</span>
            )}
          </>
        )}
        <div className="ml-auto flex gap-2">
          {!status?.running ? (
            <button
              onClick={() => engineAction("start")}
              disabled={loading}
              className="px-3 py-1 bg-green-600 text-white rounded-lg text-xs hover:bg-green-700 disabled:opacity-50"
            >▶ Start</button>
          ) : (
            <button
              onClick={() => engineAction("stop")}
              disabled={loading}
              className="px-3 py-1 bg-red-600 text-white rounded-lg text-xs hover:bg-red-700 disabled:opacity-50"
            >⏹ Stop</button>
          )}
          <button
            onClick={() => engineAction("cycle")}
            disabled={loading}
            className="px-3 py-1 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700 disabled:opacity-50"
            title="Force one immediate scan cycle"
          >⚡ Force Cycle</button>
          <button
            onClick={refreshAll}
            disabled={loading}
            className="px-3 py-1 bg-gray-100 border border-gray-300 rounded-lg text-xs hover:bg-gray-200 disabled:opacity-50"
          >↻ Refresh</button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-lg px-4 py-2 text-xs">
          {error}
        </div>
      )}

      {/* ── Tabs ───────────────────────────────────────────────────────── */}
      <div className="flex gap-1 border-b border-gray-200">
        {(["alarms", "tags", "screener"] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-xs font-medium capitalize rounded-t-lg transition-colors
              ${activeTab === tab
                ? "bg-white border border-b-white border-gray-200 text-blue-600 -mb-px"
                : "text-gray-500 hover:text-gray-700"}`}
          >
            {tab === "alarms"
              ? `🔔 Active Alarms${alarms.length ? ` (${alarms.length})` : ""}`
              : tab === "tags" ? `⚙ Tag Config (${tags.length})`
              : `🔍 Screener State`}
          </button>
        ))}
      </div>

      {/* ── Active Alarms Tab ───────────────────────────────────────────── */}
      {activeTab === "alarms" && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          {alarms.length === 0 ? (
            <div className="p-8 text-center text-gray-400">
              ✅ No active pre-alarms
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    {["Tag", "Direction", "Confidence", "ETA (min)", "Predicted", "Limit",
                      "Model", "Raised", "Acknowledge"].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {alarms.map(a => (
                    <tr key={a.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono max-w-[180px] truncate" title={a.tag_id}>{a.tag_id}</td>
                      <td className="px-3 py-2">
                        <span
                          className="px-2 py-0.5 rounded font-bold text-white text-[10px]"
                          style={{ backgroundColor: DIRECTION_COLOR[a.direction] ?? "#6b7280" }}
                        >{a.direction}</span>
                      </td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${CONFIDENCE_BADGE[a.confidence]}`}>
                          {a.confidence}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {a.eta_minutes != null ? `${a.eta_minutes} min` : "—"}
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {a.predicted_value != null ? a.predicted_value.toFixed(2) : "—"}
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {a.limit_value != null ? a.limit_value.toFixed(2) : "—"}
                      </td>
                      <td className="px-3 py-2 uppercase text-gray-500">{a.model_used ?? "—"}</td>
                      <td className="px-3 py-2 whitespace-nowrap text-gray-500">{fmtTs(a.raised_at)}</td>
                      <td className="px-3 py-2">
                        <div className="flex gap-1 items-center">
                          <input
                            type="text"
                            placeholder="Note…"
                            value={ackNote[a.id] ?? ""}
                            onChange={e => setAckNote(prev => ({ ...prev, [a.id]: e.target.value }))}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-24"
                          />
                          <button
                            onClick={() => ackAlarm(a.id)}
                            disabled={loading}
                            className="px-2 py-0.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap"
                          >✓ Ack</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Tag Config Tab ──────────────────────────────────────────────── */}
      {activeTab === "tags" && (
        <div className="flex flex-col gap-3">
          <div className="flex justify-between items-center">
            <span className="text-gray-500">{tags.length} tag(s) configured</span>
            <button
              onClick={() => { setShowAddTag(v => !v); setTagForm(emptyForm()); }}
              className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700"
            >+ Add Tag</button>
          </div>

          {/* Add/Edit form */}
          {showAddTag && (
            <form
              onSubmit={saveTag}
              className="bg-blue-50 border border-blue-200 rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 gap-3"
            >
              <div className="col-span-2 md:col-span-4 font-semibold text-blue-700 text-sm mb-1">New Tag Configuration</div>

              {[
                { label: "Tag ID *", key: "tag_id", type: "text", required: true },
                { label: "Description", key: "tag_description", type: "text" },
                { label: "Unit", key: "unit", type: "text" },
                { label: "HiHi Limit", key: "hi_hi_limit", type: "number" },
                { label: "Hi Limit", key: "hi_limit", type: "number" },
                { label: "Lo Limit", key: "lo_limit", type: "number" },
                { label: "LoLo Limit", key: "lo_lo_limit", type: "number" },
                { label: "Deadband", key: "deadband", type: "number" },
                { label: "Horizon (min)", key: "forecast_horizon_minutes", type: "number" },
                { label: "Suppression (min)", key: "suppression_window_minutes", type: "number" },
              ].map(f => (
                <label key={f.key} className="flex flex-col gap-1">
                  <span className="text-xs text-gray-600">{f.label}</span>
                  <input
                    type={f.type}
                    required={f.required}
                    value={(tagForm as Record<string, unknown>)[f.key] as string ?? ""}
                    onChange={e => setTagForm(prev => ({
                      ...prev,
                      [f.key]: f.type === "number"
                        ? (e.target.value === "" ? undefined : Number(e.target.value))
                        : e.target.value,
                    }))}
                    className="border border-gray-300 rounded px-2 py-1 text-xs"
                  />
                </label>
              ))}

              <label className="flex flex-col gap-1">
                <span className="text-xs text-gray-600">Model</span>
                <select
                  value={tagForm.preferred_model ?? "auto"}
                  onChange={e => setTagForm(prev => ({ ...prev, preferred_model: e.target.value }))}
                  className="border border-gray-300 rounded px-2 py-1 text-xs"
                >
                  {["auto", "lr", "hw", "fft", "arima"].map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-gray-600">Priority</span>
                <select
                  value={tagForm.priority ?? 3}
                  onChange={e => setTagForm(prev => ({ ...prev, priority: Number(e.target.value) }))}
                  className="border border-gray-300 rounded px-2 py-1 text-xs"
                >
                  {[1, 2, 3, 4, 5].map(p => (
                    <option key={p} value={p}>{p} — {PRIORITY_LABEL[p]}</option>
                  ))}
                </select>
              </label>

              <div className="col-span-2 md:col-span-4 flex gap-2 mt-1">
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700 disabled:opacity-50"
                >Save</button>
                <button
                  type="button"
                  onClick={() => setShowAddTag(false)}
                  className="px-4 py-1.5 bg-gray-100 border border-gray-300 rounded-lg text-xs hover:bg-gray-200"
                >Cancel</button>
              </div>
            </form>
          )}

          {/* Tags table */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    {["Tag ID", "Hi / HiHi", "Lo / LoLo", "Model", "Horizon", "Priority", "Enabled", "Actions"].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tags.map(t => (
                    <tr key={t.tag_id} className={`border-b border-gray-100 hover:bg-gray-50 ${!t.enabled ? "opacity-40" : ""}`}>
                      <td className="px-3 py-2 font-mono max-w-[200px] truncate" title={t.tag_id}>
                        {t.tag_id}
                        {t.tag_description && <div className="text-gray-400 text-[10px]">{t.tag_description}</div>}
                      </td>
                      <td className="px-3 py-2 font-mono text-orange-700">
                        {t.hi_limit ?? "—"} / {t.hi_hi_limit ?? "—"}
                      </td>
                      <td className="px-3 py-2 font-mono text-blue-700">
                        {t.lo_limit ?? "—"} / {t.lo_lo_limit ?? "—"}
                      </td>
                      <td className="px-3 py-2 uppercase">{t.preferred_model}</td>
                      <td className="px-3 py-2">{t.forecast_horizon_minutes} min</td>
                      <td className="px-3 py-2">
                        <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 text-[10px]">
                          {PRIORITY_LABEL[t.priority] ?? t.priority}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${t.enabled ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                          {t.enabled ? "Yes" : "No"}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {t.enabled && (
                          <button
                            onClick={() => disableTag(t.tag_id)}
                            disabled={loading}
                            className="px-2 py-0.5 bg-red-50 border border-red-200 text-red-600 rounded text-[10px] hover:bg-red-100 disabled:opacity-50"
                          >Disable</button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {tags.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                        No tags configured. Click "+ Add Tag" to start monitoring.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── Screener State Tab ──────────────────────────────────────────── */}
      {activeTab === "screener" && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  {["Tag ID", "Suspicious", "Reason", "Slope", "Quality", "Points", "Last Screened"].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {screener.map(r => (
                  <tr key={r.tag_id} className={`border-b border-gray-100 hover:bg-gray-50 ${r.is_suspicious ? "bg-orange-50" : ""}`}>
                    <td className="px-3 py-2 font-mono max-w-[200px] truncate" title={r.tag_id}>{r.tag_id}</td>
                    <td className="px-3 py-2">
                      {r.is_suspicious
                        ? <span className="px-2 py-0.5 rounded bg-orange-100 text-orange-700 font-bold text-[10px]">⚠ YES</span>
                        : <span className="px-2 py-0.5 rounded bg-green-50 text-green-600 text-[10px]">✓ No</span>}
                    </td>
                    <td className="px-3 py-2 text-gray-500">{r.reason ?? "—"}</td>
                    <td className="px-3 py-2 font-mono">
                      {r.slope != null ? r.slope.toExponential(2) : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono">
                      {r.quality_score != null ? (r.quality_score * 100).toFixed(0) + "%" : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono">{r.n_points ?? "—"}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-gray-400">{fmtTs(r.last_screened)}</td>
                  </tr>
                ))}
                {screener.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                      No screener data yet — start the engine and wait for the first cycle.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
}
