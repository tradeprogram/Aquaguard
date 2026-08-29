// §6.1(ARCHITECTURE.md, 2026-08-29 신규) — 화면의 모든 숫자·폴리곤·경로는 그게
// 실측인지/예보인지/우리 모델이 계산한 값인지/사용자가 넣은 가정값인지 한눈에
// 구분돼야 한다("이 빨간 영역은 진짜 모델이 계산한 건가요?"를 배지 하나로 방어).
// 계약 필드 추가가 아니라 UI 레이어에서 이미 아는 출처 정보(모듈 이름, source
// 필드, What-if 조작 여부)로만 매핑해 다른 트랙 계약을 안 건드리고 구현한다.
export type Provenance = "OBSERVED" | "FORECAST" | "MODEL" | "ASSUMPTION";

const STYLE: Record<Provenance, { label: string; className: string }> = {
  OBSERVED: { label: "실측 OBSERVED", className: "border-emerald-700/50 bg-emerald-950/50 text-emerald-300" },
  FORECAST: { label: "예보 FORECAST", className: "border-sky-700/50 bg-sky-950/50 text-sky-300" },
  MODEL: { label: "모델계산 MODEL", className: "border-violet-700/50 bg-violet-950/50 text-violet-300" },
  ASSUMPTION: { label: "가정값 ASSUMPTION", className: "border-amber-700/50 bg-amber-950/50 text-amber-300" },
};

export default function ProvenanceBadge({ kind, className = "" }: { kind: Provenance; className?: string }) {
  const s = STYLE[kind];
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-1.5 py-0.5 text-[9px] font-medium tracking-tight ${s.className} ${className}`}
    >
      {s.label}
    </span>
  );
}
