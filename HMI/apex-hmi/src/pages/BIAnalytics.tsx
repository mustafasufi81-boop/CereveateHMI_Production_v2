/**
 * BI Analytics Dashboard
 * ======================
 * Full analytics dashboard — replacement for the old HistoricalTrends (port 6004).
 * Reads ALL data from PostgreSQL via Flask /api/bi/* endpoints (no Parquet files).
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Activity, RefreshCw, BarChart2, Search, AlertTriangle } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, Legend,
} from "recharts";
import { useAuth } from "@/context/auth-context";

const API = "http://localhost:6001";

interface TagMeta { tag_id: string; record_count: number; first_seen: string; last_seen: string; }
interface TrendRow  { timestamp: string; value: number | null; }
interface Baseline  { tag_id: string; mean: number; std_dev: number; std: number; min: number; max: number; p25: number; p50: number; p75: number; count: number; upper_bound: number; lower_bound: number; }
interface Warning   { id: number; time: string; tag_id: string; warning_level: number; warning_type: string; current_value: number | null; deviation_pct: number | null; message: string; }
const LEVEL_COLOR: Record<number, string> = { 1: "#60A5FA", 2: "#FBBF24", 3: "#F97316", 4: "#EF4444" };
const LEVEL_LABEL: Record<number, string> = { 1: "INFO", 2: "CAUTION", 3: "WARNING", 4: "ALERT" };
function iso(d: Date) { return d.toISOString().slice(0, 16); }
function fmtVal(v: number | null) { return v == null ? "—" : Number(v).toFixed(3); }

export default function BIAnalytics() {
  const navigate  = useNavigate();
  const [searchParams] = useSearchParams();
  const { token } = useAuth();

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const [tags,        setTags]        = useState<TagMeta[]>([]);
  const [search,      setSearch]      = useState("");
  // Pre-select tag from ?tag= URL param (passed by openPredictiveTrend in HMI)
  const [selectedTag, setSelectedTag] = useState<string | null>(
    () => searchParams.get("tag") || null
  );

  const now = new Date();
  const [endDt,   setEndDt]   = useState(iso(now));
  const [startDt, setStartDt] = useState(iso(new Date(now.getTime() - 2 * 3600_000)));

  const [trendData, setTrendData] = useState<TrendRow[]>([]);
  const [baseline,  setBaseline]  = useState<Baseline | null>(null);
  const [warnings,  setWarnings]  = useState<Warning[]>([]);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/bi/tags`, { headers })
      .then(r => r.json())
      .then(d => setTags(d.tags || []))
      .catch(() => setError("Failed to load tags"));
  }, [token]);

  const load = useCallback(async () => {
    if (!selectedTag) return;
    setLoading(true); setError(null);
    try {
      const body = JSON.stringify({ tag_ids: [selectedTag], start: startDt + ":00", end: endDt + ":00" });
      const [tRes, bRes] = await Promise.all([
        fetch(`${API}/api/bi/trends`,    { method: "POST", headers, body }),
        fetch(`${API}/api/bi/baselines`, { method: "POST", headers, body }),
      ]);
      const tJson = await tRes.json();
      const bJson = await bRes.json();

      // /api/bi/trends returns { success, data: [{Timestamp, tagId: value, ...}] }
      const raw: Record<string, unknown>[] = tJson.data || [];
      setTrendData(raw.map(r => ({
        timestamp: String(r["Timestamp"] ?? ""),
        value: r[selectedTag] != null ? Number(r[selectedTag]) : null,
      })));

      // /api/bi/baselines returns { success, baselines: { tagId: {mean, std, min, max, p25, p50, p75, count} } }
      const blMap = bJson.baselines as Record<string, { mean: number; std: number; min: number; max: number; p25: number; p50: number; p75: number; count: number }> || {};
      const blRaw = blMap[selectedTag];
      if (blRaw) {
        setBaseline({
          tag_id:       selectedTag,
          mean:         blRaw.mean,
          std_dev:      blRaw.std,
          std:          blRaw.std,
          min:          blRaw.min,
          max:          blRaw.max,
          p25:          blRaw.p25,
          p50:          blRaw.p50,
          p75:          blRaw.p75,
          count:        blRaw.count,
          upper_bound:  blRaw.mean + 2 * blRaw.std,
          lower_bound:  blRaw.mean - 2 * blRaw.std,
        });
      } else {
        setBaseline(null);
      }

      // Fetch active PEWS warnings for this tag separately
      try {
        const wRes = await fetch(`${API}/api/pews/warnings`, { headers });
        const wJson = await wRes.json();
        setWarnings((wJson.warnings || []).filter((w: Warning) => w.tag_id === selectedTag));
      } catch { setWarnings([]); }
    } catch { setError("Failed to load data"); }
    finally { setLoading(false); }
  }, [selectedTag, startDt, endDt, token]);

  useEffect(() => { load(); }, [load]);

  function fmtTick(ts: string) {
    try { return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
    catch { return ts; }
  }

  const filtered  = tags.filter(t => t.tag_id.toLowerCase().includes(search.toLowerCase()));
  const chartData = trendData.filter(r => r.value != null);
  const tagWarns  = warnings.filter(w => w.tag_id === selectedTag);

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a", display: "flex", flexDirection: "column", fontFamily: "Consolas, monospace" }}>

      {/* Top Bar */}
      <div style={{ borderBottom: "1px solid #1e293b", background: "#0a1628", padding: "10px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 50 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <button onClick={() => navigate(-1)} style={{ display: "flex", alignItems: "center", gap: "6px", background: "none", border: "1px solid #334155", borderRadius: "6px", color: "#94a3b8", padding: "5px 12px", cursor: "pointer", fontSize: "12px" }}>
            <ArrowLeft size={13} /> Back
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <BarChart2 size={20} color="#60a5fa" />
            <div>
              <div style={{ fontSize: "16px", fontWeight: "bold", color: "#f1f5f9" }}>BI Analytics Dashboard</div>
              <div style={{ fontSize: "11px", color: "#64748b" }}>
                {selectedTag ? <>Tag: <span style={{ color: "#60a5fa" }}>{selectedTag}</span></> : "Select a tag from the left panel"}
              </div>
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Activity size={14} color="#34d399" />
          <span style={{ fontSize: "11px", color: "#94a3b8" }}>PostgreSQL Live</span>
        </div>
      </div>

      {/* Body */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", minHeight: 0 }}>

        {/* Sidebar */}
        <div style={{ width: "210px", minWidth: "210px", borderRight: "1px solid #1e293b", background: "#0a1628", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ padding: "8px", borderBottom: "1px solid #1e293b" }}>
            <div style={{ position: "relative" }}>
              <Search size={11} style={{ position: "absolute", left: "8px", top: "50%", transform: "translateY(-50%)", color: "#64748b" }} />
              <input style={{ width: "100%", background: "#1e293b", border: "1px solid #334155", borderRadius: "5px", padding: "5px 8px 5px 24px", color: "#f1f5f9", fontSize: "11px", outline: "none", boxSizing: "border-box" }}
                placeholder="Search tags..." value={search} onChange={e => setSearch(e.target.value)} />
            </div>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "4px" }}>
            {filtered.length === 0 && <div style={{ textAlign: "center", color: "#475569", fontSize: "10px", padding: "16px 6px" }}>{tags.length === 0 ? "Loading..." : "No matches"}</div>}
            {filtered.map(t => (
              <button key={t.tag_id} onClick={() => setSelectedTag(t.tag_id)}
                style={{ width: "100%", textAlign: "left", background: selectedTag === t.tag_id ? "rgba(59,130,246,0.15)" : "transparent", border: selectedTag === t.tag_id ? "1px solid #3b82f6" : "1px solid transparent", borderRadius: "5px", padding: "6px 8px", cursor: "pointer", marginBottom: "2px" }}>
                <div style={{ fontSize: "10px", color: selectedTag === t.tag_id ? "#60a5fa" : "#cbd5e1", wordBreak: "break-all" }}>{t.tag_id}</div>
                <div style={{ fontSize: "9px", color: "#475569" }}>{t.record_count.toLocaleString()} pts</div>
              </button>
            ))}
          </div>
          <div style={{ padding: "6px", borderTop: "1px solid #1e293b", fontSize: "9px", color: "#475569", textAlign: "center" }}>{tags.length} tags in DB</div>
        </div>

        {/* Main */}
        <div style={{ flex: 1, overflowY: "auto", padding: "14px", display: "flex", flexDirection: "column", gap: "12px" }}>
          {!selectedTag && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#475569", gap: "10px", marginTop: "80px" }}>
              <BarChart2 size={48} color="#1e293b" />
              <div style={{ fontSize: "15px", color: "#64748b" }}>Select a tag from the left panel</div>
              <div style={{ fontSize: "11px", color: "#475569" }}>Historical trends, baseline stats and warnings will appear here</div>
            </div>
          )}

          {selectedTag && <>
            {/* Time range */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span style={{ fontSize: "10px", color: "#64748b" }}>From</span>
              <input type="datetime-local" value={startDt} onChange={e => setStartDt(e.target.value)}
                style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "5px", color: "#cbd5e1", padding: "4px 8px", fontSize: "11px", outline: "none" }} />
              <span style={{ fontSize: "10px", color: "#64748b" }}>To</span>
              <input type="datetime-local" value={endDt} onChange={e => setEndDt(e.target.value)}
                style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "5px", color: "#cbd5e1", padding: "4px 8px", fontSize: "11px", outline: "none" }} />
              {[{l:"1H",ms:3600e3},{l:"2H",ms:7200e3},{l:"6H",ms:21600e3},{l:"12H",ms:43200e3},{l:"24H",ms:86400e3}].map(p => (
                <button key={p.l} onClick={() => { const n=new Date(); setEndDt(iso(n)); setStartDt(iso(new Date(n.getTime()-p.ms))); }}
                  style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "5px", color: "#94a3b8", padding: "4px 9px", fontSize: "10px", cursor: "pointer" }}>{p.l}</button>
              ))}
              <button onClick={load} disabled={loading}
                style={{ display: "flex", alignItems: "center", gap: "5px", background: "#1d4ed8", border: "none", borderRadius: "5px", color: "#fff", padding: "4px 12px", fontSize: "11px", cursor: "pointer", opacity: loading ? 0.6 : 1 }}>
                <RefreshCw size={11} /> {loading ? "Loading..." : "Refresh"}
              </button>
              {error && <span style={{ fontSize: "10px", color: "#ef4444" }}>{error}</span>}
            </div>

            {/* Chart */}
            <div style={{ background: "#0a1628", border: "1px solid #1e293b", borderRadius: "8px", padding: "14px" }}>
              <div style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "8px" }}>
                Historical Trend — {selectedTag} <span style={{ color: "#334155", marginLeft: "10px" }}>{chartData.length} pts</span>
              </div>
              {chartData.length === 0 ? (
                <div style={{ height: "220px", display: "flex", alignItems: "center", justifyContent: "center", color: "#475569", fontSize: "12px" }}>
                  {loading ? "Loading data..." : "No data in selected range"}
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 6 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="timestamp" tickFormatter={fmtTick} tick={{ fill: "#64748b", fontSize: 9 }} minTickGap={60} />
                    <YAxis tick={{ fill: "#64748b", fontSize: 9 }} />
                    <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "5px", fontSize: "10px" }}
                      labelFormatter={v => new Date(v).toLocaleString()} formatter={(v: number) => [v?.toFixed(4), selectedTag]} />
                    <Legend wrapperStyle={{ fontSize: "10px" }} />
                    {baseline && <ReferenceLine y={baseline.mean}        stroke="#60a5fa" strokeDasharray="4 4" label={{ value: "μ",   fill: "#60a5fa", fontSize: 9 }} />}
                    {baseline && <ReferenceLine y={baseline.upper_bound} stroke="#f97316" strokeDasharray="3 3" label={{ value: "+2σ", fill: "#f97316", fontSize: 9 }} />}
                    {baseline && <ReferenceLine y={baseline.lower_bound} stroke="#f97316" strokeDasharray="3 3" label={{ value: "-2σ", fill: "#f97316", fontSize: 9 }} />}
                    <Line type="monotone" dataKey="value" name={selectedTag} stroke="#34d399" dot={false} strokeWidth={1.5} connectNulls={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Stats + Warnings */}
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              {/* Baseline Stats */}
              <div style={{ flex: "1 1 280px", background: "#0a1628", border: "1px solid #1e293b", borderRadius: "8px", padding: "14px" }}>
                <div style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "10px" }}>Baseline Statistics</div>
                {!baseline ? <div style={{ color: "#475569", fontSize: "11px" }}>No baseline data available</div> : (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                    {[
                      ["Mean (μ)",       fmtVal(baseline.mean)],
                      ["Std Dev (σ)",    fmtVal(baseline.std_dev)],
                      ["Min",            fmtVal(baseline.min)],
                      ["Max",            fmtVal(baseline.max)],
                      ["P25",            fmtVal(baseline.p25)],
                      ["P50 (Median)",   fmtVal(baseline.p50)],
                      ["P75",            fmtVal(baseline.p75)],
                      ["Count",          baseline.count?.toLocaleString()],
                      ["Upper (+2σ)",    fmtVal(baseline.upper_bound)],
                      ["Lower (−2σ)",    fmtVal(baseline.lower_bound)],
                    ].map(([label, value]) => (
                      <div key={label as string} style={{ background: "#1e293b", borderRadius: "5px", padding: "7px 10px" }}>
                        <div style={{ fontSize: "9px", color: "#64748b" }}>{label}</div>
                        <div style={{ fontSize: "13px", fontWeight: "bold", color: "#f1f5f9" }}>{value}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Warnings */}
              <div style={{ flex: "1 1 280px", background: "#0a1628", border: "1px solid #1e293b", borderRadius: "8px", padding: "14px" }}>
                <div style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "10px", display: "flex", alignItems: "center", gap: "6px" }}>
                  <AlertTriangle size={11} /> Active Warnings
                  {tagWarns.length > 0 && <span style={{ background: "#ef4444", borderRadius: "10px", padding: "1px 7px", fontSize: "9px", color: "#fff" }}>{tagWarns.length}</span>}
                </div>
                {tagWarns.length === 0 ? (
                  <div style={{ color: "#475569", fontSize: "11px" }}>✓ No active warnings for this tag</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "5px", maxHeight: "260px", overflowY: "auto" }}>
                    {tagWarns.map(w => (
                      <div key={w.id} style={{ background: "#1e293b", borderRadius: "5px", padding: "7px 10px", borderLeft: `3px solid ${LEVEL_COLOR[w.warning_level] ?? "#64748b"}` }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                          <span style={{ fontSize: "9px", fontWeight: "bold", color: LEVEL_COLOR[w.warning_level] }}>{LEVEL_LABEL[w.warning_level] ?? "WARN"}</span>
                          <span style={{ fontSize: "9px", color: "#475569" }}>{w.warning_type}</span>
                        </div>
                        <div style={{ fontSize: "10px", color: "#cbd5e1" }}>{w.message}</div>
                        {w.current_value != null && (
                          <div style={{ fontSize: "9px", color: "#94a3b8", marginTop: "2px" }}>
                            Value: <span style={{ color: "#f1f5f9" }}>{w.current_value.toFixed(3)}</span>
                            {w.deviation_pct != null && <span style={{ marginLeft: "8px" }}>Dev: {w.deviation_pct.toFixed(1)}%</span>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>}
        </div>
      </div>
    </div>
  );
}
