"use client";

import { useEffect, useState } from "react";
import { SANGCHEONG_DEMO_INPUT, getDemoEnvelope, triggerAlert } from "@/lib/api";
import { diagnoseFailure } from "@/lib/backendDiagnosis";
import type { ModuleOEnvelope } from "@/lib/types";
import { useSlowLoading } from "@/lib/useSlowLoading";
import GoldenTimeCounter from "@/components/GoldenTimeCounter";
import RiskCard from "@/components/RiskCard";
import ProvenanceBadge from "@/components/ProvenanceBadge";
import AssumptionNote from "@/components/AssumptionNote";
import { damageCostProvenance, exposureProvenance } from "@/lib/provenance";

// Module O가 alert_package.road_flooding으로 Module C 결과를 실어주기 전까지 쓰던
// 예시 목록(contracts/module_c.example.json 기준). 지금은 파이프라인이 값을 주면
// 그걸 쓰고, 아직 underpasses 입력이 없어 빈 배열로 오면 이 목록으로 화면을 채운다.
// alert_level ∈ 정상/주의/경계/위험(§5 Module C).
// 실행 중 화면에 나열할 모듈. 서버가 단계별 진행을 알려주지 않으므로 "지금 여기"를
// 표시하지 않는다 — 무엇이 도는지만 보여 준다(있지도 않은 진행률을 그리지 않기 위해서).
const PIPELINE_STEPS = [
  "A 산사태 확률",
  "B 하천범람",
  "C 도로·지하차도",
  "D 노출자산",
  "E 대피경로",
  "G 피해액",
  "H 시민신고 검증",
  "O 통합·골든타임",
];

// 배포본(EC2) 실측값. 화면에 "보통 N초"라고 쓰려면 실제로 재 본 값이어야 한다.
const TYPICAL_RUN_SEC = 20;

// 결과가 0.06초에 와도 진행 화면을 이만큼은 띄워 둔다.
//
// 시연에서 어느 모듈이 어떤 순서로 도는지가 보여야 하는데, 눈 깜짝할 새에 지나가면
// 화면이 한 번 깜빡인 것으로만 남는다. 결과를 늦게 받는 게 아니라 **이미 받아 둔
// 결과를 이만큼 뒤에 보여주는 것**이다.
const MIN_PROGRESS_SEC = 5;

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

export default function DashboardPanel({
  mode,
  onAlertUpdated,
}: {
  mode: "citizen" | "gov";
  // 데모를 돌리면 지도 쪽 침수 폴리곤·시간축도 같이 새로 받아야 한다 — 두 컴포넌트가
  // 형제라 page.tsx가 이 신호를 받아 MapExplorer로 내려 준다(§6.9와 같은 방식).
  onAlertUpdated?: () => void;
}) {
  const govOnly = mode === "gov";
  const [envelope, setEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  // 실제로 흐른 시간. 가짜 진행률(%)을 그리는 대신 이걸 그대로 보여 준다 —
  // 어디까지 왔는지는 서버가 안 알려주므로 모르는 걸 아는 척하지 않는다.
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const { slow, start, stop } = useSlowLoading();

  // 실행 중에는 0.1초마다 경과를 갱신한다. 멈춘 화면과 도는 화면을 사람이 구분하는
  // 가장 확실한 신호가 "숫자가 계속 변하는 것"이다.
  useEffect(() => {
    if (!loading) return;
    const t0 = Date.now();
    const id = setInterval(() => setElapsed((Date.now() - t0) / 1000), 100);
    return () => clearInterval(id);
  }, [loading]);

  async function runDemo(forceLive = false) {
    // 경과 표시를 0에서 시작시킨다 — effect 본문에서 setState 하면 렌더가 한 번 더 돈다.
    setElapsed(0);
    setLoading(true);
    setError(null);
    start();
    try {
      // 사전계산본을 프론트 자기 오리진에서 먼저 읽는다. 지도가 EC2로 타일을 수백 장
      // 부르는 동안 이 요청이 그 줄 뒤에 서면 서버가 0.013초에 답해도 화면에서는
      // 수십~수백 초가 된다(2026-09-21 실측). 오리진이 다르면 그 줄을 안 탄다.
      const startedAt = Date.now();
      const result = (!forceLive && (await getDemoEnvelope())) || (await triggerAlert(SANGCHEONG_DEMO_INPUT));
      const remaining = MIN_PROGRESS_SEC * 1000 - (Date.now() - startedAt);
      if (remaining > 0) await new Promise((r) => setTimeout(r, remaining));
      setEnvelope(result);
      onAlertUpdated?.();
    } catch {
      // 문구를 고정해두면 진단이 헛돈다 — 2026-09-20에 실제로 그랬다. 화면에는
      // "무료 호스팅이라 깨어나는 데 시간이 걸린다"(Render 시절 문구)가 떴지만
      // 배포는 EC2였고, 진짜 원인은 메모리 부족으로 uvicorn이 OOM-kill 당한 것이라
      // "기다리면 되는 문제"로 읽혀 원인 파악이 늦어졌다. 다른 패널들처럼 /health를
      // 실제로 찔러 서버가 죽었는지·배포가 뒤처졌는지·요청 자체 문제인지 구분한다.
      setError(await diagnoseFailure("위험 현황 조회", "/alerts/trigger"));
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
  // 배지와 가정 표시는 explain()에서 나온다 — 화면이 문구를 지어내지 않는다(lib/provenance.ts).
  const exposureInfo = exposureProvenance(envelope?.meta?.explains);
  const damageInfo = damageCostProvenance(envelope?.meta?.explains);
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
            ? "2025.7.19 산청 산사태 재연 — Module O 통합 파이프라인"
            : "2025.7.19 산청 산사태 재연 데이터 기반 — 우리 동네 위험 현황"}
        </p>
        <button
          onClick={() => runDemo()}
          disabled={loading}
          className="shrink-0 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          <span className="flex items-center gap-1.5">
            {loading && (
              <span
                aria-hidden
                className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white"
              />
            )}
            {loading
              ? `실행 중 ${elapsed.toFixed(1)}초`
              : govOnly
                ? "산청 시나리오 실행"
                : "우리 동네 위험 확인하기"}
          </span>
        </button>
      </div>

      {envelope?.meta?.served_from === "snapshot" && !loading && (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-1.5 text-[11px] text-slate-400">
          <span>
            사전계산 결과입니다
            {typeof envelope.meta.snapshot_built_commit === "string" && (
              <> · {envelope.meta.snapshot_built_commit}</>
            )}
            {typeof envelope.meta.snapshot_pipeline_seconds === "number" && (
              <> · 실제 파이프라인 {envelope.meta.snapshot_pipeline_seconds}초</>
            )}
          </span>
          <button
            onClick={() => runDemo(true)}
            className="shrink-0 rounded-md border border-slate-700 px-2 py-0.5 text-slate-300 hover:border-sky-600 hover:text-sky-300"
            title="저장본을 무시하고 전 모듈을 실제로 다시 돌립니다"
          >
            ↻ 실시간으로 다시 계산
          </button>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-xs text-red-300">{error}</div>
      )}

      {/* 실행 중 화면. 예전에는 버튼 글자만 "실행 중…"으로 바뀌고 이 자리는 계속
          "위 버튼을 누르면…"이었다 — 20초 넘게 그대로라 멈춘 것처럼 보였다.
          진행률(%)은 만들지 않는다. 서버가 어느 모듈까지 갔는지 알려주지 않으므로
          그걸 그리면 지어낸 숫자가 된다. 대신 (1) 계속 움직이는 경과 시간,
          (2) 실측한 평소 소요시간, (3) 지금 도는 모듈 목록을 보여 준다. */}
      {loading && (
        <div className="rounded-xl border border-sky-900/50 bg-sky-950/20 p-4 text-xs">
          <div className="flex items-baseline justify-between">
            <p className="font-medium text-sky-200">
              7개 모듈의 결과를 순서대로 불러오고 통합하고 있습니다
            </p>
            <p className="font-mono text-base text-sky-300">{elapsed.toFixed(1)}초</p>
          </div>

          {/* 진행률이 아니라 "돌고 있다"는 표시 — 좌우로 흐르는 띠 */}
          <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-slate-800">
            <div className="h-full w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] rounded-full bg-sky-400" />
          </div>
          <style>{`@keyframes indeterminate {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(300%); }
          }`}</style>

          <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-slate-400">
            {PIPELINE_STEPS.map((step) => (
              <li key={step}>· {step}</li>
            ))}
          </ul>

          <p className="mt-3 text-slate-500">
            보통 {TYPICAL_RUN_SEC}초쯤 걸립니다
            {elapsed > TYPICAL_RUN_SEC * 2 && " — 평소보다 오래 걸리고 있습니다"}.
            {slow && " 서버가 잠들어 있었다면 첫 요청은 더 걸립니다."}
          </p>
        </div>
      )}

      {!envelope && !error && !loading && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-xs text-slate-500">
          {govOnly
            ? "위 버튼으로 시나리오를 실행하면 Module A~H 결과와 골든타임 비교가 표시됩니다."
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

          {/* Module C·D는 2026-09-05에 파이프라인에 연결됐다. 다만 목업 모드에서는
              여전히 example.json 값이 오므로, 어느 쪽인지는 meta.module_sources로
              판단해 실제로 예시일 때만 알린다 — 늘 띄워두면 실데이터일 때 거짓말이 된다. */}
          {envelope.meta?.module_sources &&
            (envelope.meta.module_sources.d === "example" ||
              envelope.meta.module_sources.c === "example") && (
              <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
                아래 도로·노출자산 수치는 실제 모듈이 아니라 contracts/module_c·d.example.json
                예시값입니다 (AQUAGUARD_MOCK_MODE=0으로 실모듈 전환).
              </div>
            )}

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
                노출자산 (Module D) <ProvenanceBadge kind={exposureInfo.kind} />
              </p>
              {alertPackage.exposure ? (
                <>
                  <p className="mt-1 text-base font-semibold">
                    건물 {alertPackage.exposure.exposed_buildings.length.toLocaleString()}동 노출 ·
                    농경지 {alertPackage.exposure.exposed_farmland_ha.toLocaleString()}ha
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {Object.entries(
                      alertPackage.exposure.exposed_buildings.reduce<Record<string, number>>((acc, b) => {
                        acc[b.use_type] = (acc[b.use_type] ?? 0) + 1;
                        return acc;
                      }, {})
                    )
                      .sort((a, b) => b[1] - a[1])
                      .map(([useType, n]) => `${useType} ${n.toLocaleString()}`)
                      .join(" · ")}
                  </p>
                </>
              ) : (
                <p className="mt-1 text-xs text-slate-500">임계치 미초과 — 오버레이 미실행</p>
              )}
              <AssumptionNote items={exposureInfo.assumptions} />
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
                  노출 자산 기준 피해액 하한 (Module G) <ProvenanceBadge kind={damageInfo.kind} />
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
                    <AssumptionNote items={damageInfo.assumptions} />
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
