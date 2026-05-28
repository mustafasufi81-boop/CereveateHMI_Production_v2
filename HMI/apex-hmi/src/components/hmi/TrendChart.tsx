import { useState, useEffect, useCallback, useRef } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts";
import { cn } from "@/lib/utils";
import { NoDataMessage } from "./NoDataMessage";

// ISA-101 tag colors
const TAG_COLORS = [
  '#00FF00', '#00FFFF', '#FF00FF', '#FFFF00',
  '#FF8800', '#FF4444', '#4488FF', '#AA44FF',
];

const FORECAST_COLOR   = '#F59E0B';  // amber — clearly "prediction, not history"
const FORECAST_KEY     = '__forecast__';
const FORECAST_REFRESH = 60_000;     // re-fetch forecast every 60 s

/** Map of tagId → array of {time, value} points (live MQTT buffer) */
export interface LiveTrendData {
  points: Record<string, { time: string; value: number }[]>;
  tagLabels?: Record<string, string>;
}

interface TrendChartProps {
  title: string;
  tagIds?: string[];        // For historical API mode
  liveData?: LiveTrendData; // Pre-built MQTT buffer — bypasses API when provided
  mode?: 'live' | 'historical';
  equipmentId?: string;
  /** Show a dashed seasonal_fft forecast line continuing from the last data point.
   *  Automatically enabled when exactly one tagId is provided. */
  showForecast?: boolean;
  /** How many minutes ahead to forecast (default 30) */
  forecastHorizon?: number;
}

interface TrendDataPoint {
  time: string;
  /** epoch ms — used to sort and merge historical + forecast on a shared axis */
  _ts: number;
  [key: string]: any;
}

const timeRanges = [
  { label: "1h", hours: 1 },
  { label: "4h", hours: 4 },
  { label: "8h", hours: 8 },
  { label: "24h", hours: 24 }
];

function fmtTime(d: Date) {
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export const TrendChart = ({
  title, tagIds, liveData, mode = 'historical', equipmentId,
  showForecast, forecastHorizon = 30,
}: TrendChartProps) => {
  const [selectedRange, setSelectedRange] = useState(8);
  const [historicalData, setHistoricalData] = useState<TrendDataPoint[]>([]);
  const [forecastPoints, setForecastPoints] = useState<TrendDataPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [forecastModel, setForecastModel] = useState<string>('');
  const [forecastLoading, setForecastLoading] = useState(false);
  const forecastTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Decide whether forecast is active: explicit prop OR auto when single-tag historical
  const forecastActive = showForecast ?? (mode === 'historical' && tagIds?.length === 1);
  const forecastTagId  = forecastActive && tagIds?.length === 1 ? tagIds[0] : null;

  // ── LIVE MODE: render MQTT buffer directly ─────────────────────────────────
  useEffect(() => {
    if (mode !== 'live' || !liveData) return;
    if (!liveData.points || Object.keys(liveData.points).length === 0) {
      setHistoricalData([]);
      return;
    }
    const timeMap: Record<string, TrendDataPoint> = {};
    Object.entries(liveData.points).forEach(([tagId, pts]) => {
      pts.forEach((pt) => {
        const ts = new Date(pt.time).getTime();
        const key = pt.time;
        if (!timeMap[key]) timeMap[key] = { time: pt.time, _ts: ts };
        timeMap[key][tagId] = pt.value;
      });
    });
    setHistoricalData(Object.values(timeMap).sort((a, b) => a._ts - b._ts));
  }, [liveData, mode]);

  // ── HISTORICAL MODE: fetch from API ───────────────────────────────────────
  useEffect(() => {
    if (mode === 'live') return;
    const fetchData = async () => {
      if (!tagIds || tagIds.length === 0) { setHistoricalData([]); return; }
      setLoading(true);
      try {
        const endTime   = new Date();
        const startTime = new Date(endTime.getTime() - selectedRange * 3_600_000);
        const token     = localStorage.getItem('auth_token') || localStorage.getItem('token');

        const response = await fetch('/api/historical/multiple', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ tagIds, startTime: startTime.toISOString(), endTime: endTime.toISOString(), maxPoints: 1000 }),
        });
        if (!response.ok) throw new Error('Failed to fetch trend data');

        const result = await response.json();
        const timeMap: Record<string, TrendDataPoint> = {};
        if (result.trends) {
          Object.entries(result.trends).forEach(([tagId, points]: [string, any]) => {
            if (!Array.isArray(points)) return;
            points.forEach((point: any) => {
              const d   = new Date(point.timestamp || point.time);
              const key = d.toISOString();
              if (!timeMap[key]) timeMap[key] = { time: fmtTime(d), _ts: d.getTime() };
              timeMap[key][tagId] = typeof point.value_num !== 'undefined' ? point.value_num : (point.value ?? 0);
            });
          });
        }
        setHistoricalData(Object.values(timeMap).sort((a, b) => a._ts - b._ts));
      } catch (error) {
        console.error('[TrendChart] Error fetching trend data:', error);
        setHistoricalData([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [selectedRange, tagIds, mode]);

  // ── FORECAST: fetch multi-model projection from /api/bi/forecast ─────────
  const fetchForecast = useCallback(async () => {
    if (!forecastTagId) return;
    setForecastLoading(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const end   = new Date();
      const start = new Date(end.getTime() - 2 * 3_600_000); // 2 h of training history

      const res = await fetch('http://localhost:6001/api/bi/forecast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          tag_id:            forecastTagId,
          start:             start.toISOString(),
          end:               end.toISOString(),
          steps:             forecastHorizon,
          resample_minutes:  1,
        }),
      });
      if (!res.ok) return;
      const json = await res.json();
      if (!json.success) return;

      const bestModel: string     = json.best_model ?? '';
      const timestamps: string[]  = json.timestamps ?? [];
      const modelData             = json.models?.[bestModel];
      const points: number[]      = modelData?.points ?? [];

      if (points.length === 0 || timestamps.length === 0) return;
      setForecastModel(bestModel);

      // Build forecast data points — each entry has FORECAST_KEY + a _ts for sort/merge
      const pts: TrendDataPoint[] = timestamps.map((isoStr: string, i: number) => {
        const d = new Date(isoStr);
        return {
          time:           fmtTime(d),
          _ts:            d.getTime(),
          [FORECAST_KEY]: typeof points[i] === 'number' ? points[i] : null,
        };
      });
      setForecastPoints(pts);
    } catch {
      // Silently degrade — chart still shows without forecast line
    } finally {
      setForecastLoading(false);
    }
  }, [forecastTagId, forecastHorizon]);

  // Fetch on mount + when tag/range changes + refresh every 60 s
  useEffect(() => {
    if (!forecastActive) { setForecastPoints([]); return; }
    fetchForecast();
    forecastTimerRef.current = setInterval(fetchForecast, FORECAST_REFRESH);
    return () => { if (forecastTimerRef.current) clearInterval(forecastTimerRef.current); };
  }, [forecastActive, fetchForecast, selectedRange]);

  // ── Merge historical + forecast onto a single time axis ───────────────────
  //
  // DESIGN: the two Recharts <Line> components share exactly ONE junction point —
  // the last historical data row.  We inject FORECAST_KEY into that row using
  // points[0] from the API (which _shape_forecast guarantees ≈ y[-1]).
  // This means:
  //   • Solid line  ends   at junction (last DB row)          — real data only
  //   • Dashed line starts at junction, continues into future  — model only
  //   • No phantom extension of the solid line into future timestamps
  //   • No floating disconnected forecast line
  //
  const data: TrendDataPoint[] = (() => {
    if (historicalData.length === 0) return [...forecastPoints];

    // Inject the model's anchor value into the last historical point so the
    // dashed forecast line visually starts exactly where the solid line ends.
    const anchorForecastVal = forecastPoints.length > 0
      ? forecastPoints[0][FORECAST_KEY]
      : undefined;

    const merged: TrendDataPoint[] = historicalData.map((pt, i) => {
      if (i === historicalData.length - 1 && anchorForecastVal !== undefined) {
        return { ...pt, [FORECAST_KEY]: anchorForecastVal };
      }
      return pt;
    });

    // Append the pure forecast points (they have NO tagId key — solid line doesn't extend)
    merged.push(...forecastPoints);
    return merged;
  })();

  // Determine active tag list for rendering lines
  const activeTags = mode === 'live' && liveData
    ? Object.keys(liveData.points)
    : (tagIds || []);

  const getLabel = (tagId: string) => liveData?.tagLabels?.[tagId] || tagId;

  // "NOW" marker = the last historical point (= junction between solid and dashed lines)
  const nowTs = historicalData.length > 0 ? historicalData[historicalData.length - 1]?.time : null;

  return (
    <div className="bg-slate-950/60 rounded-lg p-4 border border-primary/20">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">{title}</h3>
        <div className="flex items-center gap-3">
          {/* Forecast badge */}
          {forecastActive && forecastPoints.length > 0 && (
            <span
              title={`Forecast model: ${forecastModel.toUpperCase()}`}
              style={{
                color: FORECAST_COLOR,
                borderColor: `${FORECAST_COLOR}60`,
                backgroundColor: `${FORECAST_COLOR}15`,
                fontSize: 10,
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: 4,
                border: '1px solid',
              }}>
              🔮 {forecastModel.toUpperCase()} +{forecastHorizon}min
              {forecastLoading && ' …'}
            </span>
          )}
          {mode === 'live' ? (
            <span className="flex items-center gap-1.5 px-3 py-1 text-xs font-bold rounded-full border border-green-500/50 bg-green-500/10 text-green-400">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
              LIVE • UPDATE: 1s
            </span>
          ) : (
            <div className="flex gap-2">
              {timeRanges.map((range) => (
                <button
                  key={range.hours}
                  onClick={() => setSelectedRange(range.hours)}
                  className={cn(
                    "px-4 py-1.5 text-xs font-bold rounded-md transition-all duration-200 border",
                    selectedRange === range.hours
                      ? "bg-primary text-white border-primary shadow-lg shadow-primary/50"
                      : "bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700 hover:border-primary/50"
                  )}
                >
                  {range.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Active tags color legend */}
      {activeTags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {activeTags.map((tagId, idx) => (
            <span key={tagId} className="px-2 py-0.5 text-xs font-mono rounded-sm border"
              style={{
                color: TAG_COLORS[idx % TAG_COLORS.length],
                borderColor: `${TAG_COLORS[idx % TAG_COLORS.length]}50`,
                backgroundColor: `${TAG_COLORS[idx % TAG_COLORS.length]}15`,
              }}>
              {getLabel(tagId)}
            </span>
          ))}
          {forecastActive && forecastPoints.length > 0 && (
            <span className="px-2 py-0.5 text-xs font-mono rounded-sm border"
              style={{ color: FORECAST_COLOR, borderColor: `${FORECAST_COLOR}50`, backgroundColor: `${FORECAST_COLOR}15` }}>
              ── forecast
            </span>
          )}
        </div>
      )}

      <div className="h-72 bg-slate-900/40 rounded-lg p-3 border border-primary/10">
        {loading ? (
          <NoDataMessage type="loading" height="h-full" />
        ) : data.length === 0 ? (
          <NoDataMessage type="no-data" height="h-full"
            subtitle={
              mode === 'live'
                ? "Waiting for MQTT data... Select tags from the Asset Browser on the left."
                : "No data found for selected time range."
            }
          />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.3)" vertical={false} />
              <XAxis dataKey="time" stroke="rgba(148,163,184,0.8)" fontSize={10}
                tickLine={false} axisLine={{ stroke: "rgba(100,116,139,0.5)" }}
                interval="preserveStartEnd" tick={{ fill: "rgba(148,163,184,0.9)" }} />
              <YAxis stroke="rgba(148,163,184,0.5)" fontSize={10}
                tickLine={false} axisLine={false}
                tick={{ fill: "rgba(148,163,184,0.8)" }} width={50} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "rgb(15,23,42)", border: "1px solid rgba(59,130,246,0.5)",
                  borderRadius: "8px", fontSize: "12px", padding: "8px 12px",
                  boxShadow: "0 4px 6px rgba(0,0,0,0.3)",
                }}
                labelStyle={{ color: "rgb(226,232,240)", fontWeight: "bold" }}
                itemStyle={{ color: "rgb(203,213,225)" }}
                formatter={(value: any, name: string) =>
                  name === FORECAST_KEY
                    ? [`${typeof value === 'number' ? value.toFixed(2) : value}`, '🔮 Forecast']
                    : [typeof value === 'number' ? value.toFixed(2) : value, getLabel(name)]
                }
              />
              <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }}
                formatter={(value) =>
                  value === FORECAST_KEY
                    ? <span style={{ color: FORECAST_COLOR, fontFamily: 'monospace', fontSize: 11 }}>
                        🔮 forecast ({forecastModel})
                      </span>
                    : <span className="text-slate-300 font-mono text-xs">{getLabel(value)}</span>
                }
              />

              {/* Vertical "NOW" marker at the history/forecast boundary */}
              {nowTs && forecastPoints.length > 0 && (
                <ReferenceLine x={nowTs} stroke="rgba(245,158,11,0.4)"
                  strokeDasharray="4 4"
                  label={{ value: 'NOW', position: 'insideTopLeft', fill: '#F59E0B', fontSize: 9 }}
                />
              )}

              {/* Historical lines — solid */}
              {activeTags.map((tagId, idx) => (
                <Line key={tagId} type="monotone" dataKey={tagId} name={tagId}
                  stroke={TAG_COLORS[idx % TAG_COLORS.length]} strokeWidth={2}
                  dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "white" }}
                  connectNulls={false} />
              ))}

              {/* Forecast line — dashed amber */}
              {forecastActive && forecastPoints.length > 0 && (
                <Line key={FORECAST_KEY} type="monotone" dataKey={FORECAST_KEY}
                  name={FORECAST_KEY} stroke={FORECAST_COLOR} strokeWidth={2}
                  strokeDasharray="6 4" dot={false}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: FORECAST_COLOR }}
                  connectNulls={true} />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};
