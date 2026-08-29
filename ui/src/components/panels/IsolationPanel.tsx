// 독창성 축 4(신규 제안) — HANDOFF.md §7, ARCHITECTURE.md §15의 IMPACT & NETWORK
// ENGINE(2026-08-29 심층 리서치 반영: "가장 강한 technology gap"으로 재확인).
// 도로망 그래프에서 위험 구간을 제거한 뒤 대피소까지 도달 가능한 경로가 하나도
// 안 남는 지역을 찾아내는 기능. networkx 그래프 연결성 분석이 아직 구현 전(트랙④
// 소유)이라 실제 계산 결과가 아니라 "이 화면이 완성되면 무엇을 보여줄지"에 대한
// 개념 미리보기다 — 예시 구역명도 실존 마을이 아니라 자리표시자.
//
// time_to_isolation_min: §9 데모 시나리오 신규 항목 — "몇 분 뒤 이 마을이 완전히
// 고립되는가"를 숫자로 보여주는 게 골든타임 서사의 마지막 고리다. 대피소까지
// 아직 경로가 남아있을 때(격리 임박) vs 이미 끊겼을 때(격리 완료)를 구분해서 표시.
const EXAMPLE_ZONES = [
  { label: "예시 구역 A", buildingCount: 42, reason: "진입로 1개소가 토사 매몰로 두절", timeToIsolationMin: null },
  { label: "예시 구역 B", buildingCount: 17, reason: "우회로 없음 — 교량 침수 예상", timeToIsolationMin: 38 },
] satisfies { label: string; buildingCount: number; reason: string; timeToIsolationMin: number | null }[];

export default function IsolationPanel() {
  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-slate-400">
        §7(독창성 축 4, 신규 제안) — &ldquo;물이 여기까지 찼다&rdquo;가 아니라 &ldquo;이 마을은
        이제 대피소로 가는 길이 하나도 안 남았다&rdquo;를 도로망 그래프 연결성 분석으로
        증명한다. 산사태→하천범람→고립로 이어지는 재해 사슬의 마지막 고리.
      </p>

      <div className="rounded-lg border border-dashed border-fuchsia-800/40 bg-fuchsia-950/10 p-3 text-[11px] text-fuchsia-300/80">
        개념 미리보기 — networkx 그래프 연결성 계산이 아직 구현 전이라(HANDOFF.md §7, 트랙④ 소유)
        실시간 값이 아니다. 아래는 완성되면 어떤 화면이 나올지 보여주는 예시 시나리오.
      </div>

      <div className="space-y-2">
        {EXAMPLE_ZONES.map((z) => (
          <div key={z.label} className="rounded-xl border border-fuchsia-800/40 bg-fuchsia-950/20 p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-fuchsia-200">{z.label}</p>
              <span className="shrink-0 rounded-full bg-fuchsia-900/60 px-2 py-0.5 text-[10px] font-medium text-fuchsia-300">
                {z.timeToIsolationMin === null ? "이미 고립됨" : "고립 임박"}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-300">약 {z.buildingCount}가구 · 대피소 도달 가능 경로 0개</p>
            <p className="mt-1 text-xs text-slate-500">{z.reason}</p>
            <p className="mt-1.5 text-xs font-medium text-fuchsia-300">
              {z.timeToIsolationMin === null
                ? "고립까지 남은 시간: 0분 (이미 모든 경로 두절)"
                : `고립까지 남은 시간: 약 ${z.timeToIsolationMin}분 — 그 전에 대피 완료 필요`}
            </p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-slate-400">
        구현되면: 침수·토사 슬라이더를 움직일 때마다 위험 도로 구간을 제거하고 대피소까지
        역방향 도달가능성을 다시 계산 — 지도 위에 고립 구역이 마젠타색으로, time-to-isolation이
        짧을수록 더 급하게(점멸 등) 실시간 표시된다.
      </div>
    </div>
  );
}
