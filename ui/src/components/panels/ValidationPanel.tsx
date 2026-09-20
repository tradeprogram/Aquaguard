"use client";

import ProvenanceBadge from "@/components/ProvenanceBadge";

// Module V(검증 엔진, 신규 2026-08-29) — ARCHITECTURE.md §5 Module V, §15.
// 심층 경쟁기술 리서치가 "가장 강한 장면"으로 지목한 화면: 왼쪽 예측/오른쪽 관측을
// 자동으로 겹쳐 IoU·F1을 보여주는 것 자체가 조사된 어떤 경쟁 시스템에도 일반화돼
// 있지 않다.
//
// 2026-09-20 갱신: **목업 제거 완료.** 아래 값은 module_v_validation/data/
// module_v_example.json 의 실제 산출값(2025.7.19 산청 SFINCS 예측 vs Sentinel-1 SAR)이다.
// (교체 전 목업: IoU 0.58 / F1 0.71 / precision 0.74 / recall 0.69 / lead 195분 —
//  실제값은 0.32 / 0.485 / 0.482 / 0.488 / 217분 이다.)
//
// lead_time_min 은 SAR 촬영시각(12:37) 기준이며 실제 붕괴·범람 시각 기준이 아니다.
// 이 둘을 섞으면 안 된다 — backtest_sancheong/README.md §1 참조.
const RESULT = {
  alertId: "AL-20250719-0900",
  observedSource: "Copernicus Sentinel-1",
  acquisitionTimestamp: "2025-07-19T12:37:00+09:00",
  iou: 0.32,
  f1: 0.485,
  precision: 0.482,
  recall: 0.488,
  leadTimeMin: 217,
  predictedFeatures: "SFINCS 침수 1 features",
  observedFeatures: "SAR 홍수(5179 재투영) 420 features",
};

// 같은 Module V 파이프라인을 산사태에 돌린 결과. 홍수보다 두 자릿수 나쁘다 —
// 숨기면 검증 엔진이 만능처럼 보이므로 함께 띄운다.
const LANDSLIDE_RESULT = {
  iou: 0.0038,
  f1: 0.0076,
  auprc: 0.0106,
  baseRate: 0.0097,
};

function OverlapDiagram({ iou }: { iou: number }) {
  // iou가 높을수록 두 원의 중심 거리를 줄여 겹치는 면적을 시각적으로 늘린다 —
  // 수학적으로 정확한 IoU 역산은 아니고(실제 폴리곤은 5179 좌표로 따로 있다),
  // "겹침이 이 정도다"를 직관적으로 보여주기 위한 개략도.
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
  const h = Math.floor(RESULT.leadTimeMin / 60);
  const m = RESULT.leadTimeMin % 60;

  return (
    <div className="space-y-4 text-sm">
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
        Module V(검증 엔진) — 사건 이전 데이터만으로 재실행한 예측과, 사건 이후 Sentinel-1 관측을
        자동으로 겹쳐 공간 일치도를 계산한다. 아래는 2025.7.19 산청 실제 산출값이다.
        <ProvenanceBadge kind="OBSERVED" />
      </p>

      <div className="rounded-lg border border-dashed border-sky-800/40 bg-sky-950/10 p-3 text-[11px] leading-relaxed text-sky-300/80">
        <span className="font-semibold">IoU 0.32를 모형 성능으로 읽지 말 것.</span> 초목이 덮인
        계곡에서 Sentinel-1 후방산란이 침수를 과소탐지하는 센서 한계가 지배적이다. 이 사례의
        주검증 지표는 실측 수위 RMSE 1.42m와 SFINCS↔ANUGA 교차 IoU 0.775이며, SAR은 세 번째
        참값으로 삼각검증에만 쓴다. data leakage 금지(사건 이후 관측을 예측 입력에 섞지 않음,
        ARCHITECTURE.md §5 Module V)는 준수했다.
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-3">
        <OverlapDiagram iou={RESULT.iou} />
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
        <p className="mt-2 text-center text-[10px] leading-relaxed text-slate-500">
          지표를 직관적으로 보여주기 위한 개략도다(실제 폴리곤은 EPSG:5179 좌표로
          confusion_geometry_5179에 따로 있다). 예측 {RESULT.predictedFeatures} vs 관측{" "}
          {RESULT.observedFeatures}.
        </p>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <MetricCard label="IoU" value={RESULT.iou.toFixed(2)} />
        <MetricCard label="F1" value={RESULT.f1.toFixed(3)} />
        <MetricCard label="정밀도" value={`${(RESULT.precision * 100).toFixed(0)}`} unit="%" />
        <MetricCard label="재현율" value={`${(RESULT.recall * 100).toFixed(0)}`} unit="%" />
      </div>

      <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/30 p-4">
        <p className="flex items-center gap-1.5 text-xs text-emerald-300/80">
          경보시간(lead time) <ProvenanceBadge kind="OBSERVED" />
        </p>
        <p className="mt-1 text-2xl font-bold text-emerald-300">
          {h}시간 {m}분 먼저 감지
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-amber-300/70">
          ⚠ 기준은 <b>SAR 촬영시각 12:37</b>(= 공식 대피경보 시각)이다. <b>실제 범람·붕괴 시각이
          아니다.</b> 산사태 쪽에서 같은 기준으로 재보면 최초 신고(08:00) 대비로는 −1시간이 된다
          (backtest_sancheong/README.md §1). &ldquo;재해보다 3시간 37분 빨랐다&rdquo;로 옮기면 틀린
          주장이 된다.
        </p>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs">
        <p className="flex items-center gap-1.5 text-slate-400">
          관측 출처 <ProvenanceBadge kind="OBSERVED" />
        </p>
        <p className="mt-1 text-slate-200">{RESULT.observedSource}</p>
        <p className="text-[11px] text-slate-500">
          촬영시각 {new Date(RESULT.acquisitionTimestamp).toLocaleString("ko-KR")} · alert_id{" "}
          {RESULT.alertId}
        </p>
      </div>

      <div className="rounded-xl border border-amber-800/40 bg-amber-950/10 p-3 text-[11px] leading-relaxed text-amber-300/80">
        <span className="font-semibold">같은 엔진, 산사태에서는 훨씬 나쁘다.</span> SAR 변화탐지를
        산사태에 적용하면 IoU {LANDSLIDE_RESULT.iou} · F1 {LANDSLIDE_RESULT.f1} · AUPRC{" "}
        {LANDSLIDE_RESULT.auprc}(기저 {LANDSLIDE_RESULT.baseRate})로, 사실상 무기력하다. 강우 후
        토양수분·식생위상 변화가 섞여 노이즈가 크고, 산사태 발생부 참값 자체가 없다. Module V가
        만능이 아니라 <b>참값이 있는 홍수에서만 제 역할을 한다</b>는 뜻이다.
      </div>
    </div>
  );
}
