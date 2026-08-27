"use client";

import { useState } from "react";
import { SANGCHEONG_DEMO_INPUT, triggerAlert } from "@/lib/api";
import type { ModuleOEnvelope } from "@/lib/types";
import RiskCard from "@/components/RiskCard";

export default function WhatIfPage() {
  const [rainfall, setRainfall] = useState(250);
  const [envelope, setEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [loading, setLoading] = useState(false);

  async function recompute() {
    setLoading(true);
    try {
      // §5 Module UI-3D: 새 모델을 만들지 않고 Module A/B의 run()을 가상 강수값으로 재호출.
      // module_a_extra/module_b_extra는 orchestrator가 A/B 입력에 그대로 병합해 전달한다 —
      // 실제 모델이 붙으면 이 슬라이더가 바로 반영된다 (지금은 목업이라 값이 고정 출력됨).
      const result = await triggerAlert({
        ...SANGCHEONG_DEMO_INPUT,
        alert_id: `${SANGCHEONG_DEMO_INPUT.alert_id}-whatif`,
        // @ts-expect-error module_a_extra/module_b_extra는 계약 외 확장 필드 (orchestrator.py 참조)
        module_a_extra: { dynamic: { rainfall_cumulative_24h_mm: rainfall } },
        module_b_extra: { dynamic: { rainfall_cumulative_24h_mm: [rainfall] } },
      });
      setEnvelope(result);
    } finally {
      setLoading(false);
    }
  }

  const alertPackage = envelope?.data.alert_package;

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">What-if 예측 시뮬레이터</h1>
        <p className="text-sm text-slate-400">
          §5 Module UI-3D — &ldquo;만약 산청에 {rainfall}mm가 왔다면 위험지역이 어디까지 넓어졌을까&rdquo;를
          직접 조작하며 체감.
        </p>
      </header>

      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center justify-between text-sm text-slate-400">
          <span>24시간 누적강우량 가상 시나리오</span>
          <span className="font-mono text-lg text-slate-100">{rainfall}mm</span>
        </div>
        <input
          type="range"
          min={150}
          max={350}
          step={10}
          value={rainfall}
          onChange={(e) => setRainfall(Number(e.target.value))}
          className="mt-3 w-full accent-sky-500"
        />
        <div className="mt-1 flex justify-between text-xs text-slate-600">
          <span>150mm</span>
          <span>350mm</span>
        </div>
        <button
          onClick={recompute}
          disabled={loading}
          className="mt-4 w-full rounded-lg bg-sky-600 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {loading ? "재계산 중…" : "Module A/B 재호출"}
        </button>
      </div>

      <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-xs text-amber-300/80">
        현재 Module A/B는 목업(AQUAGUARD_MOCK_MODE=1)이라 슬라이더 값과 무관하게 contracts/의 example.json
        고정값을 반환합니다. 트랙①의 실제 모델이 연동되면 이 슬라이더가 실제 위험확률·폴리곤을 즉시 재계산합니다.
      </div>

      {alertPackage && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
