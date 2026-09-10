"use client";

import { useEffect, useState } from "react";
import type { EvacuationRoute } from "@/components/MapExplorer";
import { getEvacuationRoutes, type EvacuationRouteResult } from "@/lib/api";
import { diagnoseFailure } from "@/lib/backendDiagnosis";
import { DEMO_REGIONS, DEFAULT_REGION, type RegionKey } from "@/lib/demoShelters";

// Module E(대피소·경로 라우팅) — HANDOFF.md §6. 대피소 목록은 lib/demoShelters.ts의
// 지역별 공통 정의를 쓴다(region prop) — IsolationPanel·MapExplorer도 같은 목록
// 기준으로 계산해야 화면 간 앞뒤가 맞는다.

// 위치를 아직 못 받았을 때 보여줄 자리표시 값(contracts/module_e.example.json 형식
// 그대로) — 특정 대피소 ID에 종속되지 않으므로 어느 지역이든 그대로 쓴다.
const PLACEHOLDER_ETA = { carMin: 14.5, walkMin: 52.0, feasible: true } as const;

const CAR_KMH = 30; // 산간도로 실도로거리 보정을 반쯤 흡수한 가정 속도 — 실API 전 근사치
const WALK_KMH = 4; // §6.3
const TIME_BUDGET_MIN = 120; // contracts/module_e.example.json의 time_budget_hours 2.0

function haversineKm(a: [number, number], b: [number, number]): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

export default function EvacuationPanel({
  region = DEFAULT_REGION,
  onSelectRoute,
  onRequestMapPick,
  mapPickedOrigin,
}: {
  region?: RegionKey;
  onSelectRoute?: (route: EvacuationRoute | null) => void;
  // §6.8 폴백 ① — "지도에서 선택" 누르면 부모가 MapExplorer의 pickOrigin을 켜고,
  // 사용자가 지도를 클릭하면 부모가 mapPickedOrigin으로 좌표를 내려준다.
  onRequestMapPick?: () => void;
  mapPickedOrigin?: [number, number] | null;
}) {
  const SHELTERS = DEMO_REGIONS[region].shelters;
  const [origin, setOrigin] = useState<[number, number] | null>(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [awaitingMapPick, setAwaitingMapPick] = useState(false);
  const [backendResults, setBackendResults] = useState<Record<string, EvacuationRouteResult> | null>(null);
  const [backendLoading, setBackendLoading] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);

  useEffect(() => {
    if (!mapPickedOrigin) return;
    // 부모(MapExplorer)의 지도 클릭 이벤트로만 값이 바뀌는 외부 좌표라, 그걸 내부
    // origin 상태에 동기화하는 것 자체가 이 effect의 목적이다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOrigin(mapPickedOrigin);
    setLocError(null);
    setAwaitingMapPick(false);
  }, [mapPickedOrigin]);

  const requestMapPick = () => {
    setAwaitingMapPick(true);
    setLocError(null);
    onRequestMapPick?.();
  };

  // origin이 잡히면 실제 백엔드(module_e_routing, 네이버 Directions)로 차량 경로를
  // 조회한다. 실패(서버 미기동·API 키 문제 등)해도 화면이 멈추지 않도록 아래 rows에서
  // 이 결과가 없으면 기존 직선거리 근사로 조용히 폴백한다.
  useEffect(() => {
    if (!origin) {
      // origin이 풀리면 이전 좌표로 받아둔 경로 결과를 버린다 — 아래 rows와 렌더는
      // 전부 origin으로 가드돼 있어 당장 화면에 보이지는 않지만, 다음 origin이
      // 잡히는 순간 이전 좌표의 결과가 한 프레임 새어나오는 걸 막는 정리 작업이다.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBackendResults(null);
      setBackendError(null);
      return;
    }
    let cancelled = false;
    setBackendLoading(true);
    setBackendError(null);
    getEvacuationRoutes(
      { lon: origin[0], lat: origin[1] },
      SHELTERS.map((s) => ({ shelter_id: s.id, lon: s.lon, lat: s.lat, capacity: s.capacity })),
      TIME_BUDGET_MIN / 60
    )
      .then(({ results }) => {
        if (cancelled) return;
        const byId: Record<string, EvacuationRouteResult> = {};
        for (const r of results) byId[r.shelter_id] = r;
        setBackendResults(byId);
      })
      .catch(() => {
        if (cancelled) return;
        // 여기는 직선거리로 폴백하므로 화면이 멈추지는 않는다. 다만 "왜 실제 경로가
        // 아닌지"는 알려줘야 해서 원인을 확인해 덧붙인다(lib/backendDiagnosis.ts).
        setBackendError("실제 경로 조회 실패 — 직선거리 근사로 대체");
        diagnoseFailure("실제 경로 조회", "/evacuation-route")
          .then((detail) => {
            if (!cancelled) setBackendError(`${detail} 아래 값은 직선거리 근사입니다.`);
          })
          .catch(() => undefined);
      })
      .finally(() => {
        if (!cancelled) setBackendLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  const locate = () => {
    if (!navigator.geolocation) {
      setLocError("이 브라우저는 위치 확인을 지원하지 않아요 — 검색창으로 지역을 찾아주세요.");
      return;
    }
    setLocating(true);
    setLocError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setOrigin([pos.coords.longitude, pos.coords.latitude]);
        setLocating(false);
      },
      () => {
        setLocError("위치를 가져올 수 없어요 — 브라우저 위치 권한을 확인하거나 검색창으로 지역을 찾아주세요.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const allRows = SHELTERS.map((s) => {
    if (!origin) {
      return { ...s, ...PLACEHOLDER_ETA, distanceKm: null as number | null, real: false as const };
    }
    const backend = backendResults?.[s.id];
    if (backend) {
      return {
        ...s,
        carMin: backend.eta_min,
        walkMin: backend.modes.walk.eta_min,
        feasible: backend.time_feasible,
        distanceKm: null as number | null,
        real: !backend.fallback_used,
        routeLonlat: backend.route_lonlat,
      };
    }
    const distanceKm = haversineKm(origin, [s.lon, s.lat]);
    const carMin = (distanceKm / CAR_KMH) * 60;
    const walkMin = (distanceKm / WALK_KMH) * 60;
    return { ...s, carMin, walkMin, feasible: carMin <= TIME_BUDGET_MIN, distanceKm, real: false as const };
  }).sort((a, b) => a.carMin - b.carMin);

  // 대피소가 지역마다 최대 20곳까지 있어 전부 보여주면 리스트가 너무 길다(2026-09-10
  // 사용자 피드백) — 계산은 전체를 대상으로 하되(가장 가까운 곳을 정확히 알아야 하니까),
  // 화면엔 가까운 순 상위 5곳만 보여준다.
  const MAX_VISIBLE_SHELTERS = 5;
  const rows = allRows.slice(0, MAX_VISIBLE_SHELTERS);

  const select = (s: (typeof rows)[number]) => {
    setSelectedId(s.id);
    if (!origin) return;
    const path = "routeLonlat" in s ? s.routeLonlat : undefined;
    onSelectRoute?.({ origin, destination: [s.lon, s.lat], label: s.name, path });
  };

  // 대피소가 많을수록(예: 20곳) 네이버 응답이 다 오는 데 몇 초 걸리는데, 그 사이에
  // 사용자가 먼저 클릭하면 위 select()가 그 순간의 직선거리 근사를 지도에 영구히
  // 그려버린다(2026-09-10 사용자 피드백 — 도로를 안 따라가는 직선으로 보임). 이미
  // 골라둔 대피소의 실제 경로가 나중에 도착하면 자동으로 다시 그려서 업그레이드한다.
  useEffect(() => {
    if (!selectedId || !origin) return;
    const backend = backendResults?.[selectedId];
    if (!backend) return;
    const shelter = SHELTERS.find((s) => s.id === selectedId);
    if (!shelter) return;
    onSelectRoute?.({ origin, destination: [shelter.lon, shelter.lat], label: shelter.name, path: backend.route_lonlat });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendResults, selectedId]);

  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-slate-400">
        §5 Module E 확장 — 위험지역을 벗어난 가장 가까운 대피소까지 자동차/도보 이동시간을 계산해
        보여준다. &ldquo;네이버 지도 최적경로처럼&rdquo;이 사용자 요청 원문.
      </p>

      {!origin && (
        <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
          미리보기 — 아래 숫자는 위치를 아직 안 정해서 보여주는 고정 예시값이다. &ldquo;내 위치로
          찾기&rdquo;나 &ldquo;지도에서 선택&rdquo;을 누르면 실제 경로로 바뀐다.
        </div>
      )}
      {origin && backendLoading && (
        <div className="rounded-lg border border-dashed border-sky-800/40 bg-sky-950/10 p-3 text-[11px] text-sky-300/80">
          실제 도로 경로 조회 중…
        </div>
      )}
      {origin && !backendLoading && rows.some((r) => r.real) && (
        <div className="rounded-lg border border-dashed border-emerald-800/40 bg-emerald-950/10 p-3 text-[11px] text-emerald-300/80">
          네이버 Directions 실제 도로 경로 기준 — 차량 시간은 실경로, 도보 시간은 여전히
          직선거리 근사(공개 API에 도보 길찾기가 없음, HANDOFF.md §6.3).
        </div>
      )}
      {origin && !backendLoading && !rows.some((r) => r.real) && (
        <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
          {backendError ?? "실제 경로 API 응답 없음"} — 아래 숫자는 직선거리 근사 기반 예시값이다.
        </div>
      )}

      <div>
        <div className="flex gap-2">
          <button
            onClick={locate}
            disabled={locating}
            className="flex-1 rounded-lg border border-sky-700 bg-sky-950/30 py-2 text-xs font-medium text-sky-300 hover:bg-sky-950/60 disabled:opacity-50"
          >
            {locating ? "위치 확인 중…" : "내 위치로 찾기"}
          </button>
          <button
            onClick={requestMapPick}
            disabled={awaitingMapPick}
            className="flex-1 rounded-lg border border-white/15 bg-white/5 py-2 text-xs font-medium text-slate-200 hover:bg-white/10 disabled:opacity-50"
          >
            {awaitingMapPick ? "지도를 클릭하세요…" : "지도에서 선택"}
          </button>
        </div>
        {locError && <p className="mt-2 text-xs text-red-300">{locError}</p>}
        {origin && !locError && !awaitingMapPick && (
          <p className="mt-2 text-[11px] text-slate-500">
            선택한 위치 기준 직선거리 근사치로 계산했어요 — 대피소를 눌러 지도에 경로를 표시하세요.
          </p>
        )}
      </div>

      <div className="space-y-2">
        {rows.map((s) => (
          <button
            key={s.id}
            onClick={() => select(s)}
            className={`block w-full rounded-xl border p-3 text-left transition-colors ${
              s.feasible
                ? "border-white/10 bg-white/5 hover:bg-white/10"
                : "border-red-800/50 bg-red-950/20 hover:bg-red-950/30"
            } ${selectedId === s.id ? "ring-1 ring-sky-400" : ""}`}
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">{s.name}</p>
              <div className="flex shrink-0 gap-1">
                {origin && !s.real && (
                  <span
                    className="rounded-full bg-amber-900/60 px-2 py-0.5 text-[10px] font-medium text-amber-300"
                    title="이 대피소는 네이버 실도로 경로 조회에 실패해 직선거리 근사로 대체됐다"
                  >
                    근사
                  </span>
                )}
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    s.feasible ? "bg-emerald-900/60 text-emerald-300" : "bg-red-900/60 text-red-300"
                  }`}
                >
                  {s.feasible ? "도달 가능" : "도달 불가"}
                </span>
              </div>
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
          </button>
        ))}
        {allRows.length > MAX_VISIBLE_SHELTERS && (
          <p className="text-center text-[11px] text-slate-500">
            가까운 {MAX_VISIBLE_SHELTERS}곳만 표시 — 이 지역에 대피소 {allRows.length}곳 있음
          </p>
        )}
      </div>
    </div>
  );
}
