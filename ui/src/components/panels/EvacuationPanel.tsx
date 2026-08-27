// Module E(대피소·경로 라우팅) 확장판 미리보기 — HANDOFF.md §6.
// 카카오/네이버 길찾기 API 키가 아직 없어 실제 차량 경로는 못 붙였고, 아래 숫자는
// contracts/module_e.example.json(S001, eta_min 14.5)과 HANDOFF §6.6 제안 스키마의
// 예시값(walk 52.0)을 그대로 쓰고 나머지 후보는 같은 톤으로 손으로 채워 넣은 손 데모용
// 목업이다 — 실제 대피소 데이터·API 연동 전까지는 이 화면이 "무엇이 보여야 하는지"의
// 미리보기 역할만 한다(§6.7 착수 순서 1번: API 키 없이 뼈대부터).
interface ShelterMock {
  id: string;
  name: string;
  capacity: number;
  carMin: number;
  walkMin: number;
  feasible: boolean;
}

const SHELTERS: ShelterMock[] = [
  { id: "S001", name: "산청 상능마을회관", capacity: 200, carMin: 14.5, walkMin: 52.0, feasible: true },
  { id: "S002", name: "생비량초등학교", capacity: 300, carMin: 9.8, walkMin: 31.0, feasible: true },
  { id: "S003", name: "산청군청 대피소", capacity: 500, carMin: 26.4, walkMin: 88.0, feasible: false },
];

export default function EvacuationPanel() {
  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-slate-400">
        §5 Module E 확장 — 위험지역을 벗어난 가장 가까운 대피소까지 자동차/도보 이동시간을 계산해
        보여준다. &ldquo;네이버 지도 최적경로처럼&rdquo;이 사용자 요청 원문.
      </p>

      <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
        미리보기 — 카카오/네이버 길찾기 API 키 연동 전이라 아래 숫자는 실제 경로가 아니라
        직선거리 근사 기반 예시값이다(HANDOFF.md §6). 실제 키가 들어오면 이 화면 그대로 실데이터로
        교체된다.
      </div>

      <div className="space-y-2">
        {SHELTERS.map((s) => (
          <div
            key={s.id}
            className={`rounded-xl border p-3 ${
              s.feasible ? "border-white/10 bg-white/5" : "border-red-800/50 bg-red-950/20"
            }`}
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">{s.name}</p>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  s.feasible ? "bg-emerald-900/60 text-emerald-300" : "bg-red-900/60 text-red-300"
                }`}
              >
                {s.feasible ? "도달 가능" : "도달 불가"}
              </span>
            </div>
            <div className="mt-2 flex gap-4 text-xs">
              <span>
                <span className="font-semibold text-sky-300">차량</span>{" "}
                <span className="text-slate-300">{s.carMin.toFixed(1)}분</span>
              </span>
              <span>
                <span className="font-semibold text-amber-300">도보</span>{" "}
                <span className="text-slate-300">{s.walkMin.toFixed(0)}분</span>
              </span>
              <span className="text-slate-500">수용인원 {s.capacity}명</span>
            </div>
            {!s.feasible && (
              <p className="mt-2 text-xs font-medium text-red-300">
                ⚠ 제한시간 내 도달 불가 — 더 가까운 대피소나 안전지대로 즉시 이동하세요
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
