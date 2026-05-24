/**
 * PredictiveTrendModal
 * ====================
 * Multi-model forecast modal — all math runs in Python (Flask /api/bi/forecast).
 * Models: LR (numpy polyfit) | HW (statsmodels) | FFT (numpy.fft) | ARIMA (statsmodels)
 * React just fetches results and renders Recharts lines.
 */
import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "@/context/auth-context";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";

const API = "http://localhost:6001";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TrendPoint {
  time: string;
  actual?: number | null;
  // Forecast lines — filled only in the future window
  futureLR?:    number | null;
  futureETS?:   number | null;
  futureHW?:    number | null;
  futureFFT?:   number | null;
  futureARIMA?: number | null;
  // Confidence bands (HW / ARIMA only)
  confLow?:  number | null;
  confHigh?: number | null;
  _rawTime?: string;
}

interface ForecastModel {
  points:     number[] | string | null;
  conf_low?:  number[] | string | null;
  conf_high?: number[] | string | null;
  mae:        number | null;
  rmse:       number | null;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "N/A";
  status:     string;
  error?:     string;
  skipped?:   boolean;
  period_detected?: number;
  order?:     number[] | string;
}

// Helper to parse space-separated string or array into number[]
function parsePts(v: number[] | string | null | undefined): number[] {
  if (!v) return [];
  if (Array.isArray(v)) return v as number[];
  return (v as string).trim().split(/\s+/).map(Number).filter(isFinite);
}

interface ForecastResponse {
  success:           boolean;
  n_history:         number;
  n_train_points:    number;
  n_days_trained:    number;
  used_long_history: boolean;
  hold_n:            number;
  step_minutes:      number;
  best_model:        string;
  timestamps:        string[];
  models: Record<string, ForecastModel>;
}

interface BaselineStat {
  mean: number;
  std: number;
  min: number;
  max: number;
  p25: number;
  p50: number;
  p75: number;
  count: number;
}

interface Warning {
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
  is_acknowledged?: boolean;
}

interface PredictiveAlarm {
  id: number;
  tag_id: string;
  direction: "HIGH" | "LOW";
  confidence: string;
  predicted_value: number;
  limit_value: number;
  eta_minutes: number;
  predicted_breach_at: string;
  model_used: string;
  raised_at: string;
  active: boolean;
  acknowledged: boolean;
}

interface Props {
  tagId: string;
  tagName: string;
  onClose: () => void;
}

// Permanent record of one resolved forecast point (actual arrived at a forecast slot)
interface AccuracyRecord {
  ts:       string;                        // ISO timestamp (display key)
  actual:   number;
  forecasts: Partial<Record<ModelKey, number>>; // model → predicted value
  errors:    Partial<Record<ModelKey, number>>; // model → absolute % error
}

// Per-second live divergence record: one entry per second as actuals arrive at forecast slots
interface SecondRecord {
  ts:      string;
  actual:  number;
  fcVals:  Partial<Record<ModelKey, number>>;   // interpolated forecast at this second
  errAbs:  Partial<Record<ModelKey, number>>;   // |actual - forecast|
  errPct:  Partial<Record<ModelKey, number>>;   // % divergence
}

// Walk-forward CV benchmark result row
interface BenchmarkEntry {
  rank:         number;
  model:        string;
  mae:          number | null;
  rmse:         number | null;
  mape:         number | null;
  r2:           number | null;
  ci_coverage:  number | null;
  folds_run:    number;
  tuned_params: Record<string, unknown>;
  confidence:   string;
  verdict:      string;
}
interface BenchmarkResult {
  n_points:     number;
  signal_type:  string;
  folds:        number;
  forecast_steps: number;
  leaderboard:  BenchmarkEntry[];
  best_model:   string;
  best_params:  Record<string, unknown>;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
  catch { return iso; }
}

function fmtNum(v: number | null | undefined, d = 2) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return v.toFixed(d);
}

/**
 * Linearly interpolate the frozen forecast to any arbitrary second-level epoch.
 * Returns null if the epoch is outside the forecast window.
 */
function interpolateForecast(fc: ForecastResponse, epochMs: number, model: ModelKey): number | null {
  const pts = parsePts(fc.models[model]?.points);
  if (!pts || pts.length === 0) return null;
  const ts = fc.timestamps;
  if (!ts || ts.length === 0) return null;

  // Clamp strictly to the forecast window — do NOT extrapolate backwards.
  // If epoch < first forecast ts → return null (do NOT stamp historical actuals).
  const firstTs = new Date(ts[0]).getTime();
  const lastTs  = new Date(ts[ts.length - 1]).getTime();
  if (epochMs < firstTs || epochMs > lastTs) return null;

  let lo = -1, hi = -1;
  for (let i = 0; i < ts.length; i++) {
    const t = new Date(ts[i]).getTime();
    if (t <= epochMs) lo = i;
    if (hi === -1 && t >= epochMs) { hi = i; break; }
  }
  if (lo === -1 && hi === -1) return null;
  if (lo === -1)    return null;  // before window (already guarded above, extra safety)
  if (hi === -1 || lo === hi) return (pts[lo] as number) ?? null;
  const t0 = new Date(ts[lo]).getTime();
  const t1 = new Date(ts[hi]).getTime();
  const v0 = pts[lo] as number, v1 = pts[hi] as number;
  if (v0 === null || v0 === undefined || v1 === null || v1 === undefined) return null;
  return v0 + (v1 - v0) * ((epochMs - t0) / (t1 - t0));
}

const LEVEL_LABEL: Record<number, string> = { 1: "INFO", 2: "CAUTION", 3: "WARNING", 4: "ALERT" };
const LEVEL_COLOR: Record<number, string> = { 1: "#60A5FA", 2: "#FBBF24", 3: "#F97316", 4: "#EF4444" };

const MODEL_COLOR: Record<string, string> = {
  LR:    "#FACC15",
  HW:    "#FB923C",
  FFT:   "#22D3EE",
  ARIMA: "#A78BFA",
};
const MODEL_DASH: Record<string, string> = {
  LR:    "8 4",
  HW:    "4 2",
  FFT:   "6 2",
  ARIMA: "3 3",
};
const ALL_MODELS = ["LR", "HW", "FFT", "ARIMA"] as const;
type ModelKey = typeof ALL_MODELS[number];

const DATAKEY: Record<ModelKey, keyof TrendPoint> = {
  LR:    "futureLR",
  HW:    "futureHW",
  FFT:   "futureFFT",
  ARIMA: "futureARIMA",
};

// ── Component ─────────────────────────────────────────────────────────────────

export function PredictiveTrendModal({ tagId, tagName, onClose }: Props) {
  const { token } = useAuth();
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const overlayRef = useRef<HTMLDivElement>(null);

  const [trendData, setTrendData]   = useState<TrendPoint[]>([]);
  const [baseline, setBaseline]     = useState<BaselineStat | null>(null);
  const [warnings, setWarnings]         = useState<Warning[]>([]);
  const [predAlarms, setPredAlarms]     = useState<PredictiveAlarm[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);
  const [forecast, setForecast]     = useState<ForecastResponse | null>(null);
  const forecastRef                 = useRef<ForecastResponse | null>(null); // stable ref for timer closure
  // dataEndRef: use tag's last_seen if it's older than 5 min, so historical data loads correctly
  const dataEndRef                  = useRef<Date>(new Date());
  const [dataEndReady, setDataEndReady] = useState(false);
  // Permanent accuracy log — accumulates as actuals arrive at forecast slots.
  // useRef so it NEVER resets on re-render; logTick forces a UI refresh.
  const accuracyLogRef              = useRef<AccuracyRecord[]>([]);
  const resolvedKeysRef             = useRef<Set<string>>(new Set()); // prevent double-logging same ts
  const [logTick, setLogTick]       = useState(0);
  const [vis, setVis]               = useState<Record<ModelKey, boolean>>({ LR: true, HW: true, FFT: true, ARIMA: true });
  const toggleModel = (m: ModelKey) => setVis(p => ({ ...p, [m]: !p[m] }));
  // live clock for header (shows seconds clearly)
  const [nowClock, setNowClock] = useState<Date>(new Date());
  useEffect(() => {
    const t = setInterval(() => setNowClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  // 2h resampled history — set once on load(), merged with live raw edge each second
  const historicalBaseRef = useRef<TrendPoint[]>([]);

  // ── Per-second live divergence tracking ───────────────────────────────────
  // liveErrRef: grows by one entry per new raw-second actual that overlaps the forecast.
  // cumErrRef:  running absolute error per model ("loss" accumulator).
  // trackedSecsRef: prevents double-logging the same second key.
  const liveErrRef        = useRef<SecondRecord[]>([]);
  const trackedSecsRef    = useRef<Set<string>>(new Set());
  const cumErrRef         = useRef<Partial<Record<ModelKey, number>>>({});
  const [errTick, setErrTick] = useState(0);

  // ── Resolve actual data end time from /api/bi/tags ────────────────────────
  useEffect(() => {
    dataEndRef.current = new Date(); // reset on tag change
    setDataEndReady(false);
    // Reset divergence state for the new tag
    liveErrRef.current     = [];
    trackedSecsRef.current = new Set();
    cumErrRef.current      = {};
    fetch(`${API}/api/bi/tags`, { headers })
      .then(r => r.json())
      .then(d => {
        const list: { tag_id: string; last_seen: string }[] = Array.isArray(d) ? d : (d.tags ?? d.data ?? []);
        const meta = list.find(t => t.tag_id === tagId);
        if (meta?.last_seen) {
          const lastSeen = new Date(meta.last_seen);
          const ageMs = Date.now() - lastSeen.getTime();
          // If data is older than 5 minutes, use last_seen as the window end
          if (ageMs > 5 * 60 * 1000) dataEndRef.current = lastSeen;
        }
      })
      .catch(() => { /* keep current time */ })
      .finally(() => setDataEndReady(true));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tagId, token]);

  // ── Forecast is COMPLETELY DECOUPLED from actuals.
  //    It is fetched exactly once on mount, stored in forecastRef forever,
  //    and only regenerated when the 30-min horizon expires.
  //    Nothing else ever clears or re-fetches it.
  const forecastFetchingRef = useRef(false); // guard against double-fetch

  const doFetchForecast = useCallback(async () => {
    if (forecastFetchingRef.current) return;
    forecastFetchingRef.current = true;
    // Always use NOW as the end so refreshes slide the training window forward
    // and the forecast re-anchors to the latest actual value.
    // Use 6h window to ensure enough samples even for slow/deadbanded tags.
    const end   = new Date();
    const start = new Date(end.getTime() - 6 * 3600 * 1000);
    try {
      const fRes = await fetch(`${API}/api/bi/forecast`, {
        method: "POST", headers,
        body: JSON.stringify({ tag_id: tagId, start: start.toISOString(), end: end.toISOString(), steps: 30, resample_minutes: 1 }),
      });
      const fData = await fRes.json();
      if (fData.success) {
        forecastRef.current = fData as ForecastResponse;
        setForecast(fData as ForecastResponse);
      }
    } catch { /* keep old forecast */ }
    finally { forecastFetchingRef.current = false; }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tagId, token]);

  // Fetch forecast on mount + auto-refresh every 5 min so the forecast
  // re-anchors to the current live value and the horizon stays current.
  // Gate on dataEndReady so we have the correct time window before fetching.
  useEffect(() => {
    if (!dataEndReady) return;
    forecastRef.current = null;
    setForecast(null);
    doFetchForecast();
    const refreshTimer = setInterval(() => {
      forecastFetchingRef.current = false; // allow re-fetch
      doFetchForecast();
    }, 5 * 60 * 1000); // every 5 minutes
    return () => clearInterval(refreshTimer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tagId, token, dataEndReady]);

  // ── load() only handles actuals / baseline / warnings — NO forecast ──────
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    const end   = new Date(dataEndRef.current);
    const start = new Date(end.getTime() - 2 * 3600 * 1000);

    try {
      const [tSettled, bSettled, wSettled, paSettled] = await Promise.allSettled([
        fetch(`${API}/api/bi/trends`, {
          method: "POST", headers,
          body: JSON.stringify({ tag_ids: [tagId], start: start.toISOString(), end: end.toISOString(), resample_minutes: 1 }),
        }),
        fetch(`${API}/api/bi/baselines`, {
          method: "POST", headers,
          body: JSON.stringify({ tag_ids: [tagId], start: start.toISOString(), end: end.toISOString() }),
        }),
        fetch(`${API}/api/pews/warnings?tag_id=${encodeURIComponent(tagId)}`, { headers }),
        fetch(`${API}/api/predictive/alarms?tag_id=${encodeURIComponent(tagId)}&active=true`, { headers }),
      ]);
      if (tSettled.status === "rejected") throw new Error("Trends fetch failed");
      const tData = await tSettled.value.json();
      const bData = bSettled.status === "fulfilled" ? await bSettled.value.json().catch(() => ({})) : {};
      const wData = wSettled.status === "fulfilled" ? await wSettled.value.json().catch(() => ({})) : {};
      const paData = paSettled.status === "fulfilled" ? await paSettled.value.json().catch(() => ({})) : {};

      // ── Historical actuals ────────────────────────────────────────────────
      const rawRows: Record<string, unknown>[] = tData.data ?? [];
      const histPoints = rawRows.map(r => ({
        time:     fmtTime(String(r["Timestamp"] ?? "")),
        actual:   typeof r[tagId] === "number" ? (r[tagId] as number) : null,
        _rawTime: String(r["Timestamp"] ?? ""),
      }));
      // Store the 2h resampled baseline so refreshActuals can merge the live edge
      // without losing historical chart context.
      historicalBaseRef.current = histPoints;
      setTrendData(histPoints);

      // ── Baseline ─────────────────────────────────────────────────────────
      if (bData.success && bData.baselines)
        setBaseline((bData.baselines as Record<string, BaselineStat>)[tagId] ?? null);

      // ── Warnings ─────────────────────────────────────────────────────────
      if (wData.success) setWarnings((wData.warnings ?? []).filter((w: Warning) => !w.is_acknowledged));
      if (paData.success) setPredAlarms((paData.data ?? []).filter((a: PredictiveAlarm) => a.active && !a.acknowledged));

    } catch (e: unknown) {
      setError((e as Error).message ?? "Load failed");
    } finally {
      setLoading(false);
    }
  }, [tagId, token]);

  // Initial actuals load on mount — gated on dataEndReady
  useEffect(() => { if (dataEndReady) load(); }, [load, dataEndReady]);

  // ── Live refresh: actuals every 1 s (cheap).
  //    Forecast regenerates ONLY when the 30-min horizon expires.
  useEffect(() => {
    let fastTimer: ReturnType<typeof setInterval>;
    let forecastTimer: ReturnType<typeof setTimeout>;

    // ---- actuals poll every 1 second ----
    const refreshActuals = async () => {
      // Strategy: 2h resampled history (from historicalBaseRef) is kept intact.
      // Every second we fetch only the last 3 min at RAW resolution and merge
      // it with the historical base. This gives:
      //   • Full 2h chart context (actual line spans the whole chart)
      //   • Per-second live edge (green line advances every second)
      const end      = new Date();
      const startRaw = new Date(end.getTime() - 3 * 60 * 1000);   // last 3 min raw
      const start2h  = new Date(end.getTime() - 2 * 3600 * 1000); // last 2h for baseline
      const cutoffMs = startRaw.getTime();
      try {
        // Use allSettled so a failed warnings/baseline fetch NEVER blocks actuals update.
        // A single slow or erroring endpoint (e.g. pews/warnings) would previously cause
        // the catch block to fire every second, freezing the chart permanently.
        const [tSettled, bSettled, wSettled, paSettled] = await Promise.allSettled([
          fetch(`${API}/api/bi/trends`, {
            method: "POST", headers,
            // resample_minutes: 0 → raw per-second rows (no resampling)
            body: JSON.stringify({ tag_ids: [tagId], start: startRaw.toISOString(), end: end.toISOString(), resample_minutes: 0 }),
          }),
          fetch(`${API}/api/bi/baselines`, {
            method: "POST", headers,
            body: JSON.stringify({ tag_ids: [tagId], start: start2h.toISOString(), end: end.toISOString() }),
          }),
          fetch(`${API}/api/pews/warnings?tag_id=${encodeURIComponent(tagId)}`, { headers }),
          fetch(`${API}/api/predictive/alarms?tag_id=${encodeURIComponent(tagId)}&active=true`, { headers }),
        ]);
        // Trends are critical — if they failed, keep existing chart and return early
        if (tSettled.status === "rejected") return;
        const tData = await tSettled.value.json();
        const bData = bSettled.status === "fulfilled" ? await bSettled.value.json().catch(() => ({})) : {};
        const wData = wSettled.status === "fulfilled" ? await wSettled.value.json().catch(() => ({})) : {};
        const paData = paSettled.status === "fulfilled" ? await paSettled.value.json().catch(() => ({})) : {};
        const rawRows: Record<string, unknown>[] = tData.data ?? [];

        // Merge: keep historical rows older than 3 min, replace newer part with raw seconds
        const olderHistory = historicalBaseRef.current.filter(p => {
          const t = p._rawTime ? new Date(p._rawTime).getTime() : NaN;
          return !isNaN(t) && t < cutoffMs;
        });
        const liveEdge = rawRows.map(r => ({
          time:     fmtTime(String(r["Timestamp"] ?? "")),
          actual:   typeof r[tagId] === "number" ? (r[tagId] as number) : null,
          _rawTime: String(r["Timestamp"] ?? ""),
        }));
        setTrendData([...olderHistory, ...liveEdge]);

        if (bData.success && bData.baselines)
          setBaseline((bData.baselines as Record<string, BaselineStat>)[tagId] ?? null);
        if (wData.success)
          setWarnings((wData.warnings ?? []).filter((w: Warning) => !w.is_acknowledged));
        if (paData.success)
          setPredAlarms((paData.data ?? []).filter((a: PredictiveAlarm) => a.active && !a.acknowledged));

        // ── Accuracy log: compare forecast vs MINUTE-AVERAGE of actuals ──────
        // Forecast = 1 value per minute. Actuals = 1 value per second.
        // Comparing forecast to a random single-second reading is meaningless.
        // Solution: group all raw rows by minute bucket, compute the mean,
        // then compare forecast[i] against that minute-mean.
        const fc = forecastRef.current;
        if (fc) {
          // Build minute-bucket → average actual map from raw rows
          const minBucketAvg = new Map<string, { sum: number; count: number }>();
          for (const row of (rawRows as Record<string, unknown>[])) {
            const v = typeof row[tagId] === "number" ? (row[tagId] as number) : null;
            if (v === null) continue;
            const epoch = new Date(String(row["Timestamp"] ?? "")).getTime();
            if (isNaN(epoch)) continue;
            const bk = String(Math.round(epoch / 60_000) * 60_000);
            const existing = minBucketAvg.get(bk);
            if (existing) { existing.sum += v; existing.count++; }
            else           minBucketAvg.set(bk, { sum: v, count: 1 });
          }

          let newEntries = 0;
          for (let i = 0; i < fc.timestamps.length; i++) {
            const slotTs    = fc.timestamps[i];
            const slotEpoch = new Date(slotTs).getTime();
            if (slotEpoch > Date.now()) continue;          // future — skip
            if (resolvedKeysRef.current.has(slotTs)) continue; // already logged

            const slotBucket = String(Math.round(slotEpoch / 60_000) * 60_000);
            const bucketData = minBucketAvg.get(slotBucket);
            if (!bucketData || bucketData.count === 0) continue; // no actuals yet

            const minuteAvg = bucketData.sum / bucketData.count;
            resolvedKeysRef.current.add(slotTs);

            const forecasts: Partial<Record<ModelKey, number>> = {};
            const errors:    Partial<Record<ModelKey, number>> = {};
            for (const m of ALL_MODELS) {
              const pts = fc.models[m]?.points;
              if (pts?.[i] !== undefined && pts[i] !== null) {
                const fv = pts[i] as number;
                forecasts[m] = fv;
                errors[m] = (Math.abs(fv - minuteAvg) / signalRange) * 100;
              }
            }
            accuracyLogRef.current = [
              { ts: slotTs, actual: minuteAvg, forecasts, errors },
              ...accuracyLogRef.current,
            ].slice(0, 200);
            newEntries++;
          }
          if (newEntries > 0) setLogTick(t => t + 1);
        }

        // ── Per-second divergence: use rawRows already fetched above (last 3 min raw)
        // Interpolate frozen forecast to each new second and record error.
        const fcSnap = forecastRef.current;
        if (fcSnap) {
          let newSecs = 0;
          for (const row of rawRows) {
            const v = typeof row[tagId] === "number" ? (row[tagId] as number) : null;
            if (v === null) continue;
            const tsStr = String(row["Timestamp"] ?? "");
            const epoch = new Date(tsStr).getTime();
            if (isNaN(epoch)) continue;
              // Round to nearest second as dedup key
              const secKey = String(Math.round(epoch / 1000) * 1000);
              if (trackedSecsRef.current.has(secKey)) continue;

              const fcVals: Partial<Record<ModelKey, number>> = {};
              const errAbs: Partial<Record<ModelKey, number>> = {};
              const errPct: Partial<Record<ModelKey, number>> = {};
              let hasAny = false;
              // Use pre-computed signalRange (chartData observed max-min) as
              // denominator so triangle/sine waves near 0 don't give 0% accuracy.
              for (const m of ALL_MODELS) {
                const fv = interpolateForecast(fcSnap, epoch, m);
                if (fv !== null) {
                  fcVals[m] = fv;
                  const ae  = Math.abs(v - fv);
                  errAbs[m] = ae;
                  errPct[m] = (ae / signalRange) * 100;
                  cumErrRef.current[m] = (cumErrRef.current[m] ?? 0) + ae;
                  hasAny = true;
                }
              }
              if (!hasAny) continue; // no forecast at this second yet
              trackedSecsRef.current.add(secKey);
              liveErrRef.current = [
                { ts: tsStr, actual: v, fcVals, errAbs, errPct },
                ...liveErrRef.current,
              ].slice(0, 300); // keep newest 300 seconds
              newSecs++;
            }
            if (newSecs > 0) setErrTick(t => t + 1);
          }
      } catch { /* keep existing */ }
    };

    // ---- forecast horizon expiry timer ----
    // Fires ONLY when real time passes the last forecast timestamp.
    // Uses forecastRef (not state) so the closure always sees the latest value.
    const scheduleHorizonCheck = () => {
      const lastTs   = forecastRef.current?.timestamps?.slice(-1)[0];
      const fireAtMs = lastTs ? new Date(lastTs).getTime() : Date.now() + 30 * 60_000;
      const delay    = Math.max(60_000, fireAtMs - Date.now()); // never fire sooner than 60 s
      forecastTimer  = setTimeout(async () => {
        await doFetchForecast();
        scheduleHorizonCheck(); // re-arm for the new horizon
      }, delay);
    };

    scheduleHorizonCheck();
    fastTimer = setInterval(refreshActuals, 1_000);
    return () => { clearInterval(fastTimer); clearTimeout(forecastTimer); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tagId, token]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ackWarning = async (id: number) => {
    try {
      await fetch(`${API}/api/pews/warnings/${id}/ack`, { method: "POST", headers });
      setWarnings(prev => prev.filter(w => w.id !== id));
    } catch { /* ignore */ }
  };

  // ── Build chart data: shared time-keyed map ──────────────────────────────
  // Actuals and forecast share the SAME x-axis (real ISO timestamps).
  // Forecast is FROZEN — not re-anchored when new actuals arrive.
  // When the actual line grows into a forecast timestamp, both values appear
  // at that point so you can visually compare prediction vs reality.
  const latestActual = [...trendData].reverse().find(d => d.actual !== null && d.actual !== undefined)?.actual ?? null;
  const deviation = baseline && latestActual !== null
    ? ((latestActual - baseline.mean) / (baseline.mean || 1)) * 100 : null;

  const chartData: TrendPoint[] = (() => {
    // SECOND-BUCKET MERGE: round every timestamp to the nearest SECOND epoch.
    // Actuals are now raw per-second data so each second gets its own chart point.
    // Forecast timestamps (minute-aligned) are also rounded to the nearest second
    // so they land on the correct x-axis position without nearest-neighbour guessing.
    const toSecBucket = (iso: string): string => {
      const t = new Date(iso).getTime();
      return isNaN(t) ? iso : String(Math.round(t / 1_000) * 1_000);
    };

    // Step 1 — index actuals by SECOND bucket (one value per second, no averaging).
    const map = new Map<string, TrendPoint>();
    for (const d of trendData) {
      const key = toSecBucket(d._rawTime ?? d.time);
      if (!map.has(key)) map.set(key, { ...d });
    }

    // Step 2 — merge frozen forecast: stamp each forecast minute onto its
    // matching second bucket (forecast ts is already minute-aligned so
    // toSecBucket gives e.g. "...000" which is correct).
    if (forecast) {
      const fc   = forecast;
      const best = fc.models[fc.best_model];

      for (let i = 0; i < fc.timestamps.length; i++) {
        const ts  = fc.timestamps[i];
        const key = toSecBucket(ts);

        const existing = map.get(key);
        const pt: TrendPoint = existing
          ? { ...existing }
          : { time: fmtTime(ts), actual: null, _rawTime: ts };

        for (const m of ALL_MODELS) {
          const mdl = fc.models[m];
          if (mdl?.points?.[i] !== undefined)
            (pt as unknown as Record<string, number | null | string>)[`future${m}`] = mdl.points[i];
        }
        const clPts = parsePts(best?.conf_low);  if (clPts[i] !== undefined) pt.confLow  = clPts[i];
        const chPts = parsePts(best?.conf_high); if (chPts[i] !== undefined) pt.confHigh = chPts[i];
        map.set(key, pt);
      }
    }

    // Step 2b — fill per-second interpolated points INSIDE the forecast window.
    // Forecast arrives as minute-aligned points (30 ticks). Without fills,
    // hovering in the forecast region jumps minute-by-minute and the tooltip
    // timestamp appears stuck. We interpolate every second between consecutive
    // forecast minute marks so cursor movement gives per-second timestamps and
    // smoothly changing predicted values.
    if (forecast) {
      const fc2 = forecast;
      const fcTs = fc2.timestamps;
      for (let i = 0; i < fcTs.length - 1; i++) {
        const t0ms = new Date(fcTs[i]).getTime();
        const t1ms = new Date(fcTs[i + 1]).getTime();
        for (let tms = t0ms + 1000; tms < t1ms; tms += 1000) {
          const key = String(tms);
          if (map.has(key)) continue; // actual already at this second — keep it
          const isoStr = new Date(tms).toISOString();
          const pt: TrendPoint = { time: fmtTime(isoStr), actual: null, _rawTime: isoStr };
          for (const m of ALL_MODELS) {
            const fv = interpolateForecast(fc2, tms, m as ModelKey);
            if (fv !== null) (pt as unknown as Record<string, unknown>)[`future${m}`] = fv;
          }
          const bm2 = fc2.models[fc2.best_model];
          if (bm2?.conf_low?.length) {
            const lv = interpolateForecast({ ...fc2, models: { ...fc2.models, [fc2.best_model]: { ...bm2, points: bm2.conf_low as number[] } } } as ForecastResponse, tms, fc2.best_model as ModelKey);
            if (lv !== null) pt.confLow = lv;
          }
          if (bm2?.conf_high?.length) {
            const hv = interpolateForecast({ ...fc2, models: { ...fc2.models, [fc2.best_model]: { ...bm2, points: bm2.conf_high as number[] } } } as ForecastResponse, tms, fc2.best_model as ModelKey);
            if (hv !== null) pt.confHigh = hv;
          }
          map.set(key, pt);
        }
      }
    }

    // Step 3 — sort by real epoch, then apply honest gap-closer.
    const sorted = Array.from(map.entries())
      .sort(([a], [b]) => {
        const ta = parseInt(a), tb = parseInt(b);
        return (isNaN(ta) ? 0 : ta) - (isNaN(tb) ? 0 : tb);
      })
      .map(([, v]) => v);

    // Find last actual value (for honest bridge)
    let lastActualVal: number | null = null;
    for (let i = sorted.length - 1; i >= 0; i--) {
      if (sorted[i].actual !== null && sorted[i].actual !== undefined) {
        lastActualVal = sorted[i].actual!;
        break;
      }
    }

    // Interpolate frozen forecast to every second point so tooltips show the
    // exact predicted value for the current second. This produces a smooth
    // visual of the frozen forecast (linear interpolation between minute ticks)
    // without recomputing the model.
    if (forecast) {
      const fc = forecast;
      for (let i = 0; i < sorted.length; i++) {
        const p = sorted[i];
        const epoch = p._rawTime ? new Date(p._rawTime).getTime() : NaN;
        if (isNaN(epoch)) continue;
        for (const m of ALL_MODELS) {
          const fv = interpolateForecast(fc, epoch, m as ModelKey);
          if (fv !== null && fv !== undefined) {
            (p as unknown as Record<string, number | null>)[`future${m}`] = fv;
          }
        }
        // Interpolate CI from best model if available
        const best = fc.models[fc.best_model];
        if (best) {
          if (best.conf_low && best.conf_low.length > 0) {
            const low = interpolateForecast({ ...fc, models: { ...fc.models, [fc.best_model]: { ...best, points: best.conf_low as any } } } as any, epoch, fc.best_model as ModelKey);
            if (low !== null) p.confLow = low;
          }
          if (best.conf_high && best.conf_high.length > 0) {
            const high = interpolateForecast({ ...fc, models: { ...fc.models, [fc.best_model]: { ...best, points: best.conf_high as any } } } as any, epoch, fc.best_model as ModelKey);
            if (high !== null) p.confHigh = high;
          }
        }
      }
    }

    // Honest minimal bridge: extend the actual line to the first forecast-only
    // point by copying the last actual value into that point's `actual` field.
    // This avoids a visible gap while preserving the frozen forecast values.
    if (lastActualVal !== null) {
      let firstFcOnlyIdx = -1;
      for (let i = 0; i < sorted.length; i++) {
        const p = sorted[i];
        const hasFc = ALL_MODELS.some(m => (p as unknown as Record<string, unknown>)[`future${m}`] != null);
        if (hasFc && (p.actual === null || p.actual === undefined)) { firstFcOnlyIdx = i; break; }
      }
      if (firstFcOnlyIdx >= 0) sorted[firstFcOnlyIdx] = { ...sorted[firstFcOnlyIdx], actual: lastActualVal };
    }

    return sorted;
  })();

  // ── Pre-compute signal range from all observed actuals in chartData ──────
  // This is used for range-normalised accuracy so near-zero crossings and
  // large-spike signals don't produce misleading 0% accuracy readings.
  // We take max(observed range, 4×std, 1) so it's always a positive number.
  const observedActuals = chartData
    .map(d => d.actual)
    .filter((v): v is number => v !== null && v !== undefined && isFinite(v));
  const obsMin = observedActuals.length ? Math.min(...observedActuals) : 0;
  const obsMax = observedActuals.length ? Math.max(...observedActuals) : 1;
  const signalRange = Math.max(
    obsMax - obsMin,
    baseline ? baseline.std * 4 : 0,
    1
  );

  // ── Smart Y-axis domain: clip outlier spikes using IQR so normal variation
  //    fills the chart instead of being squashed by a single spike.
  const yDomain: [number | string, number | string] = (() => {
    if (observedActuals.length < 4) return ["auto", "auto"];
    const sorted = [...observedActuals].sort((a, b) => a - b);
    const q1 = sorted[Math.floor(sorted.length * 0.10)];
    const q3 = sorted[Math.floor(sorted.length * 0.90)];
    const iqr = q3 - q1;
    const fence = Math.max(iqr * 2.5, signalRange * 0.5, 1);
    // Include reference lines (baseline ±2σ) in domain
    const refLow  = baseline ? baseline.mean - 2 * baseline.std : q1;
    const refHigh = baseline ? baseline.mean + 2 * baseline.std : q3;
    const lo = Math.min(q1 - fence * 0.15, refLow)  * (q1 > 0 ? 0.97 : 1.03);
    const hi = Math.max(q3 + fence * 0.15, refHigh) * (q3 > 0 ? 1.03 : 0.97);
    return [Math.floor(lo), Math.ceil(hi)];
  })();

  // evalMetrics from Python response
  const evalMetrics = forecast?.models ?? {} as Record<string, ForecastModel>;
  const bestModel   = forecast?.best_model ?? null;

  const statusColor = (s: string) =>
    s === "Best Fit"  ? "#34D399" :
    s === "Diverging" ? "#EF4444" :
    s === "Stable"    ? "#60A5FA" :
    s === "Error"     ? "#F87171" : "#6B7280";
  const confColor = (c: string) =>
    c === "HIGH" ? "#34D399" : c === "MEDIUM" ? "#FBBF24" : "#EF4444";

  // ── Custom tooltip: shows actual + all model forecasts at the same time T ──
  const ChartTooltip = ({ active, payload, label }: {
    active?: boolean;
    payload?: Array<{ dataKey: string; value: number | null; name: string; payload?: TrendPoint }>;
    label?: string;
  }) => {
    if (!active || !payload?.length) return null;
    const point = payload[0]?.payload;
    const rawTs = point?._rawTime ?? label ?? "";
    const displayTime = rawTs
      ? new Date(rawTs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
      : label ?? "";

    const actualVal   = point?.actual   ?? null;
    const forecastAt: { m: ModelKey; v: number | null; isBest: boolean }[] = ALL_MODELS.map(m => ({
      m,
      v: (point as unknown as Record<string, number | null>)?.[`future${m}`] ?? null,
      isBest: m === bestModel,
    })).filter(x => x.v !== null);

    const isInFuture  = actualVal === null || actualVal === undefined;
    // hasOverlap = actual has ARRIVED at a forecast slot — real sync point
    const hasOverlap  = actualVal !== null && forecastAt.length > 0;
    // At a sync point, guard against corrupted bridge values:
    // a forecast is only genuine if it differs from actual by any amount
    // (even 0.001). We do NOT filter them out — we show everything so
    // the user sees real divergence or true match.

    return (
      <div style={{
        backgroundColor: "#0f1117",
        border: `1px solid ${hasOverlap ? "#34D399" : isInFuture ? "#6366F1" : "#374151"}`,
        borderRadius: "6px",
        padding: "10px 14px",
        fontSize: "11px",
        fontFamily: "Consolas, monospace",
        minWidth: "200px",
        boxShadow: "0 4px 24px rgba(0,0,0,0.6)",
      }}>
        {/* timestamp */}
        <div style={{ color: "#9CA3AF", fontSize: "9px", letterSpacing: "0.8px", marginBottom: "8px", borderBottom: "1px solid #1F2937", paddingBottom: "5px" }}>
          ⏱ {displayTime}
          {isInFuture && <span style={{ marginLeft: "8px", color: "#6366F1", fontSize: "8px", padding: "1px 5px", border: "1px solid #6366F1", borderRadius: "8px" }}>FORECAST</span>}
          {hasOverlap && <span style={{ marginLeft: "8px", color: "#34D399", fontSize: "8px", padding: "1px 5px", border: "1px solid #34D399", borderRadius: "8px" }}>SYNC POINT</span>}
        </div>

        {/* actual */}
        {actualVal !== null && (
          <div style={{ display: "flex", justifyContent: "space-between", gap: "20px", marginBottom: forecastAt.length ? "6px" : 0 }}>
            <span style={{ color: "#34D399", fontWeight: 700 }}>Actual</span>
            <span style={{ color: "#F9FAFB", fontWeight: 700 }}>{fmtNum(actualVal, 3)}</span>
          </div>
        )}

        {/* forecast models at same T */}
        {forecastAt.length > 0 && (
          <>
            {actualVal !== null && <div style={{ borderTop: "1px dashed #374151", margin: "5px 0" }} />}
            {forecastAt.map(({ m, v, isBest }) => {
              const diff = (actualVal !== null && v !== null) ? v! - actualVal : null;

              // Live point accuracy: how far off is this model RIGHT NOW vs the actual.
              // Uses range-normalisation so zero-crossing signals stay meaningful.
              // Train RMSE (stable quality metric) is already shown in the model table below.
              const acc: number | null = (diff !== null && signalRange > 0)
                ? Math.max(0, Math.min(100, (1 - Math.abs(diff) / signalRange) * 100))
                : null;
              const accLabel = "Live accuracy";
              const accColor = acc === null ? "#6B7280"
                : acc >= 95 ? "#34D399"
                : acc >= 80 ? "#FBBF24"
                : acc >= 60 ? "#FB923C"
                : "#EF4444";
              return (
                <div key={m} style={{ marginBottom: "5px", opacity: isBest ? 1 : 0.8 }}>
                  {/* row 1: model name + value + diff */}
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "20px" }}>
                    <span style={{ color: MODEL_COLOR[m] }}>
                      {m}{isBest ? " (best)" : ""}
                    </span>
                    <span style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <span style={{ color: "#F9FAFB", fontWeight: 600 }}>{fmtNum(v!, 3)}</span>
                      {diff !== null && (
                        <span style={{ fontSize: "9px", color: Math.abs(diff) < 0.01 ? "#34D399" : diff > 0 ? "#FB923C" : "#60A5FA" }}>
                          {diff > 0 ? "+" : ""}{fmtNum(diff, 3)}
                        </span>
                      )}
                    </span>
                  </div>
                  {/* row 2: accuracy bar (only when actual is known at this point) */}
                  {acc !== null && (
                    <div style={{ marginTop: "3px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "9px", color: "#6B7280", marginBottom: "2px" }}>
                        <span>{accLabel}</span>
                        <span style={{ color: accColor, fontWeight: 700 }}>{acc.toFixed(1)}%</span>
                      </div>
                      <div style={{ height: "3px", backgroundColor: "#1F2937", borderRadius: "2px", overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${acc}%`, backgroundColor: accColor, borderRadius: "2px", transition: "width 0.2s" }} />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            {/* CI band */}
            {(point?.confLow !== null && point?.confLow !== undefined) && (
              <div style={{ marginTop: "5px", borderTop: "1px dashed #1F2937", paddingTop: "4px", color: "#4B5563", fontSize: "9px", display: "flex", justifyContent: "space-between" }}>
                <span>95% CI</span>
                <span>[{fmtNum(point!.confLow!, 2)} – {fmtNum(point!.confHigh!, 2)}]</span>
              </div>
            )}
          </>
        )}
      </div>
    );
  };

  return (
    <div
      ref={overlayRef}
      onClick={e => { if (e.target === overlayRef.current) onClose(); }}
      style={{
        position: "fixed", inset: 0, zIndex: 99999,
        backgroundColor: "rgba(0,0,0,0.85)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "24px",
      }}
    >
      <div style={{
        width: "min(1100px, 96vw)",
        maxHeight: "92vh",
        backgroundColor: "#0f1117",
        border: "2px solid #374151",
        borderRadius: "8px",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        fontFamily: "Consolas, monospace",
      }}>
        {/* ── Header ── */}
        <div style={{
          padding: "12px 20px",
          borderBottom: "1px solid #374151",
          backgroundColor: "#1a1f2e",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ fontSize: "18px" }}>📈</span>
            <div>
              <div style={{ fontWeight: 700, fontSize: "15px", color: "#F9FAFB", letterSpacing: "0.5px" }}>
                {tagName}
              </div>
              <div style={{ fontSize: "10px", color: "#6B7280", marginTop: "2px" }}>
                live actuals · frozen forecast · per-second divergence
              </div>
            </div>
            {warnings.length > 0 && (
              <span style={{
                padding: "2px 10px",
                backgroundColor: LEVEL_COLOR[Math.max(...warnings.map(w => w.warning_level))],
                color: "#000",
                fontSize: "10px",
                fontWeight: 700,
                borderRadius: "12px",
              }}>
                {LEVEL_LABEL[Math.max(...warnings.map(w => w.warning_level))]}
              </span>
            )}
          </div>
          {/* Line legend */}
          <div style={{ display: "flex", gap: "14px", alignItems: "center", fontSize: "10px", marginRight: "12px" }}>
            <span style={{ color: "#34D399" }}>▬ Actual</span>
            {ALL_MODELS.map(m => (
              <span key={m} style={{ color: MODEL_COLOR[m] }}>╌ {m}</span>
            ))}
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none", border: "1px solid #374151",
              color: "#9CA3AF", cursor: "pointer",
              width: "28px", height: "28px", borderRadius: "4px",
              fontSize: "16px", display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >✕</button>
        </div>

        {/* ── Body ── */}
        <div style={{ flex: 1, overflow: "auto", padding: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>

          {loading && (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#6B7280", fontSize: "14px" }}>
              Loading trend data…
            </div>
          )}

          {error && (
            <div style={{ padding: "12px", backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid #EF4444", borderRadius: "6px", color: "#FCA5A5", fontSize: "12px" }}>
              ⚠ {error}
            </div>
          )}

          {!loading && !error && (
            <>
              {/* ── Chart ── */}
              <div style={{ backgroundColor: "#161b27", border: "1px solid #374151", borderRadius: "6px", padding: "12px" }}>
                <div style={{ fontSize: "10px", color: "#4B5563", marginBottom: "8px", letterSpacing: "0.8px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>30-min forecast · Python (numpy/statsmodels) · 25% holdout · click to toggle</span>
                  <div style={{ display: "flex", gap: "6px" }}>
                    {ALL_MODELS.map(m => {
                      const mx = evalMetrics[m] as ForecastModel | undefined;
                      const col = MODEL_COLOR[m];
                      return (
                        <button key={m} onClick={() => toggleModel(m)} style={{
                          padding: "2px 10px", fontSize: "10px", cursor: "pointer", borderRadius: "10px",
                          fontFamily: "Consolas, monospace", fontWeight: 700,
                          backgroundColor: vis[m] ? `${col}22` : "rgba(255,255,255,0.04)",
                          border: `1px solid ${vis[m] ? col : "#374151"}`,
                          color: vis[m] ? col : "#4B5563",
                          textDecoration: vis[m] ? "none" : "line-through",
                        }}>
                          {m}{mx && !mx.error && mx.status === "Best Fit" ? " ★" : ""}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={chartData} margin={{ top: 4, right: 20, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
                    <XAxis
                      dataKey="time"
                      tick={{ fill: "#6B7280", fontSize: 9 }}
                      interval={Math.max(59, Math.floor(chartData.length / 12))}
                    />
                    <YAxis tick={{ fill: "#6B7280", fontSize: 9 }} width={56} domain={yDomain} allowDataOverflow />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 10 }} formatter={v => <span style={{ color: "#9CA3AF" }}>{v}</span>} />

                    {/* Baseline mean */}
                    {baseline && (
                      <ReferenceLine y={baseline.mean} stroke="#60A5FA" strokeDasharray="6 3" strokeWidth={1}
                        label={{ value: `μ ${fmtNum(baseline.mean)}`, fill: "#60A5FA", fontSize: 9, position: "insideTopLeft" }} />
                    )}
                    {/* ±2σ */}
                    {baseline && baseline.std > 0 && (
                      <>
                        <ReferenceLine y={baseline.mean + 2 * baseline.std} stroke="#F97316" strokeDasharray="4 4" strokeWidth={1}
                          label={{ value: "+2σ", fill: "#F97316", fontSize: 8, position: "insideTopRight" }} />
                        <ReferenceLine y={baseline.mean - 2 * baseline.std} stroke="#F97316" strokeDasharray="4 4" strokeWidth={1}
                          label={{ value: "-2σ", fill: "#F97316", fontSize: 8, position: "insideBottomRight" }} />
                      </>
                    )}

                    {/* 🟢 Actual — solid green */}
                    <Line type="monotone" dataKey="actual" stroke="#34D399" strokeWidth={2} dot={false} connectNulls={false} name="Actual" />
                    {/* Confidence band for best model */}
                    {forecast?.best_model && evalMetrics[forecast.best_model] && !evalMetrics[forecast.best_model].error && (
                      <>
                        <Line type="monotone" dataKey="confHigh" stroke="#374151" strokeWidth={1} strokeDasharray="2 4" dot={false} connectNulls={false} name="+95% CI" />
                        <Line type="monotone" dataKey="confLow"  stroke="#374151" strokeWidth={1} strokeDasharray="2 4" dot={false} connectNulls={false} name="-95% CI" />
                      </>
                    )}
                    {/* Per-model forecast lines */}
                    {ALL_MODELS.map(m => vis[m] && (
                      <Line key={m} type="monotone" dataKey={DATAKEY[m]} stroke={MODEL_COLOR[m]}
                        strokeWidth={m === forecast?.best_model ? 2.5 : 1.5}
                        strokeDasharray={MODEL_DASH[m]}
                        dot={false} connectNulls={false} name={m} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>

                {/* ── Model Evaluation Table ── */}
                <div style={{ marginTop: "10px", borderTop: "1px solid #1F2937", paddingTop: "10px" }}>
                  <div style={{ fontSize: "9px", color: "#4B5563", letterSpacing: "0.8px", marginBottom: "6px", display: "flex", justifyContent: "space-between" }}>
                    <span>MODEL EVALUATION · PYTHON BACKEND · 25% HOLDOUT TEST SPLIT</span>
                    {forecast && (
                      <span style={{ color: forecast.used_long_history ? "#34D399" : "#374151" }}>
                        {forecast.used_long_history
                          ? `✓ Trained on ${forecast.n_days_trained.toFixed(1)}d · ${forecast.n_train_points} pts`
                          : `trained on ${forecast.n_history - forecast.hold_n} pts (short window)`
                        }
                      </span>
                    )}
                  </div>
                  {!forecast ? (
                    <div style={{ color: "#6B7280", fontSize: "11px" }}>{loading ? "Computing..." : "No forecast data"}</div>
                  ) : (
                  <>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid #1F2937" }}>
                        {["Model", "Confidence", "Status", "Next Value (+1 min)", "In 30 min"].map(h => (
                          <th key={h} style={{ padding: "4px 8px", textAlign: "left", color: "#4B5563", fontWeight: 400, fontSize: "9px", letterSpacing: "0.6px" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {ALL_MODELS.map(m => {
                        const mx = (evalMetrics[m] ?? {}) as ForecastModel;
                        const col = MODEL_COLOR[m];
                        const isBest = m === bestModel;
                        // Parse forecast points — first point = next 1 min, last = +30 min
                        const pts = mx.points ? mx.points.toString().trim().split(/\s+/).map(Number) : [];
                        const nextVal  = pts.length > 0  ? pts[0]              : null;
                        const val30min = pts.length > 0  ? pts[pts.length - 1] : null;
                        return (
                          <tr key={m} style={{ borderBottom: "1px solid #111827", backgroundColor: isBest ? "rgba(52,211,153,0.05)" : "transparent", opacity: vis[m] ? 1 : 0.35 }}>
                            <td style={{ padding: "5px 8px" }}>
                              <span style={{ color: col, fontWeight: 700 }}>{m}</span>
                              {isBest && <span style={{ marginLeft: "6px", fontSize: "9px", padding: "1px 5px", backgroundColor: "rgba(52,211,153,0.15)", color: "#34D399", borderRadius: "8px" }}>★ BEST</span>}
                            </td>
                            <td style={{ padding: "5px 8px" }}>
                              {mx.error || mx.skipped ? <span style={{ color: "#4B5563", fontSize: "9px" }}>—</span> : (
                                <span style={{ fontSize: "9px", padding: "1px 7px", borderRadius: "8px", fontWeight: 700,
                                  color: confColor(mx.confidence ?? "N/A"),
                                  backgroundColor: `${confColor(mx.confidence ?? "N/A")}18`,
                                  border: `1px solid ${confColor(mx.confidence ?? "N/A")}44`
                                }}>{mx.confidence ?? "N/A"}</span>
                              )}
                            </td>
                            <td style={{ padding: "5px 8px" }}>
                              {mx.error ? <span style={{ color: "#EF4444", fontSize: "9px", wordBreak: "break-all" }}>{mx.error.slice(0, 35)}</span>
                               : mx.skipped ? <span style={{ color: "#4B5563", fontSize: "9px" }}>Skipped</span>
                               : (
                                <span style={{ fontSize: "9px", padding: "1px 7px", borderRadius: "8px", fontWeight: 700,
                                  color: statusColor(mx.status ?? ""),
                                  backgroundColor: `${statusColor(mx.status ?? "")}18`,
                                  border: `1px solid ${statusColor(mx.status ?? "")}44`
                                }}>{mx.status ?? "—"}</span>
                              )}
                            </td>
                            <td style={{ padding: "5px 8px" }}>
                              {nextVal !== null && !mx.error && !mx.skipped
                                ? <span style={{ color: col, fontWeight: 700, fontSize: "12px" }}>{fmtNum(nextVal)}</span>
                                : <span style={{ color: "#4B5563" }}>—</span>}
                            </td>
                            <td style={{ padding: "5px 8px" }}>
                              {val30min !== null && !mx.error && !mx.skipped
                                ? <span style={{ color: col, fontWeight: 700, fontSize: "12px" }}>{fmtNum(val30min)}</span>
                                : <span style={{ color: "#4B5563" }}>—</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <div style={{ marginTop: "6px", fontSize: "9px", color: "#4B5563", fontStyle: "italic" }}>
                    ℹ Forecast accuracy improves as more live data is collected. Values converge closer to actual readings after the model has seen several hours of real process behaviour.
                  </div>
                  </>
                  )}
                </div>
              </div>

              {/* ── Bottom row: Model Detail + Baseline + Warnings + Accuracy Log ── */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "12px" }}>

                {/* Model confidence detail */}
                <div style={{ backgroundColor: "#161b27", border: "1px solid #374151", borderRadius: "6px", padding: "12px" }}>
                  <div style={{ fontSize: "10px", color: "#6B7280", marginBottom: "10px", letterSpacing: "0.8px" }}>MODEL CONFIDENCE DETAIL</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {ALL_MODELS.map(m => {
                      const mx = (evalMetrics[m] ?? {}) as ForecastModel;
                      const col = MODEL_COLOR[m];
                      const conf = mx.confidence ?? "N/A";
                      const pct = mx.rmse !== null && mx.rmse !== undefined && (baseline?.std ?? 0) > 0
                        ? Math.max(0, Math.min(100, Math.round((1 - mx.rmse / (baseline!.std * 2)) * 100)))
                        : null;
                      const names: Record<string, string> = { LR: "Linear Regression", HW: "Holt-Winters", FFT: "FFT Spectral", ARIMA: "ARIMA" };
                      return (
                        <div key={m} style={{ padding: "7px 9px", backgroundColor: "rgba(255,255,255,0.03)", borderRadius: "4px", borderLeft: `3px solid ${col}` }}>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                            <span style={{ color: col, fontSize: "11px", fontWeight: 700 }}>{names[m]}</span>
                            <span style={{ fontSize: "9px", padding: "1px 6px", borderRadius: "8px", color: confColor(conf), backgroundColor: `${confColor(conf)}18` }}>
                              {conf} CONFIDENCE
                            </span>
                          </div>
                          {pct !== null && (
                            <div style={{ marginBottom: "4px" }}>
                              <div style={{ height: "4px", backgroundColor: "#1F2937", borderRadius: "2px", overflow: "hidden" }}>
                                <div style={{ height: "100%", width: `${pct}%`, backgroundColor: col, borderRadius: "2px" }} />
                              </div>
                            </div>
                          )}
                          <div style={{ fontSize: "9px", color: statusColor(mx.status ?? "") }}>
                            {mx.error ? `⚠ ${mx.error.slice(0, 60)}`
                              : mx.status === "Diverging" ? "⚠ Forecast divergence — discard"
                              : mx.status === "Best Fit"  ? "✓ Best match on holdout test data"
                              : mx.status === "Stable"    ? "↔ Stable, usable as secondary reference"
                              : "— Insufficient data"}
                          </div>
                          {mx.period_detected && <div style={{ fontSize: "9px", color: "#4B5563", marginTop: "2px" }}>Detected period: {mx.period_detected} steps</div>}
                          {mx.order && <div style={{ fontSize: "9px", color: "#4B5563", marginTop: "2px" }}>ARIMA order: ({Array.isArray(mx.order) ? mx.order.join(",") : mx.order})</div>}
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Baseline stats */}
                <div style={{ backgroundColor: "#161b27", border: "1px solid #374151", borderRadius: "6px", padding: "12px" }}>
                  <div style={{ fontSize: "10px", color: "#6B7280", marginBottom: "10px", letterSpacing: "0.8px" }}>BASELINE STATISTICS</div>
                  {!baseline ? (
                    <div style={{ color: "#6B7280", fontSize: "12px" }}>No baseline computed yet</div>
                  ) : (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                      {[
                        ["Mean (μ)",    fmtNum(baseline.mean)],
                        ["Std Dev (σ)", fmtNum(baseline.std)],
                        ["Min",        fmtNum(baseline.min)],
                        ["Max",        fmtNum(baseline.max)],
                        ["Q1 (25%)",   fmtNum(baseline.p25)],
                        ["Q3 (75%)",   fmtNum(baseline.p75)],
                        ["Median",     fmtNum(baseline.p50)],
                        ["Samples",    String(baseline.count)],
                      ].map(([k, v]) => (
                        <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "4px 6px", backgroundColor: "rgba(255,255,255,0.03)", borderRadius: "3px" }}>
                          <span style={{ color: "#9CA3AF", fontSize: "11px" }}>{k}</span>
                          <span style={{ color: "#F9FAFB", fontSize: "11px", fontWeight: 700 }}>{v}</span>
                        </div>
                      ))}
                      {deviation !== null && (
                        <div style={{
                          gridColumn: "1/-1",
                          padding: "6px 8px",
                          backgroundColor: Math.abs(deviation) > 20 ? "rgba(249,115,22,0.15)" : "rgba(52,211,153,0.1)",
                          border: `1px solid ${Math.abs(deviation) > 20 ? "#F97316" : "#34D399"}`,
                          borderRadius: "4px",
                          display: "flex",
                          justifyContent: "space-between",
                        }}>
                          <span style={{ color: "#9CA3AF", fontSize: "11px" }}>Current Deviation from Mean</span>
                          <span style={{ color: Math.abs(deviation) > 20 ? "#F97316" : "#34D399", fontSize: "12px", fontWeight: 700 }}>
                            {deviation > 0 ? "+" : ""}{fmtNum(deviation, 1)}%
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Active warnings */}
                <div style={{ backgroundColor: "#161b27", border: "1px solid #374151", borderRadius: "6px", padding: "12px" }}>
                  <div style={{ fontSize: "10px", color: "#6B7280", marginBottom: "10px", letterSpacing: "0.8px" }}>
                    ACTIVE WARNINGS ({warnings.length + predAlarms.length})
                  </div>
                  {warnings.length === 0 && predAlarms.length === 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "80px", color: "#34D399", gap: "6px" }}>
                      <span style={{ fontSize: "24px" }}>✓</span>
                      <span style={{ fontSize: "11px" }}>No active warnings</span>
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "260px", overflowY: "auto" }}>
                      {/* Predictive pre-alarms */}
                      {predAlarms.map(a => (
                        <div key={`pa-${a.id}`} style={{
                          padding: "8px 10px",
                          backgroundColor: "rgba(251,146,60,0.08)",
                          borderLeft: "3px solid #FB923C",
                          borderRadius: "3px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          gap: "8px",
                        }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", marginBottom: "3px" }}>
                              <span style={{ fontSize: "9px", padding: "1px 6px", backgroundColor: "#FB923C", color: "#000", fontWeight: 700, borderRadius: "10px" }}>
                                ⚡ PRE-ALARM
                              </span>
                              <span style={{ fontSize: "9px", color: "#6B7280" }}>{a.direction} · {a.model_used.replace(/_/g, " ")}</span>
                            </div>
                            <div style={{ fontSize: "11px", color: "#FED7AA", marginBottom: "3px" }}>
                              Predicted breach in <b style={{ color: "#FB923C" }}>{a.eta_minutes} min</b>
                            </div>
                            <div style={{ display: "flex", gap: "12px", fontSize: "10px", color: "#6B7280" }}>
                              <span>Pred: <b style={{ color: "#F9FAFB" }}>{fmtNum(a.predicted_value)}</b></span>
                              <span>Limit: <b style={{ color: "#FB923C" }}>{fmtNum(a.limit_value)}</b></span>
                              <span>Conf: <b style={{ color: "#A3E635" }}>{a.confidence}</b></span>
                            </div>
                          </div>
                          <button
                            onClick={async () => {
                              const tok = localStorage.getItem("access_token");
                              const hdrs: Record<string,string> = { "Content-Type": "application/json" };
                              if (tok) hdrs["Authorization"] = `Bearer ${tok}`;
                              await fetch(`${API}/api/predictive/alarms/${a.id}/ack`, { method: "POST", headers: hdrs });
                              setPredAlarms(prev => prev.filter(x => x.id !== a.id));
                            }}
                            style={{
                              padding: "3px 8px",
                              fontSize: "9px",
                              backgroundColor: "rgba(251,146,60,0.15)",
                              border: "1px solid #FB923C",
                              color: "#FED7AA",
                              cursor: "pointer",
                              borderRadius: "3px",
                              flexShrink: 0,
                              fontFamily: "Consolas, monospace",
                            }}
                          >
                            ACK
                          </button>
                        </div>
                      ))}
                      {/* PEWS warnings */}
                      {warnings.map(w => (
                        <div key={w.id} style={{
                          padding: "8px 10px",
                          backgroundColor: "rgba(0,0,0,0.3)",
                          borderLeft: `3px solid ${LEVEL_COLOR[w.warning_level]}`,
                          borderRadius: "3px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          gap: "8px",
                        }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", marginBottom: "3px" }}>
                              <span style={{ fontSize: "9px", padding: "1px 6px", backgroundColor: LEVEL_COLOR[w.warning_level], color: "#000", fontWeight: 700, borderRadius: "10px" }}>
                                {LEVEL_LABEL[w.warning_level]}
                              </span>
                              <span style={{ fontSize: "9px", color: "#6B7280" }}>{w.warning_type.replace(/_/g, " ")}</span>
                            </div>
                            <div style={{ fontSize: "11px", color: "#D1D5DB", marginBottom: "3px" }}>{w.message}</div>
                            <div style={{ display: "flex", gap: "12px", fontSize: "10px", color: "#6B7280" }}>
                              {w.current_value !== null && <span>Val: <b style={{ color: "#F9FAFB" }}>{fmtNum(w.current_value)}</b></span>}
                              {w.deviation_pct !== null && <span>Dev: <b style={{ color: "#FBBF24" }}>{fmtNum(w.deviation_pct, 1)}%</b></span>}
                            </div>
                          </div>
                          <button
                            onClick={() => ackWarning(w.id)}
                            style={{
                              padding: "3px 8px",
                              fontSize: "9px",
                              backgroundColor: "rgba(99,102,241,0.2)",
                              border: "1px solid #6366F1",
                              color: "#A5B4FC",
                              cursor: "pointer",
                              borderRadius: "3px",
                              flexShrink: 0,
                              fontFamily: "Consolas, monospace",
                            }}
                          >
                            ACK
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {/* ── Per-second Live Divergence Log ── */}
                <div style={{ backgroundColor: "#161b27", border: "1px solid #374151", borderRadius: "6px", padding: "12px" }}>
                  {/* Header + live count */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <div style={{ fontSize: "10px", color: "#6B7280", letterSpacing: "0.8px" }}>⚡ LIVE DIVERGENCE LOG</div>
                    <div style={{ fontSize: "9px", color: "#4B5563" }}>{errTick >= 0 ? liveErrRef.current.length : 0} secs tracked</div>
                  </div>

                  {/* Cumulative loss row — total absolute error per model */}
                  {errTick >= 0 && Object.keys(cumErrRef.current).length > 0 && (
                    <div style={{
                      display: "grid", gridTemplateColumns: "58px 54px 72px 72px 72px 72px", gap: "2px",
                      padding: "3px 4px", marginBottom: "6px", borderRadius: "3px", fontSize: "9px",
                      backgroundColor: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.35)",
                    }}>
                      <span style={{ color: "#818CF8", fontWeight: 700 }}>ΣLOSS</span>
                      <span style={{ color: "#4B5563" }}>—</span>
                      {ALL_MODELS.map(m => {
                        const v = cumErrRef.current[m];
                        return (
                          <span key={m} style={{ color: "#A78BFA", fontWeight: 700 }}>
                            {v !== undefined ? fmtNum(v, 1) : "—"}
                          </span>
                        );
                      })}
                    </div>
                  )}

                  {errTick >= 0 && liveErrRef.current.length === 0 ? (
                    <div style={{ color: "#4B5563", fontSize: "11px", textAlign: "center", marginTop: "20px", lineHeight: "1.5" }}>
                      Waiting for actuals to reach<br/>forecast timestamps…
                    </div>
                  ) : (
                    <div style={{ overflowY: "auto", maxHeight: "190px", display: "flex", flexDirection: "column", gap: "2px" }}>
                      {/* Column headers */}
                      <div style={{
                        display: "grid", gridTemplateColumns: "58px 54px 72px 72px 72px 72px", gap: "2px",
                        padding: "2px 4px", fontSize: "8px", color: "#374151", letterSpacing: "0.5px",
                        position: "sticky", top: 0, backgroundColor: "#161b27",
                      }}>
                        <span>TIME</span><span style={{ color: "#34D399" }}>ACTUAL</span>
                        {ALL_MODELS.map(m => (
                          <div key={m} style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
                            <span style={{ color: MODEL_COLOR[m], fontWeight: 700 }}>{m}</span>
                            <span style={{ color: "#4B5563", fontSize: "7px" }}>val · Δ%</span>
                          </div>
                        ))}
                      </div>
                      {/* One row per second — newest first */}
                      {errTick >= 0 && liveErrRef.current.map((rec, idx) => {
                        const minPct = ALL_MODELS.reduce<number | null>((b, m) =>
                          rec.errPct[m] !== undefined && (b === null || rec.errPct[m]! < b) ? rec.errPct[m]! : b, null);
                        const bg = minPct === null ? "transparent"
                          : minPct < 1  ? "rgba(52,211,153,0.09)"
                          : minPct < 3  ? "rgba(251,191,36,0.09)"
                          : minPct < 8  ? "rgba(249,115,22,0.09)"
                          : "rgba(239,68,68,0.09)";
                        return (
                          <div key={idx} style={{
                            display: "grid", gridTemplateColumns: "58px 54px 72px 72px 72px 72px", gap: "2px",
                            padding: "2px 4px", borderRadius: "2px", backgroundColor: bg, fontSize: "9px",
                          }}>
                            <span style={{ color: "#6B7280" }}>{fmtTime(rec.ts)}</span>
                            <span style={{ color: "#34D399", fontWeight: 700 }}>{fmtNum(rec.actual, 2)}</span>
                            {ALL_MODELS.map(m => {
                              const p = rec.errPct[m];
                              const fc2 = rec.fcVals[m];
                              const c = p === undefined ? "#374151"
                                : p < 1  ? "#34D399"
                                : p < 3  ? "#FBBF24"
                                : p < 8  ? "#F97316"
                                : "#EF4444";
                              return (
                                <div key={m} style={{ display: "flex", flexDirection: "column", lineHeight: 1.3 }}>
                                  <span style={{ color: c, fontWeight: 700, fontSize: "9px" }}>
                                    {fc2 !== undefined ? fmtNum(fc2, 2) : "—"}
                                  </span>
                                  <span style={{ color: c, fontSize: "8px", opacity: 0.8 }}>
                                    {p !== undefined ? `${fmtNum(p, 1)}%` : "—"}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
