"use client";

import { useState } from "react";
import { ConfusionMatrix, RocCurve, TimeSeriesChart } from "@/components/charts/MiniCharts";
import ProvenanceBadge from "@/components/ProvenanceBadge";

// 사용자 요청(2026-08-27): "ML 기반으로 돌리는거면 그래프부터 포함해서 과학적으로
// 성능을 입증하고 결과를 입증할 수 있는 시각자료나 지표가 모두 떠있는게 더 좋을수도
// 있어." — 지금까지 대시보드는 확률 % + 신뢰구간 텍스트뿐이었는데, 실제 ML 모델이면
// 응당 나와야 할 검증 지표(AUC/ROC, 정밀도·재현율, 혼동행렬)와 사례별 시계열 예측
// 곡선을 보여주는 전용 패널. **트랙①(민석)의 Module A/B가 아직 실제로 학습되기
// 전이라 아래 숫자·곡선은 전부 목업이다** — 실제 모델이 나오면 이 화면 그대로
// 검증 결과값만 갈아끼우면 된다. 산청(산사태)·서울(하천범람·침수) 두 사례 기준.
type HazardKey = "landslide" | "flood";

interface HazardCase {
  title: string;
  caseLabel: string;
  color: string;
  auc: number;
  precision: number;
  recall: number;
  f1: number;
  roc: [number, number][];
  confusion: { tp: number; fp: number; fn: number; tn: number };
  series: { t: number; value: number }[];
  markers: { t: number; label: string; color: string }[];
}

const CASES: Record<HazardKey, HazardCase> = {
  landslide: {
    title: "산사태 (Module A)",
    caseLabel: "2025.7.19 산청 산사태 — 06:00~13:00 예측확률 추이",
    color: "#f87171",
    auc: 0.91,
    precision: 0.86,
    recall: 0.79,
    f1: 0.82,
    roc: [
      [0, 0],
      [0.05, 0.35],
      [0.15, 0.6],
      [0.3, 0.78],
      [0.5, 0.88],
      [0.7, 0.94],
      [1, 1],
    ],
    confusion: { tp: 34, fp: 6, fn: 9, tn: 151 },
    series: [
      { t: 0, value: 0.12 },
      { t: 0.14, value: 0.18 },
      { t: 0.29, value: 0.31 },
      { t: 0.36, value: 0.44 },
      { t: 0.43, value: 0.58 },
      { t: 0.46, value: 0.71 },
      { t: 0.57, value: 0.75 },
      { t: 0.71, value: 0.79 },
      { t: 0.85, value: 0.81 },
      { t: 1, value: 0.85 },
    ],
    markers: [
      { t: 0.464, label: "에이전트 탐지 09:15", color: "#38bdf8" },
      { t: 0.945, label: "실제 경보 12:37", color: "#fbbf24" },
    ],
  },
  flood: {
    title: "하천범람·침수 (Module B)",
    caseLabel: "2022.8.8 서울 폭우 — 18:00~23:00 예측확률 추이",
    color: "#38bdf8",
    auc: 0.89,
    precision: 0.81,
    recall: 0.88,
    f1: 0.84,
    roc: [
      [0, 0],
      [0.08, 0.4],
      [0.2, 0.65],
      [0.35, 0.8],
      [0.55, 0.9],
      [0.75, 0.95],
      [1, 1],
    ],
    confusion: { tp: 41, fp: 11, fn: 6, tn: 142 },
    series: [
      { t: 0, value: 0.2 },
      { t: 0.2, value: 0.28 },
      { t: 0.4, value: 0.39 },
      { t: 0.55, value: 0.52 },
      { t: 0.63, value: 0.7 },
      { t: 0.68, value: 0.93 },
      { t: 0.8, value: 0.9 },
      { t: 1, value: 0.84 },
    ],
    markers: [{ t: 0.68, label: "관측 강수강도 급증 21:00", color: "#fbbf24" }],
  },
};

export default function ModelPerformancePanel() {
  const [hazard, setHazard] = useState<HazardKey>("landslide");
  const c = CASES[hazard];

  return (
    <div className="space-y-4 text-sm">
      <p className="flex items-center gap-1.5 text-xs text-slate-400">
        Module A/B의 예측 성능을 실제 검증 지표(AUC/ROC, 정밀도·재현율, 혼동행렬)와 사례별 시계열
        예측 곡선으로 보여준다. 산사태는 산청, 하천범람·침수는 서울 사례 기준. <ProvenanceBadge kind="MODEL" />
      </p>

      <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
        목업 — 트랙①(Module A/B)이 아직 실제로 학습되기 전이라 아래 지표·곡선은 전부 예시값이다.
        실제 모델이 나오면 이 화면 그대로 검증 결과값만 교체하면 된다.
      </div>

      <div className="flex gap-1.5 rounded-lg border border-white/10 bg-white/5 p-1">
        {(Object.keys(CASES) as HazardKey[]).map((k) => (
          <button
            key={k}
            onClick={() => setHazard(k)}
            className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              hazard === k ? "bg-sky-500/60 text-white" : "text-slate-300 hover:bg-white/10"
            }`}
          >
            {CASES[k].title}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-4 gap-2">
        {[
          { label: "AUC", value: c.auc.toFixed(2) },
          { label: "정밀도", value: `${(c.precision * 100).toFixed(0)}%` },
          { label: "재현율", value: `${(c.recall * 100).toFixed(0)}%` },
          { label: "F1", value: c.f1.toFixed(2) },
        ].map((s) => (
          <div key={s.label} className="rounded-lg border border-white/10 bg-white/5 p-2 text-center">
            <p className="text-[10px] text-slate-400">{s.label}</p>
            <p className="text-lg font-bold text-slate-100">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-3">
        <p className="mb-1 text-xs text-slate-400">{c.caseLabel}</p>
        <TimeSeriesChart points={c.series} eventMarkers={c.markers} color={c.color} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="mb-1 text-xs text-slate-400">ROC 곡선</p>
          <RocCurve points={c.roc} auc={c.auc} />
        </div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="mb-2 text-xs text-slate-400">혼동행렬 (임계치 0.7 기준)</p>
          <ConfusionMatrix {...c.confusion} />
        </div>
      </div>
    </div>
  );
}
