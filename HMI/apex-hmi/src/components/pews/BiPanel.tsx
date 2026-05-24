/**
 * BiPanel — BI Analytics tab
 *
 * Lets the user:
 *  1. Pick a production tag + influencing tags from DB-discovered list
 *  2. Set date range
 *  3. Set rated capacity
 *  4. Run full BI analysis (calls POST /api/bi/analysis)
 *  5. View results: baseline, delta score, availability, efficiency, stability
 */
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/auth-context";

const API = "http://localhost:6001";

interface TagInfo { tag_id: string; first_seen: string | null; last_seen: string | null }
interface AnalysisResults {
  data_points: number;
  results: Record<string, unknown>;
}

function fmt(val: unknown): string {
  if (val === null || val === undefined) return "—";
  if (typeof val === "number") return isNaN(val) ? "—" : val.toFixed(3);
  if (typeof val === "object") return JSON.stringify(val, null, 2);
  return String(val);
}

function ResultCard({ title, data }: { title: string; data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined && typeof v !== "object");
  if (entries.length === 0) return null;
  return (
    <div className="p-4 bg-gray-900 border border-gray-700 rounded-lg">
      <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">{title}</div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 text-sm border-b border-gray-800 pb-1">
            <span className="text-gray-400 truncate">{k.replace(/_/g, " ")}</span>
            <span className="text-white font-mono text-right">{fmt(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ISO date string helpers
const toIso = (d: string) => d ? new Date(d).toISOString() : "";
const today = () => new Date().toISOString().slice(0, 16);
const yesterday = () => new Date(Date.now() - 86400000).toISOString().slice(0, 16);

export default function BiPanel() {
  const { token } = useAuth();
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const [tags, setTags]                 = useState<TagInfo[]>([]);
  const [tagsLoading, setTagsLoading]   = useState(true);
  const [productionTag, setProductionTag] = useState("");
  const [influencing, setInfluencing]   = useState<string[]>([]);
  const [startDate, setStartDate]       = useState(yesterday());
  const [endDate, setEndDate]           = useState(today());
  const [ratedCap, setRatedCap]         = useState(120);
  const [resample, setResample]         = useState(15);
  const [running, setRunning]           = useState(false);
  const [results, setResults]           = useState<AnalysisResults | null>(null);
  const [error, setError]               = useState<string | null>(null);

  // Load available tags on mount
  useEffect(() => {
    fetch(`${API}/api/bi/tags`, { headers })
      .then(r => r.json())
      .then(d => { if (d.success) setTags(d.tags); })
      .catch(() => {})
      .finally(() => setTagsLoading(false));
  }, [token]);

  const toggleInfluencing = (tag: string) => {
    setInfluencing(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    );
  };

  const runAnalysis = useCallback(async () => {
    if (!productionTag) { setError("Select a production tag first"); return; }
    setRunning(true); setError(null); setResults(null);
    try {
      const res = await fetch(`${API}/api/bi/analysis`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          production_tag:   productionTag,
          influencing_tags: influencing,
          start:            toIso(startDate),
          end:              toIso(endDate),
          rated_capacity:   ratedCap,
          resample_minutes: resample,
        }),
      });
      const data = await res.json();
      if (data.success) setResults(data);
      else setError(data.error ?? "Analysis failed");
    } catch (e: unknown) {
      setError((e as Error).message ?? "Network error");
    } finally {
      setRunning(false);
    }
  }, [productionTag, influencing, startDate, endDate, ratedCap, resample, token]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* ── Left: Config panel ── */}
      <div className="lg:col-span-1 space-y-4">
        <div className="p-4 bg-gray-900 border border-gray-700 rounded-lg space-y-4">
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">Analysis Configuration</h3>

          {/* Date range */}
          <div className="space-y-2">
            <label className="text-xs text-gray-400">Start Date</label>
            <input type="datetime-local" value={startDate} onChange={e => setStartDate(e.target.value)}
              className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white" />
            <label className="text-xs text-gray-400">End Date</label>
            <input type="datetime-local" value={endDate} onChange={e => setEndDate(e.target.value)}
              className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white" />
          </div>

          {/* Rated capacity + resample */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-gray-400">Rated Capacity</label>
              <input type="number" value={ratedCap} onChange={e => setRatedCap(Number(e.target.value))}
                className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Resample (min)</label>
              <input type="number" value={resample} min={1} onChange={e => setResample(Number(e.target.value))}
                className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white" />
            </div>
          </div>

          {/* Tag selector */}
          {tagsLoading ? (
            <div className="text-xs text-gray-500">Loading tags…</div>
          ) : (
            <div>
              <label className="text-xs text-gray-400 block mb-1">
                Production Tag <span className="text-red-400">*</span>
              </label>
              <select value={productionTag} onChange={e => setProductionTag(e.target.value)}
                className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white">
                <option value="">— select —</option>
                {tags.map(t => <option key={t.tag_id} value={t.tag_id}>{t.tag_id}</option>)}
              </select>

              <label className="text-xs text-gray-400 block mt-3 mb-1">
                Influencing Tags <span className="text-gray-600">(multi-select)</span>
              </label>
              <div className="max-h-48 overflow-y-auto space-y-1 border border-gray-700 rounded p-2 bg-gray-800">
                {tags.filter(t => t.tag_id !== productionTag).map(t => (
                  <label key={t.tag_id} className="flex items-center gap-2 cursor-pointer hover:bg-gray-700 px-1 rounded">
                    <input type="checkbox" checked={influencing.includes(t.tag_id)}
                      onChange={() => toggleInfluencing(t.tag_id)}
                      className="accent-blue-500" />
                    <span className="text-xs text-gray-300 font-mono truncate">{t.tag_id}</span>
                  </label>
                ))}
              </div>
              {influencing.length > 0 && (
                <div className="text-xs text-gray-500 mt-1">{influencing.length} influencing tag(s) selected</div>
              )}
            </div>
          )}

          {/* Run button */}
          <button
            onClick={runAnalysis}
            disabled={running || !productionTag}
            className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-semibold rounded transition"
          >
            {running ? "Running Analysis…" : "▶ Run BI Analysis"}
          </button>
        </div>
      </div>

      {/* ── Right: Results ── */}
      <div className="lg:col-span-2">
        {error && (
          <div className="mb-4 p-3 bg-red-900/40 border border-red-700 rounded text-red-300 text-sm">⚠ {error}</div>
        )}

        {!results && !running && !error && (
          <div className="flex flex-col items-center justify-center h-64 text-gray-600">
            <span className="text-5xl mb-3">📊</span>
            <span className="text-sm">Select tags and date range, then run analysis</span>
          </div>
        )}

        {running && (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-3" />
            <span className="text-sm">Running BI engines on {toIso(startDate).slice(0,10)} → {toIso(endDate).slice(0,10)}…</span>
          </div>
        )}

        {results && (
          <div className="space-y-4">
            {/* Meta */}
            <div className="p-3 bg-gray-800 border border-gray-700 rounded text-xs text-gray-400 flex flex-wrap gap-4">
              <span>Data points: <span className="text-white">{results.data_points}</span></span>
              <span>Production tag: <span className="text-white font-mono">{productionTag}</span></span>
              <span>Influencing: <span className="text-white">{influencing.length}</span></span>
            </div>

            {/* Result cards */}
            {Object.entries(results.results).map(([key, val]) => {
              if (!val || typeof val !== "object") return null;
              return <ResultCard key={key} title={key.replace(/_/g, " ")} data={val as Record<string, unknown>} />;
            })}
          </div>
        )}
      </div>
    </div>
  );
}
