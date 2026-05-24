/** StatusSummary — baseline coverage + per-level warning counts */
import type { PewsStatus } from "@/pages/Analytics";

const LEVEL_META: Record<number, { label: string; color: string; bg: string }> = {
  4: { label: "ALERT",   color: "text-red-400",    bg: "bg-red-900/30 border-red-700" },
  3: { label: "WARNING", color: "text-orange-400", bg: "bg-orange-900/30 border-orange-700" },
  2: { label: "CAUTION", color: "text-yellow-400", bg: "bg-yellow-900/30 border-yellow-700" },
  1: { label: "INFO",    color: "text-blue-400",   bg: "bg-blue-900/30 border-blue-700" },
};

interface Props { status: PewsStatus | null }

export default function StatusSummary({ status }: Props) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-200">System Status</h2>

      {/* Baseline coverage */}
      <div className="p-4 bg-gray-900 border border-gray-700 rounded-lg">
        <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Baseline Coverage</div>
        <div className="text-2xl font-bold text-white">{status?.baseline_count ?? "—"} tags</div>
        {status?.newest_baseline && (
          <div className="text-xs text-gray-500 mt-1">
            Last computed: {new Date(status.newest_baseline).toLocaleString()}
          </div>
        )}
      </div>

      {/* Per-level counts */}
      <div className="space-y-2">
        <div className="text-xs text-gray-400 uppercase tracking-wider">Active Warnings</div>
        {[4, 3, 2, 1].map(lvl => {
          const cnt = status?.warning_summary[String(lvl)] ?? 0;
          const meta = LEVEL_META[lvl];
          return (
            <div key={lvl} className={`flex items-center justify-between px-3 py-2 rounded border ${meta.bg}`}>
              <span className={`text-xs font-bold tracking-wider ${meta.color}`}>{meta.label}</span>
              <span className={`text-lg font-bold ${meta.color}`}>{cnt}</span>
            </div>
          );
        })}
        <div className="flex items-center justify-between px-3 py-2 rounded border bg-gray-800 border-gray-600">
          <span className="text-xs font-bold tracking-wider text-gray-300">TOTAL</span>
          <span className="text-lg font-bold text-white">{status?.total_active_warnings ?? 0}</span>
        </div>
      </div>
    </div>
  );
}
