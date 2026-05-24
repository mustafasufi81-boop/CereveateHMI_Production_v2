/**
 * PredictiveAlertsPanel
 * =====================
 * Compact scrollable list of PEWS warning history shown in the HMI right panel.
 * Clicking a row opens the PredictiveTrendModal for that tag.
 */
import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/auth-context";

const API = "http://localhost:6001";

interface Warning {
  id: number;
  time: string;
  tag_id: string;
  warning_level: number;
  warning_type: string;
  message: string;
  current_value: number | null;
  deviation_pct: number | null;
  is_acknowledged: boolean;
}

const LEVEL_COLOR: Record<number, string> = { 1: "#60A5FA", 2: "#FBBF24", 3: "#F97316", 4: "#EF4444" };
const LEVEL_LABEL: Record<number, string> = { 1: "I", 2: "C", 3: "W", 4: "A" };

function fmtTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
}

interface Props {
  onTagClick: (tagId: string, tagName: string) => void;
}

export function PredictiveAlertsPanel({ onTagClick }: Props) {
  const { token } = useAuth();
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/pews/warnings`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const d = await r.json();
      if (d.success) setWarnings((d.warnings ?? []).slice(0, 20));
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); const t = setInterval(load, 60_000); return () => clearInterval(t); }, [load]);

  if (loading) return (
    <div style={{ padding: "8px", color: "#4B5563", fontSize: "10px" }}>Loading…</div>
  );

  if (warnings.length === 0) return (
    <div style={{
      flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
      flexDirection: "column", gap: "4px", padding: "12px",
      color: "#4B5563", fontSize: "10px",
    }}>
      <span style={{ fontSize: "16px" }}>✓</span>
      <span>No active warnings</span>
    </div>
  );

  return (
    <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>
      {warnings.map(w => (
        <div
          key={w.id}
          onClick={() => onTagClick(w.tag_id, w.tag_id)}
          title={`Click to view predictive trend for ${w.tag_id}`}
          style={{
            padding: "5px 8px",
            borderBottom: "1px solid rgba(55,65,81,0.6)",
            borderLeft: `3px solid ${LEVEL_COLOR[w.warning_level] ?? "#374151"}`,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            backgroundColor: w.is_acknowledged ? "transparent" : "rgba(0,0,0,0.2)",
            transition: "background-color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.backgroundColor = "rgba(59,130,246,0.1)")}
          onMouseLeave={e => (e.currentTarget.style.backgroundColor = w.is_acknowledged ? "transparent" : "rgba(0,0,0,0.2)")}
        >
          {/* Level badge */}
          <span style={{
            flexShrink: 0,
            width: "14px", height: "14px",
            display: "flex", alignItems: "center", justifyContent: "center",
            backgroundColor: LEVEL_COLOR[w.warning_level] ?? "#374151",
            color: "#000",
            fontWeight: 700,
            fontSize: "8px",
            borderRadius: "3px",
          }}>
            {LEVEL_LABEL[w.warning_level] ?? "?"}
          </span>

          {/* Tag ID */}
          <span style={{
            flexShrink: 0,
            fontSize: "9px",
            color: "#9CA3AF",
            maxWidth: "90px",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}>
            {w.tag_id.split(".").pop() ?? w.tag_id}
          </span>

          {/* Message (truncated) */}
          <span style={{
            flex: 1,
            fontSize: "9px",
            color: w.is_acknowledged ? "#4B5563" : "#D1D5DB",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}>
            {w.message}
          </span>

          {/* Time + chart icon */}
          <span style={{ flexShrink: 0, fontSize: "9px", color: "#4B5563" }}>{fmtTime(w.time)}</span>
          <span style={{ flexShrink: 0, fontSize: "11px" }}>📈</span>
        </div>
      ))}
    </div>
  );
}
