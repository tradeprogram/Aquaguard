"use client";

import { useRef, useState } from "react";

// Render 무료 플랜은 안 쓰면 잠들어서 첫 요청에 30~60초 콜드스타트가 걸린다 — 그냥
// "로딩 중…"으로만 두면 멈춘 줄 알고 새로고침해버리기 쉬워서, 일정 시간 넘게
// 걸리면 "서버 깨우는 중" 쪽으로 문구를 바꿔줄 수 있게 하는 훅.
export function useSlowLoading(thresholdMs = 4000) {
  const [slow, setSlow] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const start = () => {
    setSlow(false);
    timerRef.current = setTimeout(() => setSlow(true), thresholdMs);
  };
  const stop = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setSlow(false);
  };

  return { slow, start, stop };
}
