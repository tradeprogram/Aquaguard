"use client";

import { useCallback, useRef, useState } from "react";

// 응답이 늦어질 때 문구를 바꿔줄 수 있게 하는 훅. "로딩 중…"으로만 두면 멈춘 줄 알고
// 새로고침해버리기 쉽다.
//
// 예전엔 늦으면 "서버 깨우는 중(무료 호스팅)"이라고 띄웠는데, 그건 Render 무료 플랜
// 시절의 문구다. 지금 배포는 EC2라 잠들지 않으므로 그 문구는 틀린 안내였고, 기다리면
// 되는 문제로 오해하게 만들었다(2026-09-20 실제로 그랬다). 지금은 "응답이 늦어지는
// 중"까지만 말하고, 원인 진단은 lib/backendDiagnosis.ts가 /health를 찔러서 한다.
//
// start/stop을 useCallback으로 고정해둔다 — 안 그러면 매 렌더 새 함수가 나가서,
// 이걸 의존성 배열에 넣는 쪽(예: ApprovePanel의 refresh useCallback)에서 렌더마다
// 콜백이 재생성 → 그 콜백에 의존하는 effect가 매번 재실행 → setState → 재렌더 →
// 다시 재생성되는 무한 루프에 빠질 수 있다.
export function useSlowLoading(thresholdMs = 4000) {
  const [slow, setSlow] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const start = useCallback(() => {
    setSlow(false);
    timerRef.current = setTimeout(() => setSlow(true), thresholdMs);
  }, [thresholdMs]);

  const stop = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setSlow(false);
  }, []);

  return { slow, start, stop };
}
