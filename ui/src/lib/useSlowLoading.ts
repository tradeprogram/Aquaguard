"use client";

import { useCallback, useRef, useState } from "react";

// Render 무료 플랜은 안 쓰면 잠들어서 첫 요청에 30~60초 콜드스타트가 걸린다 — 그냥
// "로딩 중…"으로만 두면 멈춘 줄 알고 새로고침해버리기 쉬워서, 일정 시간 넘게
// 걸리면 "서버 깨우는 중" 쪽으로 문구를 바꿔줄 수 있게 하는 훅.
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
