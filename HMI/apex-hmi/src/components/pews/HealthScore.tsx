/** HealthScore — circular gauge widget showing 0–100 system health */
interface Props { score: number }

const COLOR = (s: number) =>
  s >= 80 ? "text-emerald-400" : s >= 60 ? "text-yellow-400" : s >= 40 ? "text-orange-400" : "text-red-500";

const LABEL = (s: number) =>
  s >= 80 ? "HEALTHY" : s >= 60 ? "CAUTION" : s >= 40 ? "WARNING" : "CRITICAL";

export default function HealthScore({ score }: Props) {
  const r = 30, circ = 2 * Math.PI * r;
  const fill = circ * (score / 100);
  return (
    <div className="flex items-center gap-3">
      <svg width="80" height="80" className="-rotate-90">
        <circle cx="40" cy="40" r={r} strokeWidth="6" fill="none" className="stroke-gray-700" />
        <circle
          cx="40" cy="40" r={r} strokeWidth="6" fill="none"
          strokeDasharray={`${fill} ${circ}`}
          strokeLinecap="round"
          className={`transition-all duration-700 ${
            score >= 80 ? "stroke-emerald-400"
            : score >= 60 ? "stroke-yellow-400"
            : score >= 40 ? "stroke-orange-400"
            : "stroke-red-500"
          }`}
        />
      </svg>
      <div className="-ml-14 mt-1 flex flex-col items-center w-20">
        <span className={`text-xl font-bold leading-none ${COLOR(score)}`}>{score}</span>
        <span className={`text-[9px] font-semibold tracking-widest ${COLOR(score)}`}>{LABEL(score)}</span>
      </div>
    </div>
  );
}
