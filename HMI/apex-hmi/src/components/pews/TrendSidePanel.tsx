/**
 * TrendSidePanel
 * ==============
 * Narrow right-hand sidebar on the PEWS tab.
 * Shows a live sparkline card per tag from the historian.
 *
 * Each card has:
 *   • Tag name + current value
 *   • Mini sparkline (last 30 min)
 *   • 🔔 bell icon — opens a full-screen trend modal with 2-hour Recharts trend
 *
 * Auto-refreshes every 60 s. Modal can be closed by clicking outside or ✕.
 */
import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "@/context/auth-context";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";

const API = "http://localhost:6001";

const SPARKLINE_TAGS = [
  { id: "Triangle Waves.Int1",  label: "TW Int1",   color: "#60A5FA" },
  { id: "Triangle Waves.Real8", label: "TW Real8",  color: "#34D399" },
  { id: "Random.Real8",         label: "Rand R8",   color: "#FBBF24" },
  { id: "Random.UInt4",         label: "Rand U4",   color: "#F87171" },
  { id: "Random.Int4",          label: "Rand I4",   color: "#A78BFA" },
  { id: "Triangle Waves.Int2",  label: "TW Int2",   color: "#F472B6" },
];

interface Point { time: string; value: number | null }
type SparkMap = Record<string, Point[]>;

function fmt(t: string) {
  try { return new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return t; }
}

// ── Sparkline card ────────────────────────────────────────────────────────────
function SparkCard({
  tagId, label, color, points, onOpen,
}: {
  tagId: string; label: string; color: string;
  points: Point[]; onOpen: () => void;
}) {
  const last = [...points].reverse().find(p => p.value !== null);
  const currentVal = last?.value;

  // Trend direction
  const prev = points.slice(-10).filter(p => p.value !== null);
  const trend = prev.length >= 2
    ? (prev[prev.length - 1].value! > prev[0].value! ? "▲" : "▼")
    : "–";
  const trendColor = trend === "▲" ? "#34D399" : trend === "▼" ? "#F87171" : "#9CA3AF";

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-2 flex flex-col gap-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-gray-300 truncate" style={{ maxWidth: 90 }}>{label}</span>
        <button
          onClick={onOpen}
          title="Open full trend"
          className="text-base hover:scale-125 transition-transform"
        >
          🔔
        </button>
      </div>

      {/* Current value */}
      <div className="flex items-center gap-1">
        <span className="text-sm font-mono text-white">
          {currentVal !== undefined && currentVal !== null ? currentVal.toFixed(1) : "—"}
        </span>
        <span style={{ color: trendColor }} className="text-xs font-bold">{trend}</span>
      </div>

      {/* Mini sparkline */}
      {points.length > 2 ? (
        <ResponsiveContainer width="100%" height={40}>
          <LineChart data={points} margin={{ top: 2, right: 2, left: 0, bottom: 2 }}>
            <Line type="monotone" dataKey="value" stroke={color} dot={false}
              strokeWidth={1.5} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="h-10 flex items-center justify-center text-gray-600 text-xs">no data</div>
      )}
    </div>
  );
}

// ── Full trend modal ──────────────────────────────────────────────────────────
function TrendModal({
  tagId, label, color, points, onClose,
}: {
  tagId: string; label: string; color: string;
  points: Point[]; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  // Stats
  const vals = points.map(p => p.value).filter(v => v !== null) as number[];
  const mean = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
  const max  = vals.length ? Math.max(...vals) : 0;
  const min  = vals.length ? Math.min(...vals) : 0;
  const std  = vals.length
    ? Math.sqrt(vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length)
    : 0;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center">
      <div ref={ref} className="w-11/12 max-w-3xl bg-gray-950 border border-gray-600 rounded-xl shadow-2xl p-6">
        {/* Modal header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-white">{label}</h2>
            <p className="text-xs text-gray-400 font-mono">{tagId} — Last 2 hours</p>
          </div>
          <button onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none">✕</button>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-3 mb-4">
          {[
            { label: "Current", value: vals[vals.length - 1]?.toFixed(2) ?? "—" },
            { label: "Mean",    value: mean.toFixed(2) },
            { label: "Max",     value: max.toFixed(2) },
            { label: "Std Dev", value: std.toFixed(3) },
          ].map(s => (
            <div key={s.label} className="bg-gray-900 rounded-lg p-3 text-center">
              <div className="text-xs text-gray-400 mb-1">{s.label}</div>
              <div className="text-base font-mono font-bold text-white">{s.value}</div>
            </div>
          ))}
        </div>

        {/* Full chart */}
        {points.length > 2 ? (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="time" tick={{ fill: "#9CA3AF", fontSize: 10 }}
                interval={Math.floor(points.length / 8)} />
              <YAxis tick={{ fill: "#9CA3AF", fontSize: 10 }} width={52} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #374151", fontSize: 11 }}
                labelStyle={{ color: "#D1D5DB" }}
              />
              <Line type="monotone" dataKey="value" stroke={color}
                dot={false} strokeWidth={2} connectNulls name={label} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-64 flex items-center justify-center text-gray-500">No trend data</div>
        )}

        <p className="text-xs text-gray-600 mt-3 text-center">
          Click outside to close • Data from historian_raw.historian_timeseries
        </p>
      </div>
    </div>
  );
}

// ── Main sidebar ──────────────────────────────────────────────────────────────
export default function TrendSidePanel() {
  const { token } = useAuth();
  const [sparkData, setSparkData] = useState<SparkMap>({});
  const [openModal, setOpenModal]  = useState<string | null>(null);
  const [loading, setLoading]     = useState(true);

  const fetchSparks = useCallback(async () => {
    const end   = new Date();
    const start = new Date(end.getTime() - 2 * 3600 * 1000);

    try {
      const res = await fetch(`${API}/api/bi/trends`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          tag_ids:          SPARKLINE_TAGS.map(t => t.id),
          start:            start.toISOString(),
          end:              end.toISOString(),
          resample_minutes: 2,
        }),
      });
      const json = await res.json();
      if (!json.success) return;

      const map: SparkMap = {};
      SPARKLINE_TAGS.forEach(t => { map[t.id] = []; });

      (json.data as Record<string, unknown>[]).forEach(row => {
        const time = fmt(String(row["Timestamp"] ?? ""));
        SPARKLINE_TAGS.forEach(t => {
          const v = row[t.id];
          map[t.id].push({ time, value: v !== undefined && v !== null ? Number(v) : null });
        });
      });
      setSparkData(map);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    fetchSparks();
    const timer = setInterval(fetchSparks, 60_000);
    return () => clearInterval(timer);
  }, [fetchSparks]);

  const openTag = SPARKLINE_TAGS.find(t => t.id === openModal);

  return (
    <>
      {/* Sidebar */}
      <div className="w-44 shrink-0 border-l border-gray-700 bg-gray-950 p-2 overflow-y-auto flex flex-col gap-2">
        <div className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-1 px-1">
          Live Trends
        </div>
        {loading ? (
          <div className="text-xs text-gray-600 text-center mt-4">Loading…</div>
        ) : (
          SPARKLINE_TAGS.map(tag => (
            <SparkCard
              key={tag.id}
              tagId={tag.id}
              label={tag.label}
              color={tag.color}
              points={sparkData[tag.id] ?? []}
              onOpen={() => setOpenModal(tag.id)}
            />
          ))
        )}
      </div>

      {/* Modal */}
      {openModal && openTag && (
        <TrendModal
          tagId={openTag.id}
          label={openTag.label}
          color={openTag.color}
          points={sparkData[openTag.id] ?? []}
          onClose={() => setOpenModal(null)}
        />
      )}
    </>
  );
}
