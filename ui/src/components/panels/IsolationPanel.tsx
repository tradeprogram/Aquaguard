"use client";

import { useEffect, useRef, useState } from "react";
import { checkIsolation, getSnapshotIsolation, type IsolationCheckResult } from "@/lib/api";
import { diagnoseFailure } from "@/lib/backendDiagnosis";
import { DEMO_REGIONS, DEFAULT_REGION, type RegionKey } from "@/lib/demoShelters";

// §7 — 도로망 그래프에서 위험 구간을 제거한 뒤 대피소까지 도달 가능한
// 경로가 하나도 안 남는 건물을 찾는다. module_e_routing/isolation.py가 VWorld
// 도로망(LT_L_MOCTLINK)·건물(LT_C_SPBD) 실데이터로 networkx 그래프를 만들어 계산한다.
// 대피소 목록·bbox는 lib/demoShelters.ts 지역별 공통 정의(EvacuationPanel·MapExplorer와 동일).

// "위험 시나리오 적용" 버튼용 데모 지오메트리 — bbox 한가운데를 세로로 가르는 좁고 긴
// 폴리곤(진입로가 끊긴 상황을 흉내). 지역마다 bbox 위치가 다르므로 고정 좌표 대신
// 현재 지역의 bbox에서 매번 계산한다.
//
// scripts/build_demo_snapshot.py의 _demo_hazard가 **같은 식**으로 이 폴리곤을 만든다
// (폭 = 경도폭의 2%). 한쪽만 고치면 저장본이 안 맞아 매번 다시 계산하게 되므로 같이 고칠 것.
//
// 지도의 실제 위험영역(시각별 산사태 + 침수)은 MapExplorer.tsx가 시간 스크러버에
// 맞춰 자동으로 /isolation-check에 넘긴다 — 이 버튼은 그것과 별개로, 이 화면만으로
// 빠르게 확인해볼 수 있는 수동 시나리오다.
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

// 계산 결과 캐시 — 지역·시나리오 조합 하나가 키다.
// 패널을 닫으면 컴포넌트가 언마운트되면서 결과가 통째로 날아가고, 다시 열면
// VWorld 도로·건물을 처음부터 다시 받아야 해서 한참 걸렸다. 캐시를 page.tsx가
// 들고 있으면 패널을 닫았다 열어도, 두 시나리오를 오가도 즉시 나온다.
// base=위험 없음, hazard=데모용 가정 띠, flood=Module B의 실제 침수범위(사전계산본만 있다).
export type IsolationScenario = "base" | "hazard" | "flood";
export type IsolationCacheKey = `${RegionKey}:${IsolationScenario}`;
export type IsolationCache = Partial<Record<IsolationCacheKey, IsolationCheckResult>>;

export function isolationCacheKey(region: RegionKey, scenario: IsolationScenario | boolean): IsolationCacheKey {
  const name: IsolationScenario = typeof scenario === "boolean" ? (scenario ? "hazard" : "base") : scenario;
  return `${region}:${name}`;
}

// 실제 침수범위로 계산한 사전계산본이 있는 지역 — 그 범위가 산청 AOI(경호강 일대)뿐이라서다.
const FLOOD_SCENARIO_REGIONS: RegionKey[] = ["sancheong_all"];

export default function IsolationPanel({
  region = DEFAULT_REGION,
  cache,
  onCache,
  shown,
  onShownChange,
  onResult,
  onFocusCluster,
}: {
  region?: RegionKey;
  // 계산 결과 보관소(page.tsx 소유) — 패널 언마운트를 견딘다.
  cache?: IsolationCache;
  onCache?: (key: IsolationCacheKey, result: IsolationCheckResult) => void;
  // 지금 화면에 띄워둔 조합. 닫았다 열어도 보던 걸 그대로 다시 보여준다.
  shown?: IsolationCacheKey | null;
  onShownChange?: (key: IsolationCacheKey | null) => void;
  onResult?: (result: IsolationCheckResult | null) => void;
  // 목록에서 구역을 클릭하면 그 구역의 bbox로 지도를 이동시켜달라는 요청.
  onFocusCluster?: (bbox: [number, number, number, number]) => void;
}) {
  const { shelters, isolationBbox } = DEMO_REGIONS[region];
  const shelterLonLat = shelters.map(({ lon, lat }) => ({ lon, lat }));
  const [loading, setLoading] = useState<null | IsolationScenario>(null); // null=대기, 값=계산중인 시나리오
  const [error, setError] = useState<string | null>(null);

  // 지역을 바꾸면 이전 지역 결과는 더 보여주지 않는다 — 캐시에는 남아 있어서
  // 그 지역으로 돌아오면 다시 즉시 뜬다.
  const activeKey = shown && shown.startsWith(`${region}:`) ? shown : null;
  const result = activeKey ? cache?.[activeKey] ?? null : null;
  const scenarioApplied = activeKey?.endsWith(":hazard") ?? false;
  const floodApplied = activeKey?.endsWith(":flood") ?? false;
  const hasFlood = FLOOD_SCENARIO_REGIONS.includes(region);

  const run = async (scenario: IsolationScenario) => {
    const applyHazard = scenario === "hazard";
    const key = isolationCacheKey(region, scenario);
    const hit = cache?.[key];
    if (hit) {
      // 이미 계산해둔 조합 — 다시 부르지 않는다.
      onShownChange?.(key);
      onResult?.(hit);
      setError(null);
      return;
    }

    setLoading(scenario);
    setError(null);
    try {
      // 사전계산본이 있으면 그걸 쓴다(같은 bbox·같은 대피소 수일 때만).
      const snap = await getSnapshotIsolation(key, isolationBbox, shelterLonLat.length);
      // 실제 침수 시나리오는 저장본으로만 제공된다 — 침수범위(래스터 폴리곤)가 브라우저에는 없고
      // 서버 API도 아직 그걸 받지 않으므로, 저장본이 없으면 아무 것도 지어내지 않고 실패로 둔다.
      if (scenario === "flood" && !snap) throw new Error("no flood snapshot");
      const r =
        snap ??
        (await checkIsolation(
          isolationBbox,
          shelterLonLat,
          applyHazard ? buildDemoHazard(isolationBbox) : undefined
        ));
      onCache?.(key, r);
      onShownChange?.(key);
      onResult?.(r);
    } catch {
      // 고정 문구 대신 /health를 찔러 원인을 구분한다 — 서버 미기동인지, 배포가
      // 뒤처져 엔드포인트가 없는 건지, 요청 자체의 문제인지(lib/backendDiagnosis.ts).
      setError(await diagnoseFailure("고립 분석", "/isolation-check"));
      onShownChange?.(null);
      onResult?.(null);
    } finally {
      setLoading(null);
    }
  };

  // 패널을 다시 열면 목록은 캐시에서 바로 복원되지만 지도 레이어는 그렇지 않다 —
  // onResult 는 run() 안에서만 불리기 때문이다. 그사이 시간 스크러버가 같은 레이어를
  // 덮어썼을 수도 있어서, 보여주는 조합이 바뀔 때마다 지도에 한 번 다시 밀어준다.
  const pushedRef = useRef<IsolationCacheKey | null>(null);
  useEffect(() => {
    if (!activeKey || !result) return;
    if (pushedRef.current === activeKey) return;
    pushedRef.current = activeKey;
    onResult?.(result);
  }, [activeKey, result, onResult]);

  const clusters = result?.isolated_areas.features ?? [];
  const cached = (scenario: IsolationScenario) => Boolean(cache?.[isolationCacheKey(region, scenario)]);

  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-slate-400">
&ldquo;물이 여기까지 찼다&rdquo;가 아니라 &ldquo;이 마을은 이제 대피소로 가는 길이
        하나도 안 남았다&rdquo;를 실제 도로망 그래프 연결성 분석으로 증명한다.
        VWorld 실도로·실건물 데이터 기반 실계산이다.
      </p>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => run("base")}
          disabled={loading !== null}
          className={`flex-1 rounded-lg border py-2 text-xs font-medium disabled:opacity-50 ${
            activeKey && !scenarioApplied && !floodApplied
              ? "border-sky-500 bg-sky-900/50 text-sky-200"
              : "border-sky-700 bg-sky-950/30 text-sky-300 hover:bg-sky-950/60"
          }`}
        >
          {loading === "base" ? "계산 중…" : "현재 상태 확인"}
          {cached("base") && loading === null && <span className="ml-1 text-[10px] opacity-60">저장됨</span>}
        </button>
        <button
          onClick={() => run("hazard")}
          disabled={loading !== null}
          className={`flex-1 rounded-lg border py-2 text-xs font-medium disabled:opacity-50 ${
            scenarioApplied
              ? "border-fuchsia-500 bg-fuchsia-900/50 text-fuchsia-200"
              : "border-fuchsia-700 bg-fuchsia-950/30 text-fuchsia-300 hover:bg-fuchsia-950/60"
          }`}
        >
          {loading === "hazard" ? "계산 중…" : "위험 시나리오 적용"}
          {cached("hazard") && loading === null && <span className="ml-1 text-[10px] opacity-60">저장됨</span>}
        </button>
        {hasFlood && (
          <button
            onClick={() => run("flood")}
            disabled={loading !== null}
            className={`flex-1 rounded-lg border py-2 text-xs font-medium disabled:opacity-50 ${
              floodApplied
                ? "border-cyan-400 bg-cyan-900/50 text-cyan-100"
                : "border-cyan-700 bg-cyan-950/30 text-cyan-300 hover:bg-cyan-950/60"
            }`}
          >
            {loading === "flood" ? "불러오는 중…" : "침수 반영"}
            {cached("flood") && loading === null && <span className="ml-1 text-[10px] opacity-60">저장됨</span>}
          </button>
        )}
      </div>

      {error && <p className="text-xs text-red-300">{error}</p>}

      {!result && loading === null && !error && (
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
              floodApplied
                ? "border-cyan-700/50 bg-cyan-950/20"
                : scenarioApplied
                  ? "border-fuchsia-800/40 bg-fuchsia-950/20"
                  : "border-white/10 bg-white/5"
            }`}
          >
            <p className={`text-sm font-semibold ${scenarioApplied ? "text-fuchsia-200" : "text-slate-200"}`}>
              고립 건물 {result.isolated_building_count}채 · {clusters.length}개 구역
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {floodApplied
                ? "실제 침수(Module B, 수심 0.3m 이상)에 잠기는 도로를 끊었을 때 — 대피소 도달 가능 경로 0개인 건물"
                : scenarioApplied ? "마을 진입로 두절 가정 — 대피소 도달 가능 경로 0개인 건물" : "위험지역 없음 — 그래도 도로 데이터 자체의 연결 공백으로 일부는 고립으로 잡힐 수 있음"}
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
        지도 위 마젠타 영역이 고립 구역이다. {DEMO_REGIONS[region].label} 대피소{" "}
        {shelters.length}곳 기준. 시간 스크러버를 움직이면 그 시각의 침수·산사태 위험영역
        기준으로 지도 쪽에서 자동으로도 재계산된다 — 이 버튼은 그것과 별개로 이 화면만으로
        빠르게 확인해보는 수동 시나리오다.
        한 번 계산한 결과는 저장해두므로 패널을 닫았다 열거나 두 시나리오를 오가도
        다시 기다리지 않는다.
      </div>
    </div>
  );
}
