"use client";

import { useState } from "react";
import { SANGCHEONG_DEMO_INPUT, triggerAlert } from "@/lib/api";
import type { ModuleOEnvelope } from "@/lib/types";
import { useSlowLoading } from "@/lib/useSlowLoading";
import RiskCard from "@/components/RiskCard";
import ProvenanceBadge from "@/components/ProvenanceBadge";

// 기준(baseline) 강우량 — 이 값 대비 "+N%"로 슬라이더를 표시한다(심층 경쟁기술
// 리서치 2026-08-29: "강우 +30%면 대피 가능시간이 X분→Y분" 프레이밍이 counterfactual
// 데모의 핵심 장면). SANGCHEONG_DEMO_INPUT 자체엔 강우값이 없어 Module A/B 목업
// example.json이 가정하는 산청 사건 24시간 누적강우량(187.3mm)을 기준으로 삼는다.
const BASELINE_RAINFALL_MM = 187.3;

export default function WhatifPanel() {
  const [rainfall, setRainfall] = useState(BASELINE_RAINFALL_MM);
  const [envelope, setEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [baselineEnvelope, setBaselineEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const { slow, start, stop } = useSlowLoading();

  async function runScenario(rainfallMm: number) {
    // §5 Module UI-3D: 새 모델을 만들지 않고 Module A/B의 run()을 가상 강수값으로 재호출.
    // module_a_extra/module_b_extra는 orchestrator가 A/B 입력에 그대로 병합해 전달한다 —
    // 실제 모델이 붙으면 이 슬라이더가 바로 반영된다 (지금은 목업이라 값이 고정 출력됨).
    return triggerAlert({
      ...SANGCHEONG_DEMO_INPUT,
      alert_id: `${SANGCHEONG_DEMO_INPUT.alert_id}-whatif`,
      // @ts-expect-error module_a_extra/module_b_extra는 계약 외 확장 필드 (orchestrator.py 참조)
      module_a_extra: { dynamic: { rainfall_cumulative_24h_mm: rainfallMm } },
      module_b_extra: { dynamic: { rainfall_cumulative_24h_mm: [rainfallMm] } },
    });
  }

  async function recompute() {
    setLoading(true);
    start();
    try {
      // 카운터팩추얼은 "이전과 비교해 뭐가 바뀌는지"가 핵심이라, 기준 시나리오(현재
      // 강우량 그대로)와 사용자가 조작한 시나리오를 함께 재실행해 나란히 비교한다.
      const [baseline, current] = await Promise.all([
        runScenario(BASELINE_RAINFALL_MM),
        runScenario(rainfall),
      ]);
      setBaselineEnvelope(baseline);
      setEnvelope(current);
    } finally {
      stop();
      setLoading(false);
    }
  }

  const alertPackage = envelope?.data.alert_package;
  const baselinePackage = baselineEnvelope?.data.alert_package;
  const pctDelta = Math.round(((rainfall - BASELINE_RAINFALL_MM) / BASELINE_RAINFALL_MM) * 100);

  const baselineMargin =
    baselinePackage && "time_margin_min" in baselinePackage.shelter_route
      ? baselinePackage.shelter_route.time_margin_min
      : null;
  const currentMargin =
    alertPackage && "time_margin_min" in alertPackage.shelter_route ? alertPackage.shelter_route.time_margin_min : null;

  return (
    <div className="space-y-5 text-sm">
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
        §5 Module UI-3D — 산지 급성재난 대응형 counterfactual: &ldquo;강우가 기준 대비 {pctDelta >= 0 ? "+" : ""}
        {pctDelta}% 늘면 대피 가능시간이 어떻게 줄어드는가&rdquo;를 직접 조작하며 체감.
        <ProvenanceBadge kind="ASSUMPTION" />
      </p>

      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>24시간 누적강우량 가상 시나리오</span>
          <span className="font-mono text-base text-slate-100">
            {rainfall}mm{" "}
            <span className={pctDelta > 0 ? "text-red-300" : pctDelta < 0 ? "text-sky-300" : "text-slate-500"}>
              ({pctDelta >= 0 ? "+" : ""}
              {pctDelta}%)
            </span>
          </span>
        </div>
        <input
          type="range"
          min={100}
          max={350}
          step={10}
          value={rainfall}
          onChange={(e) => setRainfall(Number(e.target.value))}
          className="mt-3 w-full accent-sky-500"
        />
        <div className="mt-1 flex justify-between text-[10px] text-slate-600">
          <span>100mm</span>
          <span className="text-slate-500">기준 {BASELINE_RAINFALL_MM}mm (2025.7.19 산청 실측)</span>
          <span>350mm</span>
        </div>
        <button
          onClick={recompute}
          disabled={loading}
          className="mt-4 w-full rounded-lg bg-sky-600 py-2 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {loading ? (slow ? "서버 깨우는 중… (최대 1분)" : "기준 시나리오와 나란히 재계산 중…") : "기준 대비 재계산"}
        </button>
      </div>

      <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
        현재 Module A/B/E는 목업(AQUAGUARD_MOCK_MODE=1)이라 슬라이더 값과 무관하게 contracts/의 example.json
        고정값을 반환합니다 — 아래 대피 가능시간 비교도 그래서 현재는 항상 같은 값입니다. 트랙①④의 실제 모델이
        연동되면 이 슬라이더가 실제 위험확률·폴리곤·대피 여유시간을 즉시 재계산합니다.
      </div>

      {baselineMargin !== null && currentMargin !== null && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <p className="flex items-center gap-1.5 text-xs text-slate-400">
            대피 가능시간(time_margin_min) 비교 <ProvenanceBadge kind="MODEL" />
          </p>
          <p className="mt-2 flex items-center gap-2 text-2xl font-bold">
            <span className="text-slate-300">{baselineMargin.toFixed(0)}분</span>
            <span className="text-slate-600">→</span>
            <span className={currentMargin < baselineMargin ? "text-red-300" : "text-emerald-300"}>
              {currentMargin.toFixed(0)}분
            </span>
          </p>
          <p className="mt-1 text-xs text-slate-500">
            기준 시나리오({BASELINE_RAINFALL_MM}mm) 대비 강우 {pctDelta >= 0 ? "+" : ""}
            {pctDelta}%일 때 대피 가능시간이{" "}
            {currentMargin === baselineMargin
              ? "동일합니다(목업 고정값 — 실모델 연동 전)"
              : currentMargin < baselineMargin
                ? `${(baselineMargin - currentMargin).toFixed(0)}분 감소합니다`
                : `${(currentMargin - baselineMargin).toFixed(0)}분 증가합니다`}
            .
          </p>
        </div>
      )}

      {alertPackage && (
        <div className="grid grid-cols-1 gap-3">
          <RiskCard
            title="산사태 위험 (Module A)"
            prob={alertPackage.landslide.landslide_prob}
            confidenceInterval={alertPackage.landslide.confidence_interval}
            hoursToCritical={alertPackage.landslide.hours_to_critical}
            source={alertPackage.landslide.source}
          />
          <RiskCard
            title="하천범람 위험 (Module B)"
            prob={alertPackage.flood.flood_prob}
            confidenceInterval={alertPackage.flood.confidence_interval}
            hoursToCritical={alertPackage.flood.hours_to_critical}
          />
        </div>
      )}
    </div>
  );
}
