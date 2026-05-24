/**
 * HmiAnalyticsTab
 * ===============
 * Self-contained PEWS + BI Analytics panel embedded directly inside the
 * main HMI content area. No page navigation. Sub-tabs: PEWS | BI.
 *
 * Clicking a warning row → calls onTagClick → opens PredictiveTrendModal in HMI.
 */
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/auth-context";

const API = "http://localhost:6001";
const POLL_MS = 60_000;

// ── Types ────────────────────────────────────────────────────────────────────
interface PewsWarning {
  id: number;
  time: string;
  tag_id: string;
  warning_level: number;
  warning_type: string;
  current_value: number | null;
  deviation_pct: number | null;
  message: string;
  is_acknowledged?: boolean;
  acknowledged?: boolean;
}

interface PewsStatus {
  baseline_count: number;
  oldest_baseline: string | null;
  newest_baseline: string | null;
  warning_summary: Record<string, number>;
  total_active_warnings: number;
}

interface Props {
  onTagClick: (tagId: string, tagName: string) => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const LEVEL_COLOR: Record<number, string> = { 1: "#60A5FA", 2: "#FBBF24", 3: "#F97316", 4: "#EF4444" };
const LEVEL_LABEL: Record<number, string> = { 1: "INFO", 2: "CAUTION", 3: "WARNING", 4: "ALERT" };

function fmtTime(iso: string) {
  try { return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
}

function calcHealth(status: PewsStatus | null, warnings: PewsWarning[]) {
  if (!status || !warnings.length) return 100;
  const weights: Record<number, number> = { 1: 1, 2: 3, 3: 7, 4: 15 };
  const total = status.baseline_count || 1;
  const penalty = Object.entries(status.warning_summary).reduce(
    (acc, [lvl, cnt]) => acc + (weights[Number(lvl)] ?? 1) * cnt, 0
  );
  return Math.max(0, Math.round(100 - (penalty / total) * 10));
}

// ── Component ─────────────────────────────────────────────────────────────────
export function HmiAnalyticsTab({ onTagClick }: Props) {
  const { token } = useAuth();
  const headers = { Authorization: `Bearer ${token}` };
  const navigate = useNavigate();

  const [subTab, setSubTab]       = useState<"pews">("pews");
  const [warnings, setWarnings]   = useState<PewsWarning[]>([]);
  const [status, setStatus]       = useState<PewsStatus | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const [wRes, sRes] = await Promise.all([
        fetch(`${API}/api/pews/warnings`, { headers }),
        fetch(`${API}/api/pews/status`,   { headers }),
      ]);
      const wData = await wRes.json();
      const sData = await sRes.json();
      if (wData.success) setWarnings(wData.warnings ?? []);
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
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  const ack = async (id: number) => {
    try {
      await fetch(`${API}/api/pews/warnings/${id}/ack`, { method: "POST", headers });
      setWarnings(prev => prev.filter(w => w.id !== id));
    } catch { /* ignore */ }
  };

  const health = calcHealth(status, warnings);
  const healthColor = health >= 90 ? "#34D399" : health >= 70 ? "#FBBF24" : "#EF4444";

  const S: Record<string, React.CSSProperties> = {
    root: { height: "100%", display: "flex", flexDirection: "column", fontFamily: "Consolas, monospace", backgroundColor: "#0d1117" },
    tabBar: { display: "flex", alignItems: "center", borderBottom: "1px solid #374151", backgroundColor: "#111827", padding: "0 12px", gap: "4px", flexShrink: 0 },
    body: { flex: 1, overflow: "auto", padding: "12px", display: "flex", flexDirection: "column", gap: "12px" },
  };

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: "8px 16px",
    fontSize: "11px",
    fontWeight: 700,
    letterSpacing: "0.8px",
    cursor: "pointer",
    background: "none",
    border: "none",
    borderBottom: `2px solid ${active ? "#FBBF24" : "transparent"}`,
    color: active ? "#FCD34D" : "#6B7280",
    fontFamily: "Consolas, monospace",
    transition: "color 0.15s",
  });

  return (
    <div style={S.root}>
      {/* ── Sub-tab bar ── */}
      <div style={S.tabBar}>
        <button style={tabStyle(subTab === "pews")} onClick={() => setSubTab("pews")}>⚠ EARLY WARNINGS</button>
        <button style={tabStyle(false)}   onClick={() => window.open("http://localhost:6004", "HistoricalTrends", "width=1440,height=900,resizable=yes,scrollbars=yes")}>📊 BI</button>
        <div style={{ flex: 1 }} />
        {/* Health score */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "4px 0" }}>
          <span style={{ fontSize: "10px", color: "#6B7280" }}>SYSTEM HEALTH</span>
          <span style={{
            fontSize: "18px", fontWeight: 900, color: healthColor,
            textShadow: `0 0 8px ${healthColor}55`,
          }}>{health}%</span>
          <button
            onClick={load}
            style={{ padding: "3px 8px", fontSize: "10px", background: "rgba(255,255,255,0.05)", border: "1px solid #374151", color: "#9CA3AF", cursor: "pointer", borderRadius: "3px", fontFamily: "Consolas, monospace" }}
          >↻</button>
          {lastRefresh && <span style={{ fontSize: "9px", color: "#4B5563" }}>{lastRefresh.toLocaleTimeString()}</span>}
        </div>
      </div>

      {/* ── PEWS tab ── */}
      {subTab === "pews" && (
        <div style={S.body}>
          {error && (
            <div style={{ padding: "10px 12px", backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid #EF4444", borderRadius: "6px", color: "#FCA5A5", fontSize: "11px" }}>
              ⚠ {error} — Is the PEWS service running on port 6001?
            </div>
          )}

          {/* Summary cards */}
          {status && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "8px" }}>
              <div style={{ gridColumn: "1", padding: "10px 12px", backgroundColor: "#161b27", border: "1px solid #374151", borderRadius: "6px" }}>
                <div style={{ fontSize: "9px", color: "#6B7280", marginBottom: "4px", letterSpacing: "0.8px" }}>BASELINES</div>
                <div style={{ fontSize: "20px", fontWeight: 900, color: "#60A5FA" }}>{status.baseline_count}</div>
                <div style={{ fontSize: "9px", color: "#4B5563" }}>tags monitored</div>
              </div>
              <div style={{ gridColumn: "2", padding: "10px 12px", backgroundColor: "#161b27", border: "1px solid #374151", borderRadius: "6px" }}>
                <div style={{ fontSize: "9px", color: "#6B7280", marginBottom: "4px", letterSpacing: "0.8px" }}>TOTAL ACTIVE</div>
                <div style={{ fontSize: "20px", fontWeight: 900, color: warnings.length > 0 ? "#EF4444" : "#34D399" }}>{warnings.length}</div>
                <div style={{ fontSize: "9px", color: "#4B5563" }}>warnings</div>
              </div>
              {([4, 3, 2] as const).map((lvl, i) => (
                <div key={lvl} style={{ gridColumn: `${i + 3}`, padding: "10px 12px", backgroundColor: "#161b27", border: `1px solid ${LEVEL_COLOR[lvl]}44`, borderRadius: "6px" }}>
                  <div style={{ fontSize: "9px", color: LEVEL_COLOR[lvl], marginBottom: "4px", letterSpacing: "0.8px" }}>{LEVEL_LABEL[lvl]}</div>
                  <div style={{ fontSize: "20px", fontWeight: 900, color: LEVEL_COLOR[lvl] }}>
                    {status.warning_summary[String(lvl)] ?? 0}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Warnings table */}
          <div style={{ backgroundColor: "#161b27", border: "1px solid #374151", borderRadius: "6px", overflow: "hidden" }}>
            <div style={{ padding: "8px 12px", borderBottom: "1px solid #374151", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "10px", color: "#6B7280", letterSpacing: "0.8px" }}>
                ACTIVE WARNINGS {warnings.length > 0 && `(${warnings.length})`}
              </span>
              <span style={{ fontSize: "9px", color: "#4B5563" }}>Click row to view predictive trend → graph opens</span>
            </div>

            {loading ? (
              <div style={{ padding: "24px", textAlign: "center", color: "#4B5563", fontSize: "12px" }}>Loading…</div>
            ) : warnings.length === 0 ? (
              <div style={{ padding: "32px", textAlign: "center", color: "#34D399", fontSize: "13px" }}>
                <div style={{ fontSize: "28px", marginBottom: "8px" }}>✓</div>
                No active warnings — system normal
              </div>
            ) : (
              <div style={{ maxHeight: "500px", overflowY: "auto" }}>
                {/* Header row */}
                <div style={{ display: "grid", gridTemplateColumns: "36px 80px 1fr 80px 80px 70px 56px", gap: "0", padding: "4px 12px", backgroundColor: "rgba(0,0,0,0.4)", fontSize: "9px", color: "#6B7280", letterSpacing: "0.6px" }}>
                  <span>LVL</span><span>TYPE</span><span>TAG / MESSAGE</span><span>VALUE</span><span>DEV%</span><span>TIME</span><span style={{ textAlign: "right" }}>ACK</span>
                </div>
                {warnings.map(w => (
                  <div
                    key={w.id}
                    onClick={() => onTagClick(w.tag_id, w.tag_id)}
                    title="Click to open predictive trend graph"
                    style={{
                      display: "grid",
                      gridTemplateColumns: "36px 80px 1fr 80px 80px 70px 56px",
                      gap: "0",
                      padding: "7px 12px",
                      borderBottom: "1px solid rgba(55,65,81,0.4)",
                      borderLeft: `3px solid ${LEVEL_COLOR[w.warning_level] ?? "#374151"}`,
                      cursor: "pointer",
                      alignItems: "center",
                      transition: "background-color 0.1s",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.backgroundColor = "rgba(59,130,246,0.08)")}
                    onMouseLeave={e => (e.currentTarget.style.backgroundColor = "transparent")}
                  >
                    {/* Level badge */}
                    <span style={{
                      display: "inline-flex", alignItems: "center", justifyContent: "center",
                      width: "22px", height: "16px",
                      backgroundColor: LEVEL_COLOR[w.warning_level], color: "#000",
                      fontSize: "8px", fontWeight: 900, borderRadius: "3px",
                    }}>{LEVEL_LABEL[w.warning_level]?.slice(0,1)}</span>

                    {/* Type */}
                    <span style={{ fontSize: "9px", color: "#9CA3AF", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {w.warning_type.replace(/_/g, " ")}
                    </span>

                    {/* Tag + message */}
                    <div style={{ overflow: "hidden" }}>
                      <div style={{ fontSize: "11px", fontWeight: 700, color: "#F9FAFB", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {w.tag_id} <span style={{ fontSize: "9px" }}>📈</span>
                      </div>
                      <div style={{ fontSize: "9px", color: "#9CA3AF", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.message}</div>
                    </div>

                    {/* Value */}
                    <span style={{ fontSize: "11px", color: "#F9FAFB", fontWeight: 700 }}>
                      {w.current_value !== null && w.current_value !== undefined ? w.current_value.toFixed(3) : "—"}
                    </span>

                    {/* Deviation */}
                    <span style={{ fontSize: "11px", color: w.deviation_pct !== null && Math.abs(w.deviation_pct!) > 20 ? "#F97316" : "#FBBF24", fontWeight: 700 }}>
                      {w.deviation_pct !== null ? `${w.deviation_pct > 0 ? "+" : ""}${w.deviation_pct.toFixed(1)}%` : "—"}
                    </span>

                    {/* Time */}
                    <span style={{ fontSize: "9px", color: "#6B7280" }}>{fmtTime(w.time)}</span>

                    {/* ACK button */}
                    <div style={{ textAlign: "right" }}>
                      <button
                        onClick={e => { e.stopPropagation(); ack(w.id); }}
                        style={{
                          padding: "2px 7px", fontSize: "9px",
                          backgroundColor: "rgba(99,102,241,0.2)", border: "1px solid #6366F1",
                          color: "#A5B4FC", cursor: "pointer", borderRadius: "3px",
                          fontFamily: "Consolas, monospace",
                        }}
                      >ACK</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}


    </div>
  );
}
