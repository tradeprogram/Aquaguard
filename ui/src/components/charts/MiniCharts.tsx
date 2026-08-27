// 가벼운 손그림 SVG 차트 — 이 프로젝트는 새 차트 라이브러리 없이 지도(MapLibre)만
// 의존성으로 두는 기조라(§1.5), 여기도 recharts 등을 새로 얹지 않고 순수 SVG로
// 직접 그린다. ModelPerformancePanel 전용이라 범용화하지 않고 딱 필요한 3종만.

export function TimeSeriesChart({
  points,
  eventMarkers = [],
  width = 520,
  height = 160,
  color = "#38bdf8",
}: {
  points: { t: number; value: number }[]; // t: 0~1 정규화된 시간축, value: 0~1 확률
  eventMarkers?: { t: number; label: string; color: string }[];
  width?: number;
  height?: number;
  color?: string;
}) {
  const pad = { top: 10, right: 10, bottom: 20, left: 28 };
  const w = width - pad.left - pad.right;
  const h = height - pad.top - pad.bottom;
  const x = (t: number) => pad.left + t * w;
  const y = (v: number) => pad.top + (1 - v) * h;
  const path = points.map((p) => `${x(p.t)},${y(p.value)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full">
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <line
          key={g}
          x1={pad.left}
          x2={width - pad.right}
          y1={y(g)}
          y2={y(g)}
          stroke="currentColor"
          className="text-white/10"
          strokeWidth={1}
        />
      ))}
      <text x={2} y={y(1) + 4} className="fill-slate-500 text-[9px]">
        100%
      </text>
      <text x={2} y={y(0) + 4} className="fill-slate-500 text-[9px]">
        0%
      </text>
      <polyline points={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
      {eventMarkers.map((m) => (
        <g key={m.label}>
          <line x1={x(m.t)} x2={x(m.t)} y1={pad.top} y2={height - pad.bottom} stroke={m.color} strokeDasharray="3,3" strokeWidth={1.5} />
          <text x={x(m.t)} y={height - 6} textAnchor="middle" className="text-[9px]" fill={m.color}>
            {m.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

export function RocCurve({ points, auc, width = 200, height = 200 }: { points: [number, number][]; auc: number; width?: number; height?: number }) {
  const pad = 20;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const x = (fpr: number) => pad + fpr * w;
  const y = (tpr: number) => pad + (1 - tpr) * h;
  const path = points.map(([fpr, tpr]) => `${x(fpr)},${y(tpr)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full">
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="currentColor" className="text-white/15" strokeDasharray="4,4" />
      <polyline points={path} fill="none" stroke="#a78bfa" strokeWidth={2} />
      <text x={width - pad} y={pad + 12} textAnchor="end" className="fill-violet-300 text-[11px] font-semibold">
        AUC {auc.toFixed(2)}
      </text>
      <text x={pad} y={height - 4} className="fill-slate-500 text-[9px]">
        FPR →
      </text>
      <text x={4} y={pad} className="fill-slate-500 text-[9px]">
        TPR
      </text>
    </svg>
  );
}

export function ConfusionMatrix({ tp, fp, fn, tn }: { tp: number; fp: number; fn: number; tn: number }) {
  const cells = [
    { label: "TP", value: tp, tone: "bg-emerald-900/50 text-emerald-300" },
    { label: "FP", value: fp, tone: "bg-red-900/40 text-red-300" },
    { label: "FN", value: fn, tone: "bg-red-900/40 text-red-300" },
    { label: "TN", value: tn, tone: "bg-emerald-900/50 text-emerald-300" },
  ];
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {cells.map((c) => (
        <div key={c.label} className={`rounded-lg p-2 text-center ${c.tone}`}>
          <p className="text-[10px] opacity-70">{c.label}</p>
          <p className="text-base font-bold">{c.value}</p>
        </div>
      ))}
    </div>
  );
}
