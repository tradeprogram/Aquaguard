"use client";

import { useState } from "react";
import { ConfusionMatrix, RocCurve, TimeSeriesChart } from "@/components/charts/MiniCharts";
import ProvenanceBadge from "@/components/ProvenanceBadge";

// 사용자 요청(2026-08-27): "ML 기반으로 돌리는거면 그래프부터 포함해서 과학적으로
// 성능을 입증하고 결과를 입증할 수 있는 시각자료나 지표가 모두 떠있는게 더 좋을수도
// 있어."
//
// 2026-09-20 갱신: **목업 제거 완료.** 아래 숫자는 전부 트랙① 백테스트 실측값이며
// backtest_sancheong/outputs/model_performance_panel.json 에서 그대로 옮겼다.
// (교체 전 목업: 산사태 AUC 0.91 / precision 0.86 / confusion 34·6·9·151 —
//  실제값은 각각 0.469 / 0.068 / 32·436·22·348 이다. 목업을 발표에 쓰면 성능 조작이다.)
//
// 산사태 지표가 낮은 이유는 backtest_sancheong/README.md §3·§4가 규명했다:
// 참값이 '발생부 좌표'가 아니라 '피해 집계 마을(리) 중심점'이라 급사면 물리와
// 계통적으로 어긋난다. 모형 오차와 참값 부적합이 섞여 있고 분리할 수 없다.
// 낮은 값을 숨기지 않되 물리 반증으로도 읽히지 않게, caveat를 항상 함께 띄운다.
type HazardKey = "landslide" | "flood";

interface Metric {
  label: string;
  value: string;
  sub?: string;
}

interface HazardCase {
  title: string;
  caseLabel: string;
  color: string;
  /** 지표 타일. 사례마다 의미있는 지표가 달라서 고정 4종이 아니라 목록으로 둔다. */
  metrics: Metric[];
  /** 산출된 경우만. 홍수는 연속 점수가 없어 ROC를 내지 않았다. */
  auc: number | null;
  roc: [number, number][] | null;
  /** 평가역이 침수가능역으로 한정돼 TN이 정의되지 않으면 null. */
  confusion: { tp: number; fp: number; fn: number; tn: number | null };
  confusionNote: string;
  series: { t: number; value: number }[];
  markers: { t: number; label: string; color: string }[];
  seriesNote: string;
  /** 숫자만 떼어 쓰는 걸 막는 문구. 항상 지표보다 먼저 보이게 둔다. */
  caveat: string;
  findings: { label: string; value: string }[];
}

const CASES: Record<HazardKey, HazardCase> = {
  landslide: {
    title: "산사태 (Module A)",
    caseLabel: "2025.7.19 산청 — 06:00~13:00 위험사면 임계초과율(실측 강우 구동)",
    color: "#f87171",
    metrics: [
      { label: "ROC-AUC", value: "0.47", sub: "무작위 0.50" },
      { label: "AUPRC", value: "0.061", sub: "기저 0.064" },
      { label: "정밀도", value: "7%", sub: "재현율 59%" },
      { label: "F1", value: "0.12", sub: "F1 최대 운영점" },
    ],
    auc: 0.4686,
    roc: [
      [0.0, 0.0],
      [0.0523, 0.037],
      [0.1161, 0.0926],
      [0.2003, 0.1667],
      [0.273, 0.2037],
      [0.3406, 0.2593],
      [0.3712, 0.3148],
      [0.3839, 0.3704],
      [0.4503, 0.4444],
      [0.4987, 0.5],
      [0.5293, 0.5556],
      [1.0, 1.0],
    ],
    confusion: { tp: 32, fp: 436, fn: 22, tn: 348 },
    confusionNote:
      "1km 격자 838개 · F1 최대 운영점. 물리점수는 확률이 아니라 순위점수라 0.7 고정컷이 무의미하다.",
    series: [
      { t: 0.0, value: 0.0727 },
      { t: 0.1429, value: 0.1149 },
      { t: 0.2857, value: 0.2766 },
      { t: 0.4286, value: 1.0 },
      { t: 0.5714, value: 1.0 },
      { t: 0.7143, value: 1.0 },
      { t: 0.8571, value: 1.0 },
      { t: 1.0, value: 1.0 },
    ],
    markers: [
      { t: 0.2857, label: "최초 신고 08:00", color: "#f472b6" },
      { t: 0.4286, label: "T_agent 09:00", color: "#38bdf8" },
      { t: 0.9381, label: "공식 경보 12:37", color: "#fbbf24" },
    ],
    seriesNote:
      "피크 대비 정규화(피크 = 임계초과율 0.90%). 09:00에 포화 — 공식 경보(12:37)보다 3.62h 이르지만 최초 신고(08:00)보다는 1h 늦다.",
    caveat:
      "참값이 산사태 '발생부 좌표'가 아니라 '피해 집계 마을(리) 중심점'이다. 피해는 계곡·거주지에, 발생부는 급사면에 있어 계통적으로 어긋난다. 이 지표에는 모형 오차와 참값 부적합이 섞여 있고 분리할 수 없다 — 낮은 값이 물리 반증은 아니며, 높은 성능의 근거로도 쓸 수 없다.",
    findings: [
      { label: "골든타임 (공식경보 대비)", value: "+3.62 h" },
      { label: "골든타임 (최초신고 대비)", value: "−1.00 h (상한)" },
      { label: "산불 기여 (ablation)", value: "peak 1.88배 · 문턱 0.05%에서 8h 앞당김" },
      { label: "공간분할 (읍면 LOO)", value: "AUPRC 중앙값 0.072 · 9곳 중 6곳 lift>1" },
      { label: "ML 보정", value: "평가 후 기각 (p=0.074) — 물리단독 유지" },
    ],
  },
  flood: {
    title: "하천범람·침수 (Module B)",
    caseLabel: "2025.7.19 산청 경호강 — SFINCS 물리모형 (수위계·SAR·HAND 3중 검증)",
    color: "#38bdf8",
    metrics: [
      { label: "수위 RMSE", value: "1.42 m", sub: "경호교 관측 대비" },
      { label: "피크 오차", value: "−0.80 m", sub: "94.12 → 93.31 m" },
      { label: "2엔진 IoU", value: "0.775", sub: "SFINCS↔ANUGA" },
      { label: "런타임", value: "43 초", sub: "2.5일 시뮬" },
    ],
    auc: null,
    roc: null,
    confusion: { tp: 1527, fp: 1903, fn: 772, tn: null },
    confusionNote:
      "SFINCS 침수범위 vs Sentinel-1 SAR (공통 50m 격자, HAND<15m 계곡). 평가역이 침수가능역으로 한정돼 TN은 정의되지 않는다.",
    series: [],
    markers: [],
    seriesNote: "",
    caveat:
      "vs SAR IoU 0.363은 모형 오차가 아니라 초목이 덮인 계곡에서 SAR 후방산란이 침수를 못 잡는 센서 한계다(HAND-FIM·2엔진 교차 삼중검증으로 규명). 이 사례의 주검증 지표는 SAR IoU가 아니라 실측 수위 RMSE 1.42m와 2엔진 교차 IoU 0.775다.",
    findings: [
      { label: "vs SAR", value: "IoU 0.363 · F1 0.533 · POD 0.664 · precision 0.445" },
      { label: "vs HAND-FIM", value: "IoU 0.269 · precision 0.930 (FAR 0.07)" },
      { label: "SFINCS ↔ ANUGA", value: "IoU 0.775 · F1 0.873 · precision 0.963" },
      { label: "엔진 비교 (수위 RMSE)", value: "SFINCS 1.42 m vs ANUGA 2.48 m" },
      { label: "침수면적", value: "SFINCS 9.33 · SAR 6.8 · HAND-FIM 31.6 km²" },
    ],
  },
};

export default function ModelPerformancePanel() {
  const [hazard, setHazard] = useState<HazardKey>("landslide");
  const c = CASES[hazard];

  return (
    <div className="space-y-4 text-sm">
      <p className="flex items-center gap-1.5 text-xs text-slate-400">
        Module A/B의 예측 성능을 실제 검증 지표와 사례별 시계열로 보여준다. 둘 다 2025.7 산청 사례
        기준이며, 지표는 실측 참값 대비 백테스트 산출값이다(곡선 자체는 모델 출력).{" "}
        <ProvenanceBadge kind="OBSERVED" />
      </p>

      <div className="rounded-lg border border-dashed border-sky-800/40 bg-sky-950/10 p-3 text-[11px] leading-relaxed text-sky-300/80">
        <span className="font-semibold">참값 한계 — 숫자보다 먼저 읽을 것.</span> {c.caveat}
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
        {c.metrics.map((s) => (
          <div key={s.label} className="rounded-lg border border-white/10 bg-white/5 p-2 text-center">
            <p className="text-[10px] text-slate-400">{s.label}</p>
            <p className="text-lg font-bold text-slate-100">{s.value}</p>
            {s.sub && <p className="text-[9px] text-slate-500">{s.sub}</p>}
          </div>
        ))}
      </div>

      {c.series.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="mb-1 text-xs text-slate-400">{c.caseLabel}</p>
          <TimeSeriesChart points={c.series} eventMarkers={c.markers} color={c.color} />
          <p className="mt-1.5 text-[10px] leading-relaxed text-slate-500">{c.seriesNote}</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="mb-1 text-xs text-slate-400">ROC 곡선</p>
          {c.roc && c.auc !== null ? (
            <RocCurve points={c.roc} auc={c.auc} />
          ) : (
            <p className="py-8 text-center text-[11px] leading-relaxed text-slate-500">
              산출 안 됨
              <br />
              <span className="text-slate-600">
                침수범위는 연속 점수가 아니라 폴리곤이라 ROC가 정의되지 않는다. 대신 실측 수위
                RMSE와 2엔진 교차 IoU로 검증한다.
              </span>
            </p>
          )}
        </div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="mb-2 text-xs text-slate-400">혼동행렬</p>
          <ConfusionMatrix {...c.confusion} />
          <p className="mt-1.5 text-[10px] leading-relaxed text-slate-500">{c.confusionNote}</p>
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-3">
        <p className="mb-2 text-xs text-slate-400">검증 상세</p>
        <dl className="space-y-1.5">
          {c.findings.map((f) => (
            <div key={f.label} className="flex items-start justify-between gap-3 text-[11px]">
              <dt className="shrink-0 text-slate-400">{f.label}</dt>
              <dd className="text-right font-mono text-slate-200">{f.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <p className="text-[10px] leading-relaxed text-slate-500">
        출처 <span className="font-mono">backtest_sancheong/outputs/model_performance_panel.json</span> ·
        산출 <span className="font-mono">44_model_performance_panel.py</span> · 방법론과 전체 한계는{" "}
        <span className="font-mono">backtest_sancheong/README.md</span> 참조. 🚫 &ldquo;N명
        살렸다&rdquo; 금지 → &ldquo;공식 경보보다 N시간 빠른 신호&rdquo;로만 표현할 것.
      </p>
    </div>
  );
}
