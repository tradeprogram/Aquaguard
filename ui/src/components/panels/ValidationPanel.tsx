"use client";

import ProvenanceBadge from "@/components/ProvenanceBadge";

// Module V(검증 엔진, 신규 2026-08-29) — ARCHITECTURE.md §5 Module V, §15.
// 심층 경쟁기술 리서치가 "가장 강한 장면"으로 지목한 화면: 왼쪽 예측/오른쪽 관측을
// 자동으로 겹쳐 IoU·F1을 보여주는 것 자체가 조사된 어떤 경쟁 시스템에도 일반화돼
// 있지 않다. 3D는 메인 지도로 유지하고(사용자 결정, 2026-08-29), 이 화면만 별도
// 2D 오버레이 패널로 둔다 — 검증은 정밀한 3D 렌더링보다 "한눈에 겹쳐 보이는 것"이
// 더 중요하고, 트랙①이 아직 실제 폴리곤을 안 줬으니 지금은 MapLibre 좌표에 얹을
// 실좌표 자체가 없다(그래서 아래 원은 실제 geometry가 아니라 지표를 시각화한 개략도).
//
// 트랙① 소유(module_v_validation) — contracts/module_v.example.json을 그대로 목업으로
// 사용. 실제 모델이 나오면 이 컴포넌트는 그대로 두고 MOCK 상수만 실제 fetch 결과로
// 교체하면 된다(ModelPerformancePanel과 동일한 패턴).
const MOCK = {
  alertId: "AL-20250719-0915",
  observedSource: "Copernicus Sentinel-1",
  acquisitionTimestamp: "2025-07-20T01:32:00+09:00",
  iou: 0.58,
  f1: 0.71,
  precision: 0.74,
  recall: 0.69,
  leadTimeMin: 195,
};

function OverlapDiagram({ iou }: { iou: number }) {
  // iou가 높을수록 두 원의 중심 거리를 줄여 겹치는 면적을 시각적으로 늘린다 —
  // 수학적으로 정확한 IoU 역산은 아니고(실제 폴리곤이 없어 계산할 대상 자체가
  // 없음), "겹침이 이 정도다"를 직관적으로 보여주기 위한 개략도.
  const r = 78;
  const maxOffset = r * 1.7;
  const minOffset = r * 0.35;
  const offset = maxOffset - iou * (maxOffset - minOffset);
  const cxPred = 200 - offset / 2;
  const cxObs = 200 + offset / 2;
  const cy = 110;

  return (
    <svg viewBox="0 0 400 220" className="w-full">
      <defs>
        <clipPath id="val-clip-predicted">
          <circle cx={cxPred} cy={cy} r={r} />
        </clipPath>
      </defs>
      {/* FP: 예측했지만 실제로는 없었던 영역 */}
      <circle cx={cxPred} cy={cy} r={r} fill="#ef4444" fillOpacity={0.55} />
      {/* FN: 실제로 발생했지만 예측 못한 영역 */}
      <circle cx={cxObs} cy={cy} r={r} fill="#3b82f6" fillOpacity={0.55} />
      {/* TP: 관측 원을 예측 원 모양으로 잘라낸 교집합 — 두 원의 실제 겹침 그 자체 */}
      <circle cx={cxObs} cy={cy} r={r} fill="#10b981" fillOpacity={0.9} clipPath="url(#val-clip-predicted)" />

      <text x={20} y={26} className="fill-red-200 text-[13px] font-semibold">
        예측(MODEL)
      </text>
      <text x={380} y={26} className="fill-blue-200 text-[13px] font-semibold" textAnchor="end">
        관측(OBSERVED)
      </text>
    </svg>
  );
}

function MetricCard({ label, value, unit = "" }: { label: string; value: string; unit?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-2 text-center">
      <p className="text-[10px] text-slate-400">{label}</p>
      <p className="text-lg font-bold text-slate-100">
        {value}
        {unit && <span className="text-xs font-normal text-slate-400">{unit}</span>}
      </p>
    </div>
  );
}

export default function ValidationPanel() {
  return (
    <div className="space-y-4 text-sm">
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
        Module V(검증 엔진, 신규) — 사건 이전 데이터만으로 재실행한 예측과, 사건 이후 Sentinel-1/실측
        관측을 자동으로 겹쳐 공간 일치도를 계산한다.
        <ProvenanceBadge kind="MODEL" />
      </p>

      <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
        목업 — 트랙①(Module V)이 아직 실제 Sentinel-1 비교를 붙이기 전이라 아래 지표·도형은
        contracts/module_v.example.json 예시값이다. data leakage 금지 원칙(사건 이후 관측 레이어를
        예측 입력에 절대 섞지 않음, ARCHITECTURE.md §5 Module V)은 실제 연동 후에도 그대로 지켜야 한다.
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-3">
        <OverlapDiagram iou={MOCK.iou} />
        <div className="mt-2 flex items-center justify-center gap-4 text-[10px] text-slate-400">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-red-500/70" /> FP(오탐)
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500/90" /> TP(적중)
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-blue-500/70" /> FN(미탐)
          </span>
        </div>
        <p className="mt-2 text-center text-[10px] text-slate-500">
          실제 폴리곤이 아니라 아래 지표를 직관적으로 보여주기 위한 개략도 — 트랙①의 실제 geometry가
          들어오면 이 자리에 5179 좌표 기반 실제 폴리곤 오버레이로 교체된다.
        </p>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <MetricCard label="IoU" value={MOCK.iou.toFixed(2)} />
        <MetricCard label="F1" value={MOCK.f1.toFixed(2)} />
        <MetricCard label="정밀도" value={`${(MOCK.precision * 100).toFixed(0)}`} unit="%" />
        <MetricCard label="재현율" value={`${(MOCK.recall * 100).toFixed(0)}`} unit="%" />
      </div>

      <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/30 p-4">
        <p className="flex items-center gap-1.5 text-xs text-emerald-300/80">
          경보시간(lead time) <ProvenanceBadge kind="MODEL" />
        </p>
        <p className="mt-1 text-2xl font-bold text-emerald-300">
          {Math.floor(MOCK.leadTimeMin / 60)}시간 {MOCK.leadTimeMin % 60}분 먼저 감지
        </p>
        <p className="mt-1 text-xs text-slate-400">
          예측이 임계치를 넘은 시각과 실제 관측/사건 시각의 차이 — &ldquo;언제 위험을 감지했는가&rdquo;
        </p>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs">
        <p className="flex items-center gap-1.5 text-slate-400">
          관측 출처 <ProvenanceBadge kind="OBSERVED" />
        </p>
        <p className="mt-1 text-slate-200">{MOCK.observedSource}</p>
        <p className="text-[11px] text-slate-500">
          촬영시각 {new Date(MOCK.acquisitionTimestamp).toLocaleString("ko-KR")} · alert_id {MOCK.alertId}
        </p>
      </div>
    </div>
  );
}
