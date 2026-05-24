/**
 * LiveTrendChart
 * ==============
 * Fetches the last 2 hours of tag data from /api/bi/trends
 * and renders a Recharts multi-line chart.
 * Auto-refreshes every 60 seconds.
 */
import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/auth-context";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const API = "http://localhost:6001";

// Colours for up to 8 lines
const COLOURS = ["#60A5FA","#34D399","#FBBF24","#F87171","#A78BFA","#F472B6","#38BDF8","#4ADE80"];

// Tags to show — top actively logging tags from the DB
const TREND_TAGS = [
  "Triangle Waves.Int1",
  "Random.Real8",
  "Random.UInt4",
  "Triangle Waves.Real8",
  "Random.Int4",
];

interface TrendPoint { time: string; [tag: string]: number | string }

function fmtTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

export default function LiveTrendChart() {
  const { token } = useAuth();
  const [data, setData]       = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchTrends = useCallback(async () => {
    const end   = new Date();
    const start = new Date(end.getTime() - 2 * 3600 * 1000);   // last 2 hours

    try {
      const res = await fetch(`${API}/api/bi/trends`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          tag_ids:          TREND_TAGS,
          start:            start.toISOString(),
          end:              end.toISOString(),
          resample_minutes: 1,
        }),
      });
      const json = await res.json();
      if (!json.success) { setError(json.error ?? "Failed"); return; }

      // json.data is [{Timestamp, tag1, tag2,...}]
      const rows: TrendPoint[] = (json.data ?? []).map((r: Record<string, unknown>) => ({
        ...r,
        time: fmtTime(String(r["Timestamp"] ?? "")),
      }));
      setData(rows);
      setError(null);
      setLastRefresh(new Date());
    } catch (e: unknown) {
      setError((e as Error).message ?? "Network error");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchTrends();
    const t = setInterval(fetchTrends, 60_000);
    return () => clearInterval(t);
  }, [fetchTrends]);

  const activeTags = TREND_TAGS.filter(t => data.some(r => r[t] !== undefined && r[t] !== null));

  return (
    <div className="p-4 bg-gray-900 border border-gray-700 rounded-lg">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Live Historian Trends — Last 2 Hours
          </h3>
          {lastRefresh && (
            <p className="text-xs text-gray-500 mt-0.5">
              Updated: {lastRefresh.toLocaleTimeString()}
            </p>
          )}
        </div>
        <button
          onClick={fetchTrends}
          className="px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 rounded text-gray-400 transition"
        >
          ↻ Refresh
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
          Loading trend data…
        </div>
      )}

      {error && !loading && (
        <div className="p-3 bg-red-900/30 border border-red-700 rounded text-red-300 text-xs">
          ⚠ {error}
        </div>
      )}

      {!loading && !error && data.length === 0 && (
        <div className="flex items-center justify-center h-48 text-gray-600 text-sm">
          No data in the last 2 hours
        </div>
      )}

      {!loading && data.length > 0 && (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey="time"
              tick={{ fill: "#9CA3AF", fontSize: 10 }}
              interval={Math.floor(data.length / 8)}
            />
            <YAxis tick={{ fill: "#9CA3AF", fontSize: 10 }} width={48} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #374151", fontSize: 11 }}
              labelStyle={{ color: "#D1D5DB" }}
              itemStyle={{ color: "#9CA3AF" }}
            />
            <Legend
              wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
              formatter={(v) => <span style={{ color: "#D1D5DB" }}>{v}</span>}
            />
            {activeTags.map((tag, i) => (
              <Line
                key={tag}
                type="monotone"
                dataKey={tag}
                stroke={COLOURS[i % COLOURS.length]}
                dot={false}
                strokeWidth={1.5}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
