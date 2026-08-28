"use client";

import { useCallback, useEffect, useState } from "react";
import { SANGCHEONG_DEMO_INPUT, approveAlert, getAlert } from "@/lib/api";
import type { ModuleOEnvelope } from "@/lib/types";
import { useSlowLoading } from "@/lib/useSlowLoading";

function useCountdown(createdAt?: string, timeoutMin?: number) {
  const [remainingSec, setRemainingSec] = useState<number | null>(null);

  useEffect(() => {
    if (!createdAt || timeoutMin === undefined) return;
    const deadline = new Date(createdAt).getTime() + timeoutMin * 60_000;
    const tick = () => setRemainingSec(Math.max(0, Math.round((deadline - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [createdAt, timeoutMin]);

  return remainingSec;
}

export default function ApprovePanel({ alertId = SANGCHEONG_DEMO_INPUT.alert_id }: { alertId?: string }) {
  const [envelope, setEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const { slow, start, stop } = useSlowLoading();

  const refresh = useCallback(
    async (isInitial = false) => {
      if (isInitial) start();
      try {
        const result = await getAlert(alertId);
        setEnvelope(result);
        setError(null);
      } catch {
        setError("이 alert_id의 경보를 찾을 수 없습니다 — 대시보드에서 먼저 시나리오를 실행하세요.");
      } finally {
        if (isInitial) {
          stop();
          setInitialLoading(false);
        }
      }
    },
    [alertId, start, stop]
  );

  useEffect(() => {
    // refresh()는 네트워크 응답 이후(await 뒤)에만 setState하므로 안전하지만,
    // 정적 분석 규칙은 이를 구분하지 못해 명시적으로 예외 처리한다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh(true);
    const id = setInterval(() => refresh(false), 3000);
    return () => clearInterval(id);
  }, [refresh]);

  const remainingSec = useCountdown(envelope?.meta?.created_at, envelope?.meta?.escalation_timeout_min);

  async function decide(decision: "승인" | "거부") {
    setSubmitting(true);
    start();
    try {
      await approveAlert(alertId, decision, "official_demo");
      await refresh();
    } finally {
      stop();
      setSubmitting(false);
    }
  }

  const data = envelope?.data;
  const alertPackage = data?.alert_package;
  // 2026-08-29: 자동승인 삭제 — "권고중(escalation)"도 여전히 사람의 승인/거부를
  // 기다리는 미확정 상태다(§5 Module O). 확정 상태는 "승인"/"거부"뿐이라 버튼도
  // escalation 중에는 계속 눌러야 한다.
  const escalated = data?.approval_status === "권고중(escalation)";
  const pending = data?.approval_status === "대기" || escalated;
  const timedOut = remainingSec === 0;

  return (
    <div className="space-y-5 text-sm">
      <p className="text-xs text-slate-400">
        §5 Module O — 지자체 담당자가 회의·서면 검토 없이 버튼 하나로 승인/보류. 사람의 최종 판단권은
        유지하되 판단 시간을 몇 시간→몇 초로.
      </p>

      {initialLoading && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-xs text-slate-500">
          {slow ? "서버 깨우는 중… (최대 1분, 무료 호스팅이라 오래 쉬면 느려요)" : "불러오는 중…"}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-xs text-red-300">{error}</div>
      )}

      {data && alertPackage && (
        <>
          <div
            className={`rounded-xl border p-5 text-center ${
              escalated
                ? "border-red-800/50 bg-red-950/30"
                : pending
                  ? "border-amber-800/50 bg-amber-950/30"
                  : "border-emerald-800/50 bg-emerald-950/30"
            }`}
          >
            <p className="text-xs opacity-80">현재 상태</p>
            <p className="mt-1 text-2xl font-bold">{data.approval_status}</p>
            {data.approval_status === "대기" && remainingSec !== null && !timedOut && (
              <p className="mt-2 text-xs">
                {`${Math.floor(remainingSec / 60)}분 ${remainingSec % 60}초 안에 응답하지 않으면 상위 담당자에게 긴급 재알림(escalation)됩니다`}
              </p>
            )}
            {escalated && (
              <p className="mt-2 text-xs text-red-300">
                {`무응답으로 상위 담당자에게 ${data.escalation_level}차 긴급 재알림됨 — 시스템은 대피명령을 독자 발령하지 않습니다. 계속 승인/거부 대기 중`}
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 rounded-xl border border-white/10 bg-white/5 p-3 text-xs">
            <div>
              <p className="text-slate-400">산사태 위험확률</p>
              <p className="text-base font-semibold">
                {(alertPackage.landslide.landslide_prob * 100).toFixed(0)}%{" "}
                <span className="text-[10px] font-normal text-slate-500">
                  [{(alertPackage.landslide.confidence_interval[0] * 100).toFixed(0)}%,{" "}
                  {(alertPackage.landslide.confidence_interval[1] * 100).toFixed(0)}%]
                </span>
              </p>
            </div>
            <div>
              <p className="text-slate-400">하천범람 위험확률</p>
              <p className="text-base font-semibold">{(alertPackage.flood.flood_prob * 100).toFixed(0)}%</p>
            </div>
            <div>
              <p className="text-slate-400">시민 역검증</p>
              <p className="text-base font-semibold">{data.citizen_verification.verification_status}</p>
            </div>
            <div>
              <p className="text-slate-400">대피 시간 여유</p>
              <p className="text-base font-semibold">
                {"time_feasible" in alertPackage.shelter_route
                  ? alertPackage.shelter_route.time_feasible
                    ? "충분"
                    : "부족 ⚠"
                  : "—"}
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => decide("승인")}
              disabled={!pending || submitting}
              className="flex-1 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-40"
            >
              {submitting && slow ? "서버 깨우는 중…" : "승인"}
            </button>
            <button
              onClick={() => decide("거부")}
              disabled={!pending || submitting}
              className="flex-1 rounded-lg bg-red-700 py-2.5 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-40"
            >
              {submitting && slow ? "서버 깨우는 중…" : "거부"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
