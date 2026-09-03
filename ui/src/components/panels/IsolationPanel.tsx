"use client";

import { useState } from "react";
import { checkIsolation, type IsolationCheckResult } from "@/lib/api";

// §7(독창성 축 4) — 도로망 그래프에서 위험 구간을 제거한 뒤 대피소까지 도달 가능한
// 경로가 하나도 안 남는 건물을 찾는다. module_e_routing/isolation.py가 VWorld
// 도로망(LT_L_MOCTLINK)·건물(LT_C_SPBD) 실데이터로 networkx 그래프를 만들어 계산한다.
//
// 지금은 EvacuationPanel과 같은 산청 상능마을 대피소 2곳(S001·S002) 주변 bbox로
// 고정돼 있다 — 화면 뷰포트 연동은 다음 단계(TODO).
const DEMO_BBOX: [number, number, number, number] = [128.045, 35.343, 128.065, 35.358];
const DEMO_SHELTERS = [
  { lon: 128.057, lat: 35.349 },
  { lon: 128.052, lat: 35.353 },
];
// 마을 중앙 진입로를 세로로 끊는 위험폴리곤 — "위험 시나리오 적용" 버튼용 데모 지오메트리.
// 실제 서비스에서는 Module A/B의 토사·침수 폴리곤이 여기 들어가야 한다(TODO).
const DEMO_HAZARD: GeoJSON.Polygon = {
  type: "Polygon",
  coordinates: [
    [
      [128.054, 35.343],
      [128.056, 35.343],
      [128.056, 35.358],
      [128.054, 35.358],
      [128.054, 35.343],
    ],
  ],
};

export default function IsolationPanel({
  onResult,
  onFocusCluster,
}: {
  onResult?: (result: IsolationCheckResult | null) => void;
  // 목록에서 구역을 클릭하면 그 구역의 bbox로 지도를 이동시켜달라는 요청.
  onFocusCluster?: (bbox: [number, number, number, number]) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IsolationCheckResult | null>(null);
  const [scenarioApplied, setScenarioApplied] = useState(false);

  const run = async (applyHazard: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const r = await checkIsolation(DEMO_BBOX, DEMO_SHELTERS, applyHazard ? DEMO_HAZARD : undefined);
      setResult(r);
      setScenarioApplied(applyHazard);
      onResult?.(r);
    } catch {
      setError("고립 분석 실패 — 백엔드(VWorld 연동)가 켜져 있는지 확인해주세요.");
      onResult?.(null);
    } finally {
      setLoading(false);
    }
  };

  const clusters = result?.isolated_areas.features ?? [];

  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-slate-400">
        §7(독창성 축 4) — &ldquo;물이 여기까지 찼다&rdquo;가 아니라 &ldquo;이 마을은
        이제 대피소로 가는 길이 하나도 안 남았다&rdquo;를 실제 도로망 그래프 연결성
        분석으로 증명한다. VWorld 실도로·실건물 데이터 기반 실계산이다(개념 미리보기 아님).
      </p>

      <div className="flex gap-2">
        <button
          onClick={() => run(false)}
          disabled={loading}
          className="flex-1 rounded-lg border border-sky-700 bg-sky-950/30 py-2 text-xs font-medium text-sky-300 hover:bg-sky-950/60 disabled:opacity-50"
        >
          {loading && !scenarioApplied ? "계산 중…" : "현재 상태 확인"}
        </button>
        <button
          onClick={() => run(true)}
          disabled={loading}
          className="flex-1 rounded-lg border border-fuchsia-700 bg-fuchsia-950/30 py-2 text-xs font-medium text-fuchsia-300 hover:bg-fuchsia-950/60 disabled:opacity-50"
        >
          {loading && scenarioApplied ? "계산 중…" : "위험 시나리오 적용"}
        </button>
      </div>

      {error && <p className="text-xs text-red-300">{error}</p>}

      {!result && !loading && !error && (
        <div className="rounded-lg border border-dashed border-fuchsia-800/40 bg-fuchsia-950/10 p-3 text-[11px] text-fuchsia-300/80">
          버튼을 눌러 산청 상능마을 대피소 2곳 기준으로 실제 도로망 연결성을 계산한다.
          &ldquo;현재 상태&rdquo;는 위험지역 없이 도로가 원래 얼마나 끊겨있는지(데이터
          자체의 한계), &ldquo;위험 시나리오&rdquo;는 마을 진입로가 끊겼다고 가정했을 때다.
        </div>
      )}

      {result && (
        <>
          <div
            className={`rounded-xl border p-3 ${
              scenarioApplied ? "border-fuchsia-800/40 bg-fuchsia-950/20" : "border-white/10 bg-white/5"
            }`}
          >
            <p className={`text-sm font-semibold ${scenarioApplied ? "text-fuchsia-200" : "text-slate-200"}`}>
              고립 건물 {result.isolated_building_count}채 · {clusters.length}개 구역
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {scenarioApplied ? "마을 진입로 두절 가정 — 대피소 도달 가능 경로 0개인 건물" : "위험지역 없음 — 그래도 도로 데이터 자체의 연결 공백으로 일부는 고립으로 잡힐 수 있음"}
            </p>
            {result.warnings.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-[11px] text-amber-300/80">
                {result.warnings.map((w, i) => (
                  <li key={i}>⚠ {w}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-2">
            {clusters
              .slice()
              .sort((a, b) => (b.properties?.building_count ?? 0) - (a.properties?.building_count ?? 0))
              .slice(0, 8)
              .map((f, i) => {
                const bbox = f.properties?.bbox as [number, number, number, number] | undefined;
                return (
                  <button
                    key={i}
                    onClick={() => bbox && onFocusCluster?.(bbox)}
                    disabled={!bbox}
                    className="block w-full rounded-xl border border-fuchsia-800/40 bg-fuchsia-950/20 p-3 text-left transition-colors hover:bg-fuchsia-950/40 disabled:cursor-default disabled:hover:bg-fuchsia-950/20"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-fuchsia-200">고립 구역 {i + 1}</p>
                      <span className="shrink-0 rounded-full bg-fuchsia-900/60 px-2 py-0.5 text-[10px] font-medium text-fuchsia-300">
                        {f.geometry.type === "Point" ? "단독 건물" : "군집"}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-300">약 {f.properties?.building_count}채 · 대피소 도달 가능 경로 0개</p>
                    <p className="mt-1 text-[11px] text-fuchsia-400/70">지도에서 위치 보기 →</p>
                  </button>
                );
              })}
            {clusters.length > 8 && <p className="text-center text-[11px] text-slate-500">외 {clusters.length - 8}개 구역 더 있음 — 지도에서 전체 확인</p>}
          </div>
        </>
      )}

      <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-slate-400">
        지도 위 마젠타 영역이 고립 구역이다. 지금은 산청 데모 지역·고정 대피소 2곳
        기준이고, 침수·토사 슬라이더 값을 실제 위험폴리곤으로 자동 연동하는 건 다음
        단계(TODO) — 지금은 &ldquo;위험 시나리오 적용&rdquo; 버튼이 데모용 고정
        시나리오를 대신 보여준다.
      </div>
    </div>
  );
}
