"use client";

import { useEffect, useState } from "react";
import type { EvacuationRoute } from "@/components/MapExplorer";

// Module E(대피소·경로 라우팅) 확장판 미리보기 — HANDOFF.md §6.
// 카카오/네이버 길찾기 API 키가 아직 없어 실제 도로 경로는 못 붙였다 — "내 위치로
// 찾기"를 누르면 브라우저 Geolocation(§6.8)으로 받은 실제 좌표에서 아래 대피소들까지
// 직선거리(하버사인) ÷ 가정 속도로 근사 계산한다(§6.3과 같은 원칙). 누르기 전엔
// contracts/module_e.example.json 기준 고정 예시값을 그대로 보여준다.
interface Shelter {
  id: string;
  name: string;
  lon: number;
  lat: number;
  capacity: number;
}

// 산청 상능마을(트리거 지점) 근처에 손으로 넣은 대피소 후보 — HANDOFF §6.2. S003은
// 실제 산청군청(산청읍) 좌표라 일부러 멀어서 "도달 불가" 사례를 보여준다.
const SHELTERS: Shelter[] = [
  { id: "S001", name: "산청 상능마을회관", lon: 128.057, lat: 35.349, capacity: 200 },
  { id: "S002", name: "생비량초등학교", lon: 128.052, lat: 35.353, capacity: 300 },
  { id: "S003", name: "산청군청 대피소", lon: 127.900325, lat: 35.40737, capacity: 500 },
];

// 위치를 아직 못 받았을 때 보여줄 고정 데모 값 — contracts/module_e.example.json
// (S001, eta_min 14.5)과 HANDOFF §6.6 제안 스키마 예시값(walk 52.0) 그대로.
const DEMO_ETA: Record<string, { carMin: number; walkMin: number; feasible: boolean }> = {
  S001: { carMin: 14.5, walkMin: 52.0, feasible: true },
  S002: { carMin: 9.8, walkMin: 31.0, feasible: true },
  S003: { carMin: 26.4, walkMin: 88.0, feasible: false },
};

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
  onSelectRoute,
  onRequestMapPick,
  mapPickedOrigin,
}: {
  onSelectRoute?: (route: EvacuationRoute | null) => void;
  // §6.8 폴백 ① — "지도에서 선택" 누르면 부모가 MapExplorer의 pickOrigin을 켜고,
  // 사용자가 지도를 클릭하면 부모가 mapPickedOrigin으로 좌표를 내려준다.
  onRequestMapPick?: () => void;
  mapPickedOrigin?: [number, number] | null;
}) {
  const [origin, setOrigin] = useState<[number, number] | null>(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [awaitingMapPick, setAwaitingMapPick] = useState(false);

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

  const rows = SHELTERS.map((s) => {
    if (!origin) {
      return { ...s, ...DEMO_ETA[s.id], distanceKm: null as number | null };
    }
    const distanceKm = haversineKm(origin, [s.lon, s.lat]);
    const carMin = (distanceKm / CAR_KMH) * 60;
    const walkMin = (distanceKm / WALK_KMH) * 60;
    return { ...s, carMin, walkMin, feasible: carMin <= TIME_BUDGET_MIN, distanceKm };
  }).sort((a, b) => a.carMin - b.carMin);

  const select = (s: (typeof rows)[number]) => {
    setSelectedId(s.id);
    if (origin) onSelectRoute?.({ origin, destination: [s.lon, s.lat], label: s.name });
  };

  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-slate-400">
        §5 Module E 확장 — 위험지역을 벗어난 가장 가까운 대피소까지 자동차/도보 이동시간을 계산해
        보여준다. &ldquo;네이버 지도 최적경로처럼&rdquo;이 사용자 요청 원문.
      </p>

      <div className="rounded-lg border border-dashed border-amber-800/40 bg-amber-950/10 p-3 text-[11px] text-amber-300/80">
        미리보기 — 카카오/네이버 길찾기 API 키 연동 전이라 아래 숫자는 실제 도로 경로가 아니라
        직선거리 근사 기반 예시값이다(HANDOFF.md §6). 실제 키가 들어오면 이 화면 그대로 실데이터로
        교체된다.
      </div>

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
          </button>
        ))}
      </div>
    </div>
  );
}
