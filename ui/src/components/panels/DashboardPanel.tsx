"use client";

import { useState } from "react";
import { API_BASE, SANGCHEONG_DEMO_INPUT, triggerAlert } from "@/lib/api";
import type { ModuleOEnvelope } from "@/lib/types";
import { useSlowLoading } from "@/lib/useSlowLoading";
import GoldenTimeCounter from "@/components/GoldenTimeCounter";
import RiskCard from "@/components/RiskCard";
import ProvenanceBadge from "@/components/ProvenanceBadge";

// Module O가 alert_package.road_flooding으로 Module C 결과를 실어주기 전까지 쓰던
// 예시 목록(contracts/module_c.example.json 기준). 지금은 파이프라인이 값을 주면
// 그걸 쓰고, 아직 underpasses 입력이 없어 빈 배열로 오면 이 목록으로 화면을 채운다.
// alert_level ∈ 정상/주의/경계/위험(§5 Module C).
const DEMO_UNDERPASSES: { id: string; name: string; level: "정상" | "주의" | "경계" | "위험" }[] = [
  { id: "SC-UP-003", name: "산청천 지하차도", level: "위험" },
  { id: "SC-UP-011", name: "생비량로 지하차도", level: "주의" },
  { id: "SC-RD-004", name: "경호강변 저지대 도로", level: "정상" },
];
const LEVEL_STYLE: Record<string, string> = {
  정상: "bg-slate-800 text-slate-300",
  주의: "bg-amber-900/60 text-amber-300",
  경계: "bg-orange-900/60 text-orange-300",
  위험: "bg-red-900/60 text-red-300",
};

export default function DashboardPanel({ mode }: { mode: "citizen" | "gov" }) {
  const govOnly = mode === "gov";
  const [envelope, setEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { slow, start, stop } = useSlowLoading();

  async function runDemo() {
    setLoading(true);
    setError(null);
    start();
    try {
      const result = await triggerAlert(SANGCHEONG_DEMO_INPUT);
      setEnvelope(result);
    } catch (e) {
      setError(
        API_BASE.includes("localhost")
          ? `백엔드(api_server.py) 연결 실패 — "python -m uvicorn api_server:app --port 8000"로 먼저 띄워주세요. (${
              e instanceof Error ? e.message : String(e)
            })`
          : `백엔드 서버 연결 실패 — 무료 호스팅이라 오래 쉬었으면 깨어나는 데 시간이 걸릴 수 있어요. 잠시 후 다시 시도해주세요. (${
              e instanceof Error ? e.message : String(e)
            })`
      );
    } finally {
      stop();
      setLoading(false);
    }
  }

  const data = envelope?.data;
  const alertPackage = data?.alert_package;
  // Module O가 실제 Module C 결과를 주면 그걸 쓰고, 아직 underpasses 입력이 없어
  // 빈 배열로 오면 데모 목록으로 채운다. 이름은 계약에 없는 값이라(C는 underpass_id만
  // 낸다) 데모 목록에서 찾고, 없으면 id를 그대로 보여준다.
  const underpasses = alertPackage?.road_flooding?.length
    ? alertPackage.road_flooding.map((u) => ({
        id: u.underpass_id,
        name: DEMO_UNDERPASSES.find((d) => d.id === u.underpass_id)?.name ?? u.underpass_id,
        level: u.alert_level,
      }))
    : DEMO_UNDERPASSES;

  return (
    <div className="space-y-5 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-slate-400">
          {govOnly
            ? "2025.7.19 산청 산사태 재연 — Module O(§5) 목업 파이프라인"
            : "2025.7.19 산청 산사태 재연 데이터 기반 — 우리 동네 위험 현황"}
        </p>
        <button
          onClick={runDemo}
          disabled={loading}
          className="shrink-0 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {loading
            ? slow
              ? "서버 깨우는 중… (최대 1분)"
              : "실행 중…"
            : govOnly
              ? "산청 시나리오 실행"
              : "우리 동네 위험 확인하기"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-xs text-red-300">{error}</div>
      )}

      {!envelope && !error && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-xs text-slate-500">
          {govOnly
            ? "위 버튼으로 시나리오를 실행하면 Module A~H(현재 목업) 결과와 골든타임 비교가 표시됩니다."
            : "위 버튼을 누르면 우리 동네의 산사태·홍수 위험, 도로 침수, 대피 경로가 표시됩니다."}
        </div>
      )}

      {envelope && data && alertPackage && (
        <>
          {envelope.status !== "ok" && (
            <div className="rounded-lg border border-amber-800/50 bg-amber-950/30 p-3 text-xs text-amber-300">
              status: {envelope.status} (fallback_tier {envelope.fallback_tier}) — {envelope.warnings.join(", ")}
            </div>
          )}

          {govOnly && <GoldenTimeCounter data={data} />}

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

          <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
            Module C·D는 아직 Module O 파이프라인에 연결 전 — 아래는
            contracts/module_c·d.example.json 기준 예시 데이터.
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div className="rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="flex items-center gap-1.5 text-xs text-slate-400">
                도로·지하차도 침수 (Module C) <ProvenanceBadge kind="RULE" />
              </p>
              <p className="mt-0.5 text-[11px] text-slate-500">
                예측 모델이 아니라 관측 강우에 고시 임계값을 적용한 규칙 판정입니다
              </p>
              <div className="mt-2 space-y-1.5">
                {underpasses.map((u) => (
                  <div key={u.id} className="flex items-center justify-between text-xs">
                    <span className="text-slate-300">{u.name}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${LEVEL_STYLE[u.level]}`}>
                      {u.level}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="flex items-center gap-1.5 text-xs text-slate-400">
                노출자산 (Module D) <ProvenanceBadge kind="MODEL" />
              </p>
              <p className="mt-1 text-base font-semibold">건물 3채 노출 · 농경지 4.2ha</p>
              <p className="text-[11px] text-slate-500">주거 2 · 상가 1 — risk_prob 45~78%</p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div className="rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="flex items-center gap-1.5 text-xs text-slate-400">
                대피소 · 경로 (Module E) <ProvenanceBadge kind="MODEL" />
              </p>
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
            {govOnly && (
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                {/* "예상 피해액"이 아니다 — Module G는 노출된 자산에 복구비 지원단가를
                    곱한 값이라 실제 피해 총액이 아니라 그 하한이다. 비주거·용도 미상
                    건물은 공식 침수 단가가 없어 아예 빠져 있고 위험확률 가중도 없다.
                    라벨이 "예상 피해액"이면 심사에서 과대 주장으로 읽힌다(트랙② 요청 3). */}
                <p className="flex items-center gap-1.5 text-xs text-slate-400">
                  노출 자산 기준 피해액 하한 (Module G) <ProvenanceBadge kind="MODEL" />
                </p>
                {"estimated_cost_krw" in alertPackage.damage_cost ? (
                  <>
                    <p className="mt-1 text-base font-semibold">
                      {(alertPackage.damage_cost.estimated_cost_krw / 1e8).toFixed(1)}억원
                      <span className="ml-1 text-xs font-normal text-slate-400">이상</span>
                    </p>
                    <p className="text-[11px] text-slate-400">
                      복구비 지원단가 기준 · 위험확률 미가중 · 비주거/용도 미상 제외
                    </p>
                    <p className="text-[11px] text-slate-500">{alertPackage.damage_cost.basis_citation}</p>
                  </>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">임계치 미초과 — 산정 미실행</p>
                )}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-white/10 bg-white/5 p-3">
            <p className="flex items-center gap-1.5 text-xs text-slate-400">
              시민 신고 역검증 (Module H) <ProvenanceBadge kind="OBSERVED" />
            </p>
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
