"use client";

import { useState } from "react";
import { checkIsolation, type IsolationCheckResult } from "@/lib/api";
import { diagnoseFailure } from "@/lib/backendDiagnosis";
import { DEMO_REGIONS, DEFAULT_REGION, type RegionKey } from "@/lib/demoShelters";

// §7(독창성 축 4) — 도로망 그래프에서 위험 구간을 제거한 뒤 대피소까지 도달 가능한
// 경로가 하나도 안 남는 건물을 찾는다. module_e_routing/isolation.py가 VWorld
// 도로망(LT_L_MOCTLINK)·건물(LT_C_SPBD) 실데이터로 networkx 그래프를 만들어 계산한다.
// 대피소 목록·bbox는 lib/demoShelters.ts 지역별 공통 정의(EvacuationPanel·MapExplorer와 동일).

// "위험 시나리오 적용" 버튼용 데모 지오메트리 — bbox 한가운데를 세로로 가르는 좁고 긴
// 폴리곤(진입로가 끊긴 상황을 흉내). 지역마다 bbox 위치가 다르므로 고정 좌표 대신
// 현재 지역의 bbox에서 매번 계산한다 — 실제 침수·토사 슬라이더 값은 MapExplorer.tsx가
// 자동으로 /isolation-check에 넘긴다(이 버튼은 슬라이더 없이도 화면 단독으로 테스트해볼
// 수 있게 남겨둔 수동 트리거).
function buildDemoHazard(bbox: [number, number, number, number]): GeoJSON.Polygon {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const midLon = (minLon + maxLon) / 2;
  const halfWidth = (maxLon - minLon) * 0.02;
  return {
    type: "Polygon",
    coordinates: [
      [
        [midLon - halfWidth, minLat],
        [midLon + halfWidth, minLat],
        [midLon + halfWidth, maxLat],
        [midLon - halfWidth, maxLat],
        [midLon - halfWidth, minLat],
      ],
    ],
  };
}

export default function IsolationPanel({
  region = DEFAULT_REGION,
  onResult,
  onFocusCluster,
}: {
  region?: RegionKey;
  onResult?: (result: IsolationCheckResult | null) => void;
  // 목록에서 구역을 클릭하면 그 구역의 bbox로 지도를 이동시켜달라는 요청.
  onFocusCluster?: (bbox: [number, number, number, number]) => void;
}) {
  const { shelters, isolationBbox } = DEMO_REGIONS[region];
  const shelterLonLat = shelters.map(({ lon, lat }) => ({ lon, lat }));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IsolationCheckResult | null>(null);
  const [scenarioApplied, setScenarioApplied] = useState(false);

  const run = async (applyHazard: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const r = await checkIsolation(isolationBbox, shelterLonLat, applyHazard ? buildDemoHazard(isolationBbox) : undefined);
      setResult(r);
      setScenarioApplied(applyHazard);
      onResult?.(r);
    } catch {
      // 고정 문구 대신 /health를 찔러 원인을 구분한다 — 서버 미기동인지, 배포가
      // 뒤처져 엔드포인트가 없는 건지, 요청 자체의 문제인지(lib/backendDiagnosis.ts).
      setError(await diagnoseFailure("고립 분석", "/isolation-check"));
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
          버튼을 눌러 {DEMO_REGIONS[region].label} 대피소 {shelters.length}곳 기준으로 실제 도로망 연결성을 계산한다.
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
        지도 위 마젠타 영역이 고립 구역이다. 지금은 {DEMO_REGIONS[region].label} 데모
        지역·고정 대피소 {shelters.length}곳 기준. 지도 오른쪽 위 침수·토사 슬라이더를
        움직이면 그 값 기준으로 자동으로도 재계산된다 — 이 버튼은 슬라이더 없이 이
        화면만으로 빠르게 테스트해볼 수 있는 별도 데모 시나리오다.
      </div>
    </div>
  );
}
