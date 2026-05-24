/**
 * AlarmHistoryModal – ISA-18.2 compliant full alarm lifecycle viewer
 * Shows ALL historical alarms (active + cleared) with full details:
 *   • When raised, what level (LL/L/H/HH), value that triggered it
 *   • Who acknowledged, when, notes
 *   • Who cleared, when, reason + notes
 *   • Duration
 * Filterable by: date range, tag, alarm level, state, priority, free-text search
 * Paginated, sortable columns
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  X, Search, Filter, ChevronLeft, ChevronRight, Download,
  AlertTriangle, AlertCircle, CheckCircle, Clock, User,
  RefreshCw, ChevronUp, ChevronDown, ChevronsUpDown, Info
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePermission } from "@/hooks/usePermission";

// ─── Types ───────────────────────────────────────────────────────────────────
interface AlarmRecord {
  event_id: number;
  tag_id: string;
  raised_at: string;
  event_type: string;
  alarm_state: string;
  alarm_priority: number;
  alarm_level: string;
  message: string;
  alarm_setpoint: number | null;
  alarm_actual_value: number | null;
  severity: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  ack_notes: string | null;
  cleared_by: string | null;
  cleared_at: string | null;
  clear_reason: string | null;
  clear_notes: string | null;
  duration_minutes: number | null;
  suppressed_by: string | null;
  suppressed_at: string | null;
  suppress_until: string | null;
}

interface FiltersState {
  search: string;
  date_from: string;
  date_to: string;
  tag_id: string;
  alarm_level: string;
  alarm_state: string;
  alarm_priority: string;
}

interface Props {
  onClose: () => void;
}

// ─── Constants ───────────────────────────────────────────────────────────────
const ALARM_LEVELS = ["", "LL", "LOLO", "L", "LOW", "H", "HIGH", "HH", "HIHI", "DEVIATION", "ROC"];
const ALARM_STATES = ["", "ACTIVE_UNACK", "ACTIVE_ACK", "RTN_UNACK", "CLEARED", "SUPPRESSED"];
const PRIORITIES   = [
  { value: "", label: "All Priorities" },
  { value: "5", label: "5 – Critical" },
  { value: "4", label: "4 – Urgent" },
  { value: "3", label: "3 – High" },
  { value: "2", label: "2 – Warning" },
  { value: "1", label: "1 – Low" },
];
const PAGE_SIZES = [25, 50, 100, 200];

// ─── Helpers ─────────────────────────────────────────────────────────────────
function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function fmtDuration(mins: number | null): string {
  if (mins === null) return "—";
  if (mins < 1) return "<1m";
  if (mins < 60) return `${Math.round(mins)}m`;
  const h = Math.floor(mins / 60);
  const m = Math.round(mins % 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function levelColor(level: string): string {
  const l = (level || "").toUpperCase();
  if (l === "LL" || l === "LOLO") return "text-purple-300 bg-purple-900/50 border-purple-600";
  if (l === "L"  || l === "LOW")  return "text-blue-300   bg-blue-900/50   border-blue-600";
  if (l === "H"  || l === "HIGH") return "text-yellow-300 bg-yellow-900/50 border-yellow-600";
  if (l === "HH" || l === "HIHI") return "text-red-300    bg-red-900/50    border-red-600";
  return "text-slate-300 bg-slate-800/50 border-slate-600";
}

function stateColor(state: string): string {
  switch (state) {
    case "ACTIVE_UNACK": return "text-red-300    bg-red-900/40    border-red-500";
    case "ACTIVE_ACK":   return "text-blue-300   bg-blue-900/40   border-blue-500";
    case "RTN_UNACK":    return "text-orange-300 bg-orange-900/40 border-orange-500";
    case "CLEARED":      return "text-green-300  bg-green-900/40  border-green-500";
    case "SUPPRESSED":   return "text-purple-300 bg-purple-900/40 border-purple-500";
    default:             return "text-slate-400  bg-slate-800/40  border-slate-600";
  }
}

function priorityLabel(p: number): string {
  return ["", "LOW", "WARNING", "HIGH", "URGENT", "CRITICAL"][p] || String(p);
}

function priorityColor(p: number): string {
  if (p === 5) return "text-red-400    bg-red-950    border-red-700";
  if (p === 4) return "text-orange-400 bg-orange-950 border-orange-700";
  if (p === 3) return "text-yellow-400 bg-yellow-950 border-yellow-700";
  if (p === 2) return "text-blue-400   bg-blue-950   border-blue-700";
  return "text-slate-400 bg-slate-900 border-slate-700";
}

// ─── SortIcon ────────────────────────────────────────────────────────────────
function SortIcon({ col, sortBy, sortDir }: { col: string; sortBy: string; sortDir: string }) {
  if (sortBy !== col) return <ChevronsUpDown className="w-3 h-3 text-slate-600" />;
  return sortDir === "asc"
    ? <ChevronUp   className="w-3 h-3 text-blue-400" />
    : <ChevronDown className="w-3 h-3 text-blue-400" />;
}

// ─── Main Component ──────────────────────────────────────────────────────────
export default function AlarmHistoryModal({ onClose }: Props) {
  const canExport = usePermission('reports', 'canGenerate');
  const [records, setRecords]       = useState<AlarmRecord[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage]             = useState(1);
  const [pageSize, setPageSize]     = useState(50);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [tagList, setTagList]       = useState<string[]>([]);
  const [expanded, setExpanded]     = useState<number | null>(null);
  const [sortBy, setSortBy]         = useState("time");
  const [sortDir, setSortDir]       = useState("desc");

  const [filters, setFilters] = useState<FiltersState>({
    search:        "",
    date_from:     "",
    date_to:       "",
    tag_id:        "",
    alarm_level:   "",
    alarm_state:   "",
    alarm_priority:"",
  });
  const [appliedFilters, setAppliedFilters] = useState<FiltersState>(filters);

  // debounce search
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Fetch tag list for dropdown ───────────────────────────────────────────
  useEffect(() => {
    fetch("/api/alarms/history/tags", {
      headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` },
    })
      .then(r => r.json())
      .then(d => { if (d.success) setTagList(d.tags); })
      .catch(() => {});
  }, []);

  // ── Fetch records ─────────────────────────────────────────────────────────
  const fetchHistory = useCallback(async (f: FiltersState, pg: number, ps: number, sb: string, sd: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("page",      String(pg));
      params.set("page_size", String(ps));
      params.set("sort_by",   sb);
      params.set("sort_dir",  sd);
      if (f.search)         params.set("search",         f.search);
      if (f.date_from)      params.set("date_from",      f.date_from);
      if (f.date_to)        params.set("date_to",        f.date_to);
      if (f.tag_id)         params.set("tag_id",         f.tag_id);
      if (f.alarm_level)    params.set("alarm_level",    f.alarm_level);
      if (f.alarm_state)    params.set("alarm_state",    f.alarm_state);
      if (f.alarm_priority) params.set("alarm_priority", f.alarm_priority);

      const resp = await fetch(`/api/alarms/history?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` },
      });
      const data = await resp.json();
      if (!data.success) throw new Error(data.error || "Unknown error");
      setRecords(data.records);
      setTotalCount(data.total_count);
      setTotalPages(data.total_pages);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory(appliedFilters, page, pageSize, sortBy, sortDir);
  }, [appliedFilters, page, pageSize, sortBy, sortDir, fetchHistory]);

  // ── Sort column click ─────────────────────────────────────────────────────
  const handleSort = (col: string) => {
    if (sortBy === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortBy(col); setSortDir("desc"); }
    setPage(1);
  };

  // ── Apply filters ─────────────────────────────────────────────────────────
  const applyFilters = () => { setAppliedFilters({ ...filters }); setPage(1); };
  const clearFilters = () => {
    const empty: FiltersState = { search:"", date_from:"", date_to:"", tag_id:"", alarm_level:"", alarm_state:"", alarm_priority:"" };
    setFilters(empty); setAppliedFilters(empty); setPage(1);
  };

  // ── CSV Export ────────────────────────────────────────────────────────────
  const exportCSV = () => {
    const header = ["event_id","tag_id","raised_at","alarm_level","alarm_state","priority","value","setpoint","message","acknowledged_by","acknowledged_at","ack_notes","cleared_by","cleared_at","clear_reason","clear_notes","duration_minutes"];
    const rows = records.map(r => [
      r.event_id, r.tag_id, r.raised_at, r.alarm_level, r.alarm_state, priorityLabel(r.alarm_priority),
      r.alarm_actual_value ?? "", r.alarm_setpoint ?? "", `"${(r.message||"").replace(/"/g,'""')}"`,
      r.acknowledged_by ?? "", r.acknowledged_at ?? "", `"${(r.ack_notes||"").replace(/"/g,'""')}"`,
      r.cleared_by ?? "", r.cleared_at ?? "", `"${(r.clear_reason||"").replace(/"/g,'""')}"`,
      `"${(r.clear_notes||"").replace(/"/g,'""')}"`, r.duration_minutes ?? "",
    ]);
    const csv = [header, ...rows].map(r => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `alarm_history_${new Date().toISOString().slice(0,10)}.csv`; a.click();
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-2" onClick={onClose}>
      <div
        className="bg-gradient-to-br from-slate-900 via-slate-850 to-slate-900 border-2 border-blue-500/40 rounded-xl w-full max-w-[98vw] h-[96vh] flex flex-col shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800/80 rounded-t-xl flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-600/30 border border-blue-500/50 flex items-center justify-center">
              <Clock className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Alarm History</h2>
              <p className="text-xs text-slate-400">ISA-18.2 Lifecycle Log — All events including cleared</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 bg-slate-700/60 px-2 py-1 rounded">
              {totalCount.toLocaleString()} records
            </span>
            <button onClick={() => fetchHistory(appliedFilters, page, pageSize, sortBy, sortDir)} title="Refresh"
              className="p-2 rounded bg-slate-700/60 hover:bg-slate-600 border border-slate-600 text-slate-300 transition-colors">
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </button>
            {canExport && (
              <button onClick={exportCSV} title="Export CSV"
                className="p-2 rounded bg-green-700/60 hover:bg-green-600 border border-green-600 text-green-300 transition-colors flex items-center gap-1 px-3">
                <Download className="w-4 h-4" />
                <span className="text-xs font-mono">CSV</span>
              </button>
            )}
            <button onClick={onClose} className="p-2 rounded bg-slate-700/60 hover:bg-red-700/60 border border-slate-600 hover:border-red-500 text-slate-300 hover:text-white transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* ── Filters ────────────────────────────────────────────────── */}
        <div className="px-4 py-3 border-b border-slate-700/60 bg-slate-800/40 flex-shrink-0">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
            {/* Search */}
            <div className="relative lg:col-span-2">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input
                type="text" placeholder="Search tag or message..."
                value={filters.search}
                onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
                onKeyDown={e => e.key === "Enter" && applyFilters()}
                className="w-full pl-7 pr-3 py-1.5 rounded bg-slate-700/60 border border-slate-600 text-slate-200 text-xs placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>
            {/* Date From */}
            <input type="datetime-local" value={filters.date_from}
              onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))}
              className="px-2 py-1.5 rounded bg-slate-700/60 border border-slate-600 text-slate-200 text-xs focus:outline-none focus:border-blue-500"
            />
            {/* Date To */}
            <input type="datetime-local" value={filters.date_to}
              onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))}
              className="px-2 py-1.5 rounded bg-slate-700/60 border border-slate-600 text-slate-200 text-xs focus:outline-none focus:border-blue-500"
            />
            {/* Tag */}
            <select value={filters.tag_id} onChange={e => setFilters(f => ({ ...f, tag_id: e.target.value }))}
              className="px-2 py-1.5 rounded bg-slate-700/60 border border-slate-600 text-slate-200 text-xs focus:outline-none focus:border-blue-500">
              <option value="">All Tags</option>
              {tagList.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            {/* Alarm Level */}
            <select value={filters.alarm_level} onChange={e => setFilters(f => ({ ...f, alarm_level: e.target.value }))}
              className="px-2 py-1.5 rounded bg-slate-700/60 border border-slate-600 text-slate-200 text-xs focus:outline-none focus:border-blue-500">
              <option value="">All Levels</option>
              {ALARM_LEVELS.filter(Boolean).map(l => <option key={l} value={l}>{l}</option>)}
            </select>
            {/* State */}
            <select value={filters.alarm_state} onChange={e => setFilters(f => ({ ...f, alarm_state: e.target.value }))}
              className="px-2 py-1.5 rounded bg-slate-700/60 border border-slate-600 text-slate-200 text-xs focus:outline-none focus:border-blue-500">
              <option value="">All States</option>
              {ALARM_STATES.filter(Boolean).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          {/* Row 2: priority + buttons */}
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <select value={filters.alarm_priority} onChange={e => setFilters(f => ({ ...f, alarm_priority: e.target.value }))}
              className="px-2 py-1.5 rounded bg-slate-700/60 border border-slate-600 text-slate-200 text-xs focus:outline-none focus:border-blue-500">
              {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            <button onClick={applyFilters}
              className="flex items-center gap-1 px-3 py-1.5 rounded bg-blue-600/60 hover:bg-blue-600 border border-blue-500 text-white text-xs font-semibold transition-colors">
              <Filter className="w-3 h-3" /> Apply
            </button>
            <button onClick={clearFilters}
              className="flex items-center gap-1 px-3 py-1.5 rounded bg-slate-700/60 hover:bg-slate-600 border border-slate-600 text-slate-300 text-xs transition-colors">
              <X className="w-3 h-3" /> Clear
            </button>
            {/* Page size */}
            <div className="flex items-center gap-1 ml-auto text-xs text-slate-400">
              <span>Show:</span>
              {PAGE_SIZES.map(s => (
                <button key={s} onClick={() => { setPageSize(s); setPage(1); }}
                  className={cn("px-2 py-0.5 rounded border text-xs transition-colors",
                    pageSize === s ? "bg-blue-600 border-blue-500 text-white" : "bg-slate-700/60 border-slate-600 text-slate-300 hover:bg-slate-600"
                  )}>{s}</button>
              ))}
            </div>
          </div>
        </div>

        {/* ── Table ──────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-auto">
          {error && (
            <div className="m-4 p-3 rounded bg-red-900/40 border border-red-600 text-red-300 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {error}
            </div>
          )}
          {loading && !records.length && (
            <div className="flex items-center justify-center h-40 gap-3 text-slate-400">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-400" />
              <span>Loading alarm history...</span>
            </div>
          )}
          {!loading && !error && records.length === 0 && (
            <div className="flex flex-col items-center justify-center h-40 gap-2 text-slate-500">
              <Info className="w-10 h-10" />
              <p>No alarm records match your filters.</p>
            </div>
          )}
          {records.length > 0 && (
            <table className="w-full text-xs border-collapse">
              <thead className="sticky top-0 z-10">
                <tr className="bg-slate-800 border-b border-slate-700">
                  {/* Raised At */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap cursor-pointer hover:text-white select-none"
                    onClick={() => handleSort("time")}>
                    <div className="flex items-center gap-1">Raised At <SortIcon col="time" sortBy={sortBy} sortDir={sortDir} /></div>
                  </th>
                  {/* Tag */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap cursor-pointer hover:text-white select-none"
                    onClick={() => handleSort("tag_id")}>
                    <div className="flex items-center gap-1">Tag <SortIcon col="tag_id" sortBy={sortBy} sortDir={sortDir} /></div>
                  </th>
                  {/* Level */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap cursor-pointer hover:text-white select-none"
                    onClick={() => handleSort("alarm_level")}>
                    <div className="flex items-center gap-1">Level <SortIcon col="alarm_level" sortBy={sortBy} sortDir={sortDir} /></div>
                  </th>
                  {/* Priority */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap cursor-pointer hover:text-white select-none"
                    onClick={() => handleSort("alarm_priority")}>
                    <div className="flex items-center gap-1">Priority <SortIcon col="alarm_priority" sortBy={sortBy} sortDir={sortDir} /></div>
                  </th>
                  {/* State */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap">State</th>
                  {/* Trigger Value */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap">Value / SP</th>
                  {/* Message */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold">Message</th>
                  {/* ACK */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap">Acknowledged By</th>
                  {/* Cleared */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap">Cleared By</th>
                  {/* Duration */}
                  <th className="px-3 py-2.5 text-left text-slate-300 font-semibold whitespace-nowrap">Duration</th>
                  {/* Expand */}
                  <th className="px-2 py-2.5 w-6"></th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, idx) => {
                  const isExp = expanded === r.event_id;
                  const rowBg = idx % 2 === 0 ? "bg-slate-900/40" : "bg-slate-800/20";
                  const isCleared    = r.alarm_state === "CLEARED";
                  const isSuppressed = r.alarm_state === "SUPPRESSED";

                  return [
                    <tr key={r.event_id}
                      className={cn(rowBg, "border-b border-slate-800 hover:bg-slate-700/30 transition-colors cursor-pointer",
                        isCleared && "opacity-70",
                        isSuppressed && "opacity-60 border-purple-900/40")}
                      onClick={() => setExpanded(isExp ? null : r.event_id)}
                    >
                      {/* Raised At */}
                      <td className="px-3 py-2 whitespace-nowrap text-slate-300 font-mono">{fmt(r.raised_at)}</td>
                      {/* Tag */}
                      <td className="px-3 py-2 whitespace-nowrap font-semibold text-amber-300">{r.tag_id}</td>
                      {/* Level */}
                      <td className="px-3 py-2 whitespace-nowrap">
                        {r.alarm_level ? (
                          <span className={cn("px-1.5 py-0.5 rounded border text-[10px] font-bold uppercase", levelColor(r.alarm_level))}>
                            {r.alarm_level}
                          </span>
                        ) : <span className="text-slate-600">—</span>}
                      </td>
                      {/* Priority */}
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className={cn("px-1.5 py-0.5 rounded border text-[10px] font-bold", priorityColor(r.alarm_priority))}>
                          {priorityLabel(r.alarm_priority)}
                        </span>
                      </td>
                      {/* State */}
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className={cn("px-1.5 py-0.5 rounded border text-[10px] font-bold", stateColor(r.alarm_state))}>
                          {r.alarm_state === 'ACTIVE_UNACK' ? 'UNACK' :
                           r.alarm_state === 'ACTIVE_ACK'   ? '✓ ACK' :
                           r.alarm_state === 'RTN_UNACK'    ? 'RTN' :
                           r.alarm_state === 'CLEARED'      ? '✓ CLEARED' :
                           r.alarm_state === 'SUPPRESSED'   ? '⊘ SUPP' :
                           r.alarm_state ?? '—'}
                        </span>
                      </td>
                      {/* Value / SP */}
                      <td className="px-3 py-2 whitespace-nowrap font-mono">
                        <span className="text-red-300 font-bold">{r.alarm_actual_value?.toFixed(2) ?? "—"}</span>
                        {r.alarm_setpoint != null && (
                          <span className="text-slate-500"> / <span className="text-slate-400">{r.alarm_setpoint?.toFixed(2)}</span></span>
                        )}
                      </td>
                      {/* Message */}
                      <td className="px-3 py-2 text-slate-300 max-w-[220px] truncate" title={r.message}>{r.message}</td>
                      {/* ACK */}
                      <td className="px-3 py-2 whitespace-nowrap">
                        {r.suppressed_by ? (
                          <div className="flex items-center gap-1">
                            <span className="text-purple-400 font-bold text-[10px]">⊘</span>
                            <span className="text-purple-300 font-semibold">{r.suppressed_by}</span>
                          </div>
                        ) : r.acknowledged_by ? (
                          <div className="flex items-center gap-1">
                            <CheckCircle className="w-3 h-3 text-blue-400 flex-shrink-0" />
                            <span className="text-blue-300 font-semibold">{r.acknowledged_by}</span>
                          </div>
                        ) : <span className="text-slate-600 italic">Not ACK'd</span>}
                      </td>
                      {/* Cleared */}
                      <td className="px-3 py-2 whitespace-nowrap">
                        {r.cleared_by ? (
                          <div className="flex items-center gap-1">
                            <CheckCircle className="w-3 h-3 text-green-400 flex-shrink-0" />
                            <span className="text-green-300 font-semibold">{r.cleared_by}</span>
                          </div>
                        ) : <span className="text-slate-600 italic">Active</span>}
                      </td>
                      {/* Duration */}
                      <td className="px-3 py-2 whitespace-nowrap font-mono text-slate-300">{fmtDuration(r.duration_minutes)}</td>
                      {/* Expand icon */}
                      <td className="px-2 py-2 text-slate-600">
                        {isExp ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </td>
                    </tr>,

                    /* ── Expanded detail row ── */
                    isExp && (
                      <tr key={`exp-${r.event_id}`} className="bg-slate-800/60">
                        <td colSpan={11} className="px-6 py-4">
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

                            {/* Alarm raised */}
                            <div className="rounded-lg bg-red-950/40 border border-red-700/40 p-3">
                              <div className="flex items-center gap-2 mb-2">
                                <AlertCircle className="w-4 h-4 text-red-400" />
                                <span className="text-red-400 font-bold text-xs uppercase">Alarm Raised</span>
                              </div>
                              <div className="space-y-1 text-xs">
                                <div className="flex justify-between"><span className="text-slate-500">Time</span><span className="text-slate-200 font-mono">{fmt(r.raised_at)}</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">Tag</span><span className="text-amber-300 font-semibold">{r.tag_id}</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">Level</span><span className={cn("px-1 rounded border text-[10px] font-bold", levelColor(r.alarm_level))}>{r.alarm_level || "—"}</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">Trigger Value</span><span className="text-red-300 font-bold font-mono">{r.alarm_actual_value?.toFixed(4) ?? "—"}</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">Setpoint</span><span className="text-slate-300 font-mono">{r.alarm_setpoint?.toFixed(4) ?? "—"}</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">Priority</span><span className={cn("px-1 rounded border text-[10px] font-bold", priorityColor(r.alarm_priority))}>{priorityLabel(r.alarm_priority)}</span></div>
                                <div className="mt-1 pt-1 border-t border-slate-700">
                                  <span className="text-slate-500">Message: </span>
                                  <span className="text-slate-300">{r.message}</span>
                                </div>
                              </div>
                            </div>

                            {/* ACK details */}
                            <div className={cn("rounded-lg border p-3", r.acknowledged_by ? "bg-blue-950/40 border-blue-700/40" : "bg-slate-800/40 border-slate-700/40")}>
                              <div className="flex items-center gap-2 mb-2">
                                <User className="w-4 h-4 text-blue-400" />
                                <span className="text-blue-400 font-bold text-xs uppercase">Acknowledgement</span>
                              </div>
                              {r.acknowledged_by ? (
                                <div className="space-y-1 text-xs">
                                  <div className="flex justify-between"><span className="text-slate-500">Operator</span><span className="text-blue-300 font-semibold">{r.acknowledged_by}</span></div>
                                  <div className="flex justify-between"><span className="text-slate-500">Time</span><span className="text-slate-200 font-mono">{fmt(r.acknowledged_at)}</span></div>
                                  {r.ack_notes && <div className="mt-1 pt-1 border-t border-slate-700"><span className="text-slate-500">Notes: </span><span className="text-slate-300">{r.ack_notes}</span></div>}
                                </div>
                              ) : (
                                <p className="text-slate-600 italic text-xs">Not yet acknowledged</p>
                              )}
                            </div>

                            {/* Clear details */}
                            <div className={cn("rounded-lg border p-3", r.cleared_by ? "bg-green-950/40 border-green-700/40" : "bg-slate-800/40 border-slate-700/40")}>
                              <div className="flex items-center gap-2 mb-2">
                                <CheckCircle className="w-4 h-4 text-green-400" />
                                <span className="text-green-400 font-bold text-xs uppercase">Clearance</span>
                              </div>
                              {r.cleared_by ? (
                                <div className="space-y-1 text-xs">
                                  <div className="flex justify-between"><span className="text-slate-500">Operator</span><span className="text-green-300 font-semibold">{r.cleared_by}</span></div>
                                  <div className="flex justify-between"><span className="text-slate-500">Time</span><span className="text-slate-200 font-mono">{fmt(r.cleared_at)}</span></div>
                                  <div className="flex justify-between"><span className="text-slate-500">Duration</span><span className="text-slate-300 font-mono">{fmtDuration(r.duration_minutes)}</span></div>
                                  {r.clear_reason && <div className="flex justify-between"><span className="text-slate-500">Reason</span><span className="text-slate-300">{r.clear_reason}</span></div>}
                                  {r.clear_notes && <div className="mt-1 pt-1 border-t border-slate-700"><span className="text-slate-500">Notes: </span><span className="text-slate-300">{r.clear_notes}</span></div>}
                                </div>
                              ) : (
                                <p className="text-slate-600 italic text-xs">Alarm still active / not cleared</p>
                              )}
                            </div>

                            {/* Suppression details — only shown when suppressed */}
                            {r.suppressed_by && (
                              <div className="rounded-lg border p-3 bg-purple-950/40 border-purple-700/40 col-span-full">
                                <div className="flex items-center gap-2 mb-2">
                                  <span className="text-purple-400 font-bold text-sm">⊘</span>
                                  <span className="text-purple-400 font-bold text-xs uppercase">Suppression Active</span>
                                </div>
                                <div className="space-y-1 text-xs">
                                  <div className="flex justify-between"><span className="text-slate-500">Suppressed By</span><span className="text-purple-300 font-semibold">{r.suppressed_by}</span></div>
                                  <div className="flex justify-between"><span className="text-slate-500">Suppressed At</span><span className="text-slate-200 font-mono">{fmt(r.suppressed_at)}</span></div>
                                  <div className="flex justify-between"><span className="text-slate-500">Active Until</span><span className="text-slate-200 font-mono">{r.suppress_until ? fmt(r.suppress_until) : "Indefinite"}</span></div>
                                </div>
                              </div>
                            )}

                          </div>{/* end grid */}
                        </td>
                      </tr>
                    )
                  ];
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* ── Pagination ──────────────────────────────────────────────── */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700 bg-slate-800/60 rounded-b-xl flex-shrink-0">
            <span className="text-xs text-slate-400">
              Showing {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount.toLocaleString()}
            </span>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(1)} disabled={page === 1}
                className="px-2 py-1 rounded text-xs bg-slate-700/60 border border-slate-600 text-slate-300 disabled:opacity-30 hover:bg-slate-600 transition-colors">«</button>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="px-2 py-1 rounded text-xs bg-slate-700/60 border border-slate-600 text-slate-300 disabled:opacity-30 hover:bg-slate-600 transition-colors">
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              {/* Page numbers */}
              {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
                let p: number;
                if (totalPages <= 7) p = i + 1;
                else if (page <= 4) p = i + 1;
                else if (page >= totalPages - 3) p = totalPages - 6 + i;
                else p = page - 3 + i;
                return (
                  <button key={p} onClick={() => setPage(p)}
                    className={cn("px-2.5 py-1 rounded text-xs border transition-colors",
                      page === p ? "bg-blue-600 border-blue-500 text-white font-bold" : "bg-slate-700/60 border-slate-600 text-slate-300 hover:bg-slate-600"
                    )}>{p}</button>
                );
              })}
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                className="px-2 py-1 rounded text-xs bg-slate-700/60 border border-slate-600 text-slate-300 disabled:opacity-30 hover:bg-slate-600 transition-colors">
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
              <button onClick={() => setPage(totalPages)} disabled={page === totalPages}
                className="px-2 py-1 rounded text-xs bg-slate-700/60 border border-slate-600 text-slate-300 disabled:opacity-30 hover:bg-slate-600 transition-colors">»</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
