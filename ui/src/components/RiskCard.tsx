export default function RiskCard({
  title,
  prob,
  confidenceInterval,
  hoursToCritical,
  source,
  extra,
}: {
  title: string;
  prob: number;
  confidenceInterval: [number, number];
  hoursToCritical: number | null;
  source?: "observed" | "forecast";
  extra?: string;
}) {
  const level = prob >= 0.7 ? "위험" : prob >= 0.4 ? "주의" : "정상";
  const color =
    level === "위험"
      ? "text-red-300 bg-red-950/40 border-red-800/50"
      : level === "주의"
        ? "text-amber-300 bg-amber-950/40 border-amber-800/50"
        : "text-slate-300 bg-slate-900 border-slate-800";

  return (
    <div className={`rounded-xl border p-4 ${color}`}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{title}</p>
        <span className="rounded-full border border-current/40 px-2 py-0.5 text-xs">{level}</span>
      </div>
      <p className="mt-2 text-2xl font-bold">{(prob * 100).toFixed(0)}%</p>
      <p className="text-xs opacity-70">
        신뢰구간 [{(confidenceInterval[0] * 100).toFixed(0)}%, {(confidenceInterval[1] * 100).toFixed(0)}%]
        {source && ` · ${source === "observed" ? "실측" : "예보"}`}
      </p>
      {hoursToCritical !== null && (
        <p className="mt-1 text-xs opacity-80">임계치까지 {hoursToCritical.toFixed(1)}시간</p>
      )}
      {extra && <p className="mt-1 text-xs opacity-70">{extra}</p>}
    </div>
  );
}
