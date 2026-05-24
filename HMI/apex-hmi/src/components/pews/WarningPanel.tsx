/** WarningPanel — scrollable list of active PEWS warnings with ack button */
import type { PewsWarning } from "@/pages/Analytics";

const LEVEL_META: Record<number, { label: string; border: string; badge: string }> = {
  4: { label: "ALERT",   border: "border-red-600",    badge: "bg-red-600 text-white" },
  3: { label: "WARNING", border: "border-orange-500", badge: "bg-orange-500 text-white" },
  2: { label: "CAUTION", border: "border-yellow-500", badge: "bg-yellow-500 text-black" },
  1: { label: "INFO",    border: "border-blue-500",   badge: "bg-blue-500 text-white" },
};

interface Props {
  warnings: PewsWarning[];
  onAck: (id: number) => void;
}

export default function WarningPanel({ warnings, onAck }: Props) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-gray-200">
          Active Warnings
          {warnings.length > 0 && (
            <span className="ml-2 px-2 py-0.5 text-xs bg-red-700 text-white rounded-full">
              {warnings.length}
            </span>
          )}
        </h2>
      </div>

      {warnings.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-gray-600">
          <span className="text-4xl mb-2">✓</span>
          <span className="text-sm">No active warnings</span>
        </div>
      ) : (
        <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
          {warnings.map(w => {
            const meta = LEVEL_META[w.warning_level] ?? LEVEL_META[1];
            return (
              <div
                key={w.id}
                className={`p-3 bg-gray-900 rounded-lg border-l-4 ${meta.border} hover:bg-gray-800 transition`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    {/* Tag + level badge */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${meta.badge}`}>
                        {meta.label}
                      </span>
                      <span className="text-xs font-mono text-gray-300 truncate">{w.tag_id}</span>
                      <span className="text-[10px] text-gray-500">{w.warning_type}</span>
                    </div>

                    {/* Message */}
                    <p className="text-sm text-gray-200 mt-1 leading-snug">{w.message}</p>

                    {/* Values row */}
                    <div className="flex gap-4 mt-1.5 text-xs text-gray-400 flex-wrap">
                      {w.current_value != null && (
                        <span>Current: <span className="text-white font-mono">{w.current_value.toFixed(3)}</span></span>
                      )}
                      {w.avg_value != null && (
                        <span>Avg: <span className="text-gray-300 font-mono">{w.avg_value.toFixed(3)}</span></span>
                      )}
                      {w.deviation_pct != null && (
                        <span>Deviation: <span className="text-orange-300 font-mono">{w.deviation_pct.toFixed(1)}%</span></span>
                      )}
                      <span className="text-gray-600">{new Date(w.time).toLocaleTimeString()}</span>
                    </div>
                  </div>

                  {/* Ack button */}
                  <button
                    onClick={() => onAck(w.id)}
                    className="shrink-0 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition"
                    title="Acknowledge"
                  >
                    ACK
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
