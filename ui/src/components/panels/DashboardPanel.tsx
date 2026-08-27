"use client";

import { useState } from "react";
import { SANGCHEONG_DEMO_INPUT, triggerAlert } from "@/lib/api";
import type { ModuleOEnvelope } from "@/lib/types";
import GoldenTimeCounter from "@/components/GoldenTimeCounter";
import RiskCard from "@/components/RiskCard";

export default function DashboardPanel({ onOpenApprove }: { onOpenApprove: () => void }) {
  const [envelope, setEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runDemo() {
    setLoading(true);
    setError(null);
    try {
      const result = await triggerAlert(SANGCHEONG_DEMO_INPUT);
      setEnvelope(result);
    } catch (e) {
      setError(
        `백엔드(api_server.py) 연결 실패 — "python -m uvicorn api_server:app --port 8000"로 먼저 띄워주세요. (${
          e instanceof Error ? e.message : String(e)
        })`
      );
    } finally {
      setLoading(false);
    }
  }

  const data = envelope?.data;
  const alertPackage = data?.alert_package;

  return (
    <div className="space-y-5 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-slate-400">2025.7.19 산청 산사태 재연 — Module O(§5) 목업 파이프라인</p>
        <button
          onClick={runDemo}
          disabled={loading}
          className="shrink-0 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {loading ? "실행 중…" : "산청 시나리오 실행"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-xs text-red-300">{error}</div>
      )}

      {!envelope && !error && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-xs text-slate-500">
          위 버튼으로 시나리오를 실행하면 Module A~H(현재 목업) 결과와 골든타임 비교가 표시됩니다.
        </div>
      )}

      {envelope && data && alertPackage && (
        <>
          {envelope.status !== "ok" && (
            <div className="rounded-lg border border-amber-800/50 bg-amber-950/30 p-3 text-xs text-amber-300">
              status: {envelope.status} (fallback_tier {envelope.fallback_tier}) — {envelope.warnings.join(", ")}
            </div>
          )}

          <GoldenTimeCounter data={data} />

          <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 p-3">
            <div>
              <p className="text-xs text-slate-400">승인 상태 (원클릭 승인, §5 Module O)</p>
              <p className="text-base font-semibold">{data.approval_status}</p>
            </div>
            <button
              onClick={onOpenApprove}
              className="rounded-lg border border-sky-700 px-3 py-1.5 text-xs text-sky-300 hover:bg-sky-950/50"
            >
              승인 화면으로 →
            </button>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <RiskCard
              title="산사태 위험 (Module A)"
              prob={alertPackage.landslide.landslide_prob}
              confidenceInterval={alertPackage.landslide.confidence_interval}
              hoursToCritical={alertPackage.landslide.hours_to_critical}
              source={alertPackage.landslide.source}
              extra={
                alertPackage.landslide.precursor_flag
                  ? "InSAR 땅밀림 전조 감지됨 — 시민 역검증(Module H) 트리거"
                  : undefined
              }
            />
            <RiskCard
              title="하천범람 위험 (Module B)"
              prob={alertPackage.flood.flood_prob}
              confidenceInterval={alertPackage.flood.confidence_interval}
              hoursToCritical={alertPackage.flood.hours_to_critical}
            />
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div className="rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="text-xs text-slate-400">대피소 · 경로 (Module E)</p>
              {"shelter_id" in alertPackage.shelter_route ? (
                <>
                  <p className="mt-1 text-base font-semibold">
                    {alertPackage.shelter_route.shelter_id ?? "대피소 없음"} · ETA{" "}
                    {alertPackage.shelter_route.eta_min?.toFixed(1)}분
                  </p>
                  {!alertPackage.shelter_route.time_feasible && (
                    <p className="mt-1 text-xs font-medium text-red-300">
                      ⚠ 지정 대피소까지 시간이 부족합니다 — 가까운 안전지대로 즉시 이동하세요
                    </p>
                  )}
                  {alertPackage.shelter_route.fallback_used && (
                    <p className="text-[11px] text-amber-300">긴급 폴백 경로 사용됨</p>
                  )}
                </>
              ) : (
                <p className="mt-1 text-xs text-slate-500">임계치 미초과 — 라우팅 미실행</p>
              )}
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="text-xs text-slate-400">예상 피해비용 (Module G)</p>
              {"estimated_cost_krw" in alertPackage.damage_cost ? (
                <>
                  <p className="mt-1 text-base font-semibold">
                    {(alertPackage.damage_cost.estimated_cost_krw / 1e8).toFixed(1)}억원
                  </p>
                  <p className="text-[11px] text-slate-500">{alertPackage.damage_cost.basis_citation}</p>
                </>
              ) : (
                <p className="mt-1 text-xs text-slate-500">임계치 미초과 — 산정 미실행</p>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/5 p-3">
            <p className="text-xs text-slate-400">시민 신고 역검증 (Module H)</p>
            <p className="mt-1 text-base font-semibold">{data.citizen_verification.verification_status}</p>
            <p className="text-[11px] text-slate-500">
              신뢰도 보정: {data.citizen_verification.confidence_adjustment >= 0 ? "+" : ""}
              {(data.citizen_verification.confidence_adjustment * 100).toFixed(0)}%p
            </p>
          </div>
        </>
      )}
    </div>
  );
}
