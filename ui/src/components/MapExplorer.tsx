"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type ExpressionSpecification,
  type GeoJSONSource,
  type MapGeoJSONFeature,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import buffer from "@turf/buffer";
import centroid from "@turf/centroid";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import type { Feature, FeatureCollection, LineString, MultiLineString, Polygon, MultiPolygon } from "geojson";
import {
  API_BASE,
  SANGCHEONG_DEMO_INPUT,
  checkIsolation,
  getAlertGeojson,
  getAlertTimeline,
  getBoundaries,
  getVWorldBuildings,
  getVWorldRivers,
  getVWorldRoads,
  searchAdmin,
  tileBase,
  TIMELINE_ROUTE,
  type AdminLevel,
  type AdminSearchResult,
  type AlertTimeline,
} from "@/lib/api";
import { diagnoseFailure } from "@/lib/backendDiagnosis";
import { DEFAULT_REGION, DEMO_REGIONS, type RegionKey } from "@/lib/demoShelters";
import { useSlowLoading } from "@/lib/useSlowLoading";

// 산청군 생비량면 — data/vector/adm_dong_5179.geojson 실측 centroid. 초기 카메라 위치일
// 뿐, 이제 이 페이지는 검색으로 어디든 이동할 수 있는 범용 3D 지도다(고정 AOI 아님).
// 2026-08-29: pitch가 높을수록(원래 60) 원근 투영상 지평선까지 훨씬 넓은 면적이
// 화면에 잡혀 그만큼 더 많은 타일을 한꺼번에 요청하게 된다(§ maxPitch 주석의 실측
// 참조) — flyTo·fitBounds로 프로그램적으로 카메라를 놓는 모든 곳에서 이 값 하나만
// 쓰도록 통일해 나중에 조정하기 쉽게 함.
const DEFAULT_PITCH = 50;

// 2026-08-29: pitch·zoom이 겹치면 위성 래스터 타일 요청이 한꺼번에 수백 개까지
// 튄다(§ maxPitch 주석) — "동시 요청 수를 줄이면 덜 몰릴 것"이라 예상하고
// setMaxParallelImageRequests(8)을 넣어 실측했더니 오히려 11.98초로 더 느려졌다
// (동시성 제한 없이는 3.8~4.5초) — 이 환경에서는 총 타일 수를 줄이는 것(pitch
// 상한 인하)만 효과가 있고, 동시 요청 수 자체를 조르는 건 역효과라 뺐다.
const INITIAL_CENTER: [number, number] = [128.0559, 35.3505];
const INITIAL_BOUNDS: [[number, number], [number, number]] = [
  [128.00826, 35.30385],
  [128.1152, 35.39634],
];

// 2026-08-28: 이 앱은 어차피 대한민국 전용(위성영상은 V-World, 행정경계·건물·도로도
// 전부 국내 소스 — §2.6)인데 지도에 maxBounds 제한이 없어서 줌아웃하면 전세계가
// 다 보였다. 전세계 뷰에서는 osm_vectors(전세계 벡터타일)·라벨 래스터 타일이 한
// 화면에 훨씬 많이 잡혀 요청·렌더 부하가 커지고, 화면 밖 지역은 애초에 아무 데이터도
// 없어 회색 배경만 그려진다 — 렉의 상당 부분이 여기서 온다. 카메라가 이 범위
// 밖으로 못 나가게 막으면 그 낭비가 원천 차단된다.
//
// 값은 손으로 어림한 게 아니라 실제 행정경계 데이터(data/vector/adm_sido_5179.geojson,
// 전국 17개 시도 전부 포함 확인됨)를 4326으로 재투영해 total_bounds를 계산한 값에
// 여유(약 0.1~0.2°)를 더한 것 — [124.60971768, 33.11560188, 131.87278315, 38.61357533]
// (2026-08-28 계산). 제주·독도까지 포함해서 전국이 다 보이는 게 맞다.
const SOUTH_KOREA_BOUNDS: [[number, number], [number, number]] = [
  [124.4, 32.9],
  [132.0, 38.8],
];

// 산청·서울 AOI 정적 벡터타일(2026-08-28, scripts/fetch_aoi_data.py +
// ui/scripts/build_vector_tiles.mjs) — 실시간 V-World 뷰포트 쿼리는 10km² 한도
// 때문에 패닝할 때마다 데이터가 깜빡이는 근본적 한계가 있다(§ vworld-rivers 주석).
// 이 두 지역은 "피해규모 재현"의 데모 AOI라 신뢰성이 최우선이므로, 아예 통째로
// 미리 받아 정적 파일로 박아두고 실시간 API 의존성 자체를 없앤다. 경계는 손으로
// 어림한 게 아니라 실제 행정경계(data/vector/adm_sigungu_5179.geojson·
// adm_sido_5179.geojson)를 4326으로 재투영한 total_bounds.
// 2026-09-05: 서울 AOI를 시 전역(605km², 43개 시군구가 bbox에 걸림)에서 강남구·서초구
// (84km²)로 좁혔다. 전역 bbox는 데모가 실제로 다루는 범위보다 훨씬 넓어 노출자산·경로
// 같은 파이프라인을 붙이기에 무거웠다.
// 2026-09-20: 다시 강남구만으로 좁혔다(39km²). 서초는 산청·강남과 똑같은 "모형 없는
// 지역"이라 화면에 새로 보여주는 게 없는데 정적 타일만 그만큼 더 들고 있었다.
//
// 이 bbox는 소스의 `bounds`로 그대로 들어가므로 MapLibre는 범위 밖 타일을 아예
// 요청하지 않는다 — 좁히면 그 바깥 타일은 디스크에만 남는 죽은 파일이 된다.
// 실제로 그래서 시 전역 시절 타일 411MB가 서빙되지 않은 채 남아 있었고, 이번에
// 강남 범위 밖 444MB를 전부 지웠다(범위를 다시 넓히려면 scripts/fetch_aoi_satellite.py와
// ui/scripts/build_vector_tiles.mjs로 재생성해야 한다).
const AOI_KEYS = ["sancheong", "seoul"] as const;
type AOIKey = (typeof AOI_KEYS)[number];
const AOI_BOUNDS: Record<AOIKey, [number, number, number, number]> = {
  sancheong: [127.688782, 35.219031, 128.114735, 35.576211],
  // 강남구 total_bounds(data/vector/adm_sigungu_5179.geojson을 4326으로 재투영)
  seoul: [127.008577, 37.456219, 127.124207, 37.535823],
};

function getActiveAOI(lng: number, lat: number): AOIKey | null {
  for (const key of AOI_KEYS) {
    const [minLon, minLat, maxLon, maxLat] = AOI_BOUNDS[key];
    if (lng >= minLon && lng <= maxLon && lat >= minLat && lat <= maxLat) return key;
  }
  return null;
}

// build_vector_tiles.mjs의 JOBS 배열과 반드시 일치해야 하는 값(z 범위가 다르면
// 없는 타일을 요청하게 됨).
const AOI_TILE_ZOOM = {
  buildings: { minzoom: 10, maxzoom: 16 },
  roads: { minzoom: 9, maxzoom: 16 },
  landcover: { minzoom: 8, maxzoom: 15 },
};

// scripts/fetch_aoi_satellite.py의 ZOOM_MIN/ZOOM_MAX와 반드시 일치해야 함.
// z17~18은 타일 수가 기하급수적(두 지역 합쳐 9만 개+)이라 z16까지만 미리 받았다 —
// 래스터 소스는 maxzoom을 넘는 줌에서 마지막 유효 타일을 자동으로 확대해서 쓰기
// 때문에(§satellite 소스 참고) 그 이상 줌에서도 추가 네트워크 요청 없이 커버된다.
const AOI_SATELLITE_ZOOM = { minzoom: 6, maxzoom: 16 };

// 환경부 세분류 토지피복도(L2_CODE, 20개 범주 — 산청·서울 데이터에 실제 등장하는
// 값만) 색상. 위성사진 위에 반투명으로 얹어 농지·산림·시가화 등을 구분하기 위한
// 용도라(§2026-08-28 사용자 요청) 채도를 낮춰 텍스처를 완전히 가리지 않게 했다.
const LANDCOVER_FILL_COLOR: ExpressionSpecification = [
  "match",
  ["get", "L2_CODE"],
  "110", "#c98a7d", // 주거지역
  "120", "#a56a63", // 공업지역
  "130", "#c9736a", // 상업지역
  "140", "#d9a79c", // 문화·체육·휴양지역
  "150", "#8a8a8a", // 교통지역
  "160", "#9c9088", // 공공시설지역
  "210", "#d7d192", // 논
  "220", "#c2a35c", // 밭
  "230", "#b8c9a0", // 시설재배지(비닐하우스)
  "240", "#9caf6b", // 과수원
  "250", "#c7b57a", // 기타재배지
  "310", "#4f7a3d", // 활엽수림
  "320", "#2f5233", // 침엽수림
  "330", "#3f6b34", // 혼효림
  "410", "#a8c66c", // 자연초지
  "420", "#c3d69b", // 인공초지
  "510", "#7a9e9f", // 내륙습지
  "610", "#d9cba3", // 자연나지
  "620", "#c9c2b0", // 인공나지
  "710", "#2ab7c9", // 내륙수
  "#94a3b8", // 그 외
];

// 지형(raster-dem)은 스타일 JSON에 선언하지 않고 'load' 이후 명령형으로 추가한다 — 아래 참조.
// 위성영상: Esri World Imagery — 우리 백엔드를 거치지 않고 브라우저에서 Esri CDN에
// 직접 요청한다(무료, 키 불필요, CORS 허용 확인됨). 2026-08-28: V-World WMTS 프록시로
// 교체했다가(국내 커버리지가 더 촘촘해서) 다시 되돌림 — V-World WMTS가 Render(싱가포르
// 리전)에서 항상 502로 실패했고, 그 실패를 감추려던 Esri 폴백·캐스케이드 로직이 오히려
// Render 무료 인스턴스를 과부하시켜 헬스체크 실패·429·로딩 지연을 유발했다(자세한 경위는
// api_server.py의 _IMAGERY_CACHE 주석 §연혁 참조). Esri는 산간지역 등 일부 위치에서
// "Image Not Available" 회색 타일을 반환하는 단점이 있지만, 그 정도가 백엔드 전체가
// 불안정해지는 것보다는 훨씬 낫다 — 직결이 훨씬 빠르고 안정적이다.
//
// maxzoom을 19가 아니라 18로 낮춰둔다 — 실측 결과 산청 등 산간지역은 z19에서 거의
// 항상 이 회색 플레이스홀더만 나오고, z18까지는 대체로 실제 이미지가 있었다
// (2026-08-28 확인). MapLibre는 소스의 maxzoom을 넘는 줌에서는 그 이상 타일을 요청하지
// 않고 마지막 유효 타일(z18)을 그대로 확대해서 쓴다 — 그 이상 확대하면 살짝 흐려지긴
// 하지만 회색 화면보다는 훨씬 낫다. 서울처럼 실제로 z19 커버리지가 있는 곳도 손해를
// 보지만, 이 프로젝트의 메인 데모 지역(산청)이 산간이라 이 쪽을 우선한다.
const MAP_STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    satellite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 18,
      attribution: "Esri, Maxar, Earthstar Geographics",
    },
    labels: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
    },
    // OSM 벡터(OpenMapTiles 스키마: building/transportation 등) — 무료·키 불필요(OpenFreeMap).
    // 프로덕션에서는 §2.6 건축물대장·§2.6 도로망 표준노드링크로 교체.
    osm_vectors: {
      type: "vector",
      url: "https://tiles.openfreemap.org/planet",
    },
  },
  layers: [
    { id: "satellite", type: "raster", source: "satellite" },
    { id: "labels", type: "raster", source: "labels" },
    // OSM 도로 — z14까지만 있는 벡터타일이라 그보다 확대하면(예: 서울 z16 테스트 지점)
    // 성긴 지오메트리가 늘어나 보이며 구불구불하게 뒤틀린다. 기본은 숨기고 VWorld
    // 표준노드링크(§2.6, 아래 vworld-roads*)로 교체 — 실패했을 때만 폴백으로 노출.
    {
      id: "roads-casing-osm",
      type: "line",
      source: "osm_vectors",
      "source-layer": "transportation",
      minzoom: 11,
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
      paint: {
        "line-color": "#1e293b",
        "line-width": [
          "interpolate", ["linear"], ["zoom"],
          11, ["match", ["get", "class"], ["motorway", "trunk"], 2, ["primary", "secondary"], 1.4, 0.8],
          16, ["match", ["get", "class"], ["motorway", "trunk"], 9, ["primary", "secondary"], 6, ["tertiary", "minor"], 4, 2.5],
        ],
      },
    },
    {
      id: "roads-osm",
      type: "line",
      source: "osm_vectors",
      "source-layer": "transportation",
      minzoom: 11,
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
      paint: {
        "line-color": [
          "match", ["get", "class"],
          ["motorway", "trunk"], "#f59e0b",
          ["primary", "secondary"], "#fde68a",
          ["tertiary", "minor", "service"], "#e2e8f0",
          "#cbd5e1",
        ],
        "line-width": [
          "interpolate", ["linear"], ["zoom"],
          11, ["match", ["get", "class"], ["motorway", "trunk"], 1.2, ["primary", "secondary"], 0.8, 0.4],
          16, ["match", ["get", "class"], ["motorway", "trunk"], 6, ["primary", "secondary"], 4, ["tertiary", "minor"], 2.5, 1.2],
        ],
      },
    },
    // 터널: 점선 + 낮은 불투명도로 지하임을 표시
    {
      id: "roads-tunnel-osm",
      type: "line",
      source: "osm_vectors",
      "source-layer": "transportation",
      minzoom: 11,
      filter: ["==", ["get", "brunnel"], "tunnel"],
      layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
      paint: { "line-color": "#94a3b8", "line-dasharray": [2, 2], "line-width": 2, "line-opacity": 0.5 },
    },
    {
      // OSM(OpenFreeMap) 건물 — 산간지역은 매핑이 드문드문이라 기본은 숨겨두고,
      // VWorld 건물통합정보(§2.3 1순위, 아래 vworld-buildings-3d)로 교체한다.
      // 폴백용으로 스타일에는 남겨둠(대한민국 밖이나 VWorld 요청 실패 시 대비).
      id: "buildings-3d-osm",
      type: "fill-extrusion",
      source: "osm_vectors",
      "source-layer": "building",
      minzoom: 13,
      layout: { visibility: "none" },
      paint: {
        "fill-extrusion-color": [
          "interpolate", ["linear"], ["get", "render_height"],
          0, "#d6d3c9",
          20, "#b8b39f",
          60, "#8f8a73",
        ],
        "fill-extrusion-height": ["coalesce", ["get", "render_height"], 5],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.9,
      },
    },
  ],
};

// 도로가 주황/노랑 계열이라 예전 하늘색 경계선이 묻혀서 초록 계열로 변경 —
// 선택 강조(노랑)·도로(주황)·물(파랑)과 안 겹치는 색.
const ADM_LAYER_STYLE: Record<AdminLevel, { color: string; width: number; opacity: number }> = {
  sido: { color: "#059669", width: 2.5, opacity: 0.75 },
  sigungu: { color: "#10b981", width: 1.5, opacity: 0.7 },
  dong: { color: "#34d399", width: 1, opacity: 0.55 },
};

const BRIDGE_DECK_HEIGHT_M = 8;
const BRIDGE_DECK_BASE_M = 3;
const BRIDGE_HALF_WIDTH_M = { motorway: 12, trunk: 10, primary: 8, secondary: 7 } as Record<string, number>;
const DEFAULT_BRIDGE_HALF_WIDTH_M = 4;

// --- 시간축 위험영역(§5 UI-3D) ---
// 예전에는 여기에 손으로 그린 흐름 경로 + 깊이 슬라이더가 있었다. 실제 예측이 아니라
// what-if 볼륨이었고, 화면에서는 모형 산출물과 구분이 안 돼 오해를 부르기 쉬웠다.
// 2026-09-20에 걷어내고, 트랙①이 실측 강우로 시간마다 구동해 남긴 위험영역
// (risk_landslide_index.json, 폴리곤마다 arrival_hour) 자체를 시간축으로 세운다.
//
// 높이는 "퇴적 깊이"가 아니다 — 토석류 runout 모형이 아직 없다(4차 지시서 P1).
// 위험영역을 지형 위에서 보이게 하는 표시용 고정 높이이고, 화면에도 그렇게 쓴다.
// 침수 쪽은 반대로 SFINCS 실측 수심이 있으므로 그 값을 그대로 높이로 쓴다
// (flood-model-3d). 둘을 색·범례·높이 근거로 확실히 갈라 둔다.
// 폴리곤 묶음의 lon/lat 경계. "위험영역으로 이동" 버튼이 카메라를 거기로 보낼 때 쓴다.
// 좌표가 Polygon/MultiPolygon 어느 쪽이든 끝까지 내려가서 숫자 쌍만 줍는다.
function featuresBounds(
  features: Feature<Polygon | MultiPolygon>[]
): [[number, number], [number, number]] | null {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") {
      const [lon, lat] = c as [number, number];
      if (lon < minLon) minLon = lon;
      if (lat < minLat) minLat = lat;
      if (lon > maxLon) maxLon = lon;
      if (lat > maxLat) maxLat = lat;
      return;
    }
    if (Array.isArray(c)) for (const q of c) walk(q);
  };
  for (const f of features) walk(f.geometry.coordinates);
  return Number.isFinite(minLon) ? [[minLon, minLat], [maxLon, maxLat]] : null;
}

const RISK_WALL_HEIGHT_M = 14;
// 0.7 영역은 0.5 영역 안에 들어가 있다(P>=0.7 ⊂ P>=0.5). 같은 높이로 세우면 겹쳐서
// 아예 안 보이므로 더 높게 세운다 — 깊이를 뜻하는 값이 아니라 순전히 가림 방지다.
const RISK_WALL_HEIGHT_CRITICAL_M = 34;

// 방금 도달한 영역은 밝게, 이전 시각에 이미 넘어간 영역은 어둡게 — "번져가는" 것이
// 색으로도 읽히게 한다(age = 현재 프레임 − arrival_hour).
// 0.5(경고)는 주황, 0.7(위험)은 빨강 — 임계가 다르면 색도 달라야 한다.
const RISK_COLOR_NEW = "#fb923c";
const RISK_COLOR_RECENT = "#ea580c";
const RISK_COLOR_OLD = "#7c2d12";
const RISK_CRIT_NEW = "#f87171";
const RISK_CRIT_RECENT = "#dc2626";
const RISK_CRIT_OLD = "#7f1d1d";

function hhmm(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : "—";
}

// "2025. 7. 19(토) 09:00" — 연도까지 다 보여야 한다. 2025년 산청 재연이라는 걸
// 화면만 보고 알 수 있어야 하고, 연도가 없으면 올해 일처럼 읽힌다.
const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];
function frameLabel(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!m) return iso;
  const [, y, mo, d, hh, mm] = m;
  const w = WEEKDAY[new Date(Number(y), Number(mo) - 1, Number(d)).getDay()];
  return `${y}. ${Number(mo)}. ${Number(d)}(${w}) ${hh}:${mm}`;
}


// 데모 AOI(산청·서울) 빠른 이동 버튼 — 이 두 지역만 정적 벡터타일로 완전히
// 캐싱돼 있다(§AOI_BOUNDS). 부산 등 다른 지역도 라이브 V-World 폴백으로 여전히
// 뜨긴 하지만, 데모 스코프 밖이라 2026-08-29 사용자 요청으로 버튼에서 제외.
const TEST_LOCATIONS: { label: string; center: [number, number]; zoom: number; regionKey: RegionKey }[] = [
  { label: "산청 상능마을", center: INITIAL_CENTER, zoom: 12.5, regionKey: "sancheong" },
  { label: "서울 강남", center: [127.0276, 37.4979], zoom: 16, regionKey: "gangnam" },
];

// EvacuationPanel(§6)에서 선택한 대피 경로 — 카카오/네이버 실경로 API 붙기 전까지는
// 출발지→대피소 직선(하버사인 근사)만 표시한다(HANDOFF.md §6.9).
export interface EvacuationRoute {
  origin: [number, number]; // [lon, lat]
  destination: [number, number]; // [lon, lat]
  label: string;
  // module_e_routing이 네이버 Directions로 실제 도로 경로를 받아온 경우 여기에 담긴다
  // (§6.4 /evacuation-route). 없으면(키 미설정·API 실패) 기존처럼 origin→destination 직선.
  path?: [number, number][];
}

interface MapExplorerProps {
  route?: EvacuationRoute | null;
  // §6.8 폴백 ① — 위치 권한이 없어도 지도를 클릭해 출발지를 고를 수 있게. true인
  // 동안 커서가 십자선으로 바뀌고, 다음 클릭 좌표를 onOriginPicked로 한 번 올려보낸다.
  pickOrigin?: boolean;
  onOriginPicked?: (lonLat: [number, number]) => void;
  // §7 IsolationPanel에서 계산한 고립 건물 클러스터(hull, 단독 건물은 Point) — 마젠타로 표시.
  isolatedAreas?: GeoJSON.FeatureCollection | null;
  // 위험영역과 겹쳐 통행 불가로 판정된 도로 구간 — 빨간 굵은 선으로 표시한다.
  // 고립 구역(마젠타)·대피경로(시안)와 색으로 구분된다.
  blockedRoads?: GeoJSON.FeatureCollection | null;
  // 패널에서 "고립 구역 N"을 클릭하면 그 구역으로 지도를 이동시키는 용도. nonce를
  // 넣는 이유는 같은 구역을 연달아 두 번 눌러도(같은 bbox) 매번 다시 이동해야 하는데
  // React effect는 값이 안 바뀌면 재실행을 안 하기 때문 — 클릭마다 nonce를 올려 강제한다.
  focusBbox?: { bbox: [number, number, number, number]; nonce: number } | null;
  // "산청 상능마을"/"서울 강남" 버튼으로 지도가 이동할 때 부모에 어느 지역인지 알려준다
  // — EvacuationPanel/IsolationPanel이 그 지역의 대피소 목록을 쓰도록 상태를 끌어올림.
  onRegionSelect?: (region: RegionKey) => void;
  // 데모 트리거로 경보가 새로 생기면 올라가는 값 — 침수 폴리곤과 시간축을 다시 받는다.
  alertNonce?: number;
}

export default function MapExplorer({
  route = null,
  pickOrigin = false,
  onOriginPicked,
  isolatedAreas = null,
  blockedRoads = null,
  focusBbox = null,
  onRegionSelect,
  alertNonce = 0,
}: MapExplorerProps = {}) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const highlightUpdateRef = useRef<((code: string | null) => void) | null>(null);
  // 현재 카메라 중심이 산청·서울 AOI 안인지 — 안이면 정적 타일을 보여주고 실시간
  // V-World fetch는 건너뛴다(아래 syncAOILayers/updateVWorld* 참조).
  const aoiRef = useRef<AOIKey | null>(null);
  // §7 고립 판정이 "지금 어느 지역이 선택돼있는지"를 알아야 그 지역 대피소/bbox로
  // /isolation-check를 부를 수 있다 — 렌더마다 다시 만들어지지 않아야 하므로 state가
  // 아니라 ref로 들고 있는다(TEST_LOCATIONS 버튼이 갱신).
  const isolationRegionRef = useRef<RegionKey>(DEFAULT_REGION);
  // 대피소 레이어는 지역이 바뀌면 다시 그려야 해서 ref가 아니라 state로도 들고 있다
  // (ref 변경은 렌더를 유발하지 않아 useEffect가 안 돈다).
  const [shelterRegion, setShelterRegion] = useState<RegionKey>(DEFAULT_REGION);
  // §7 — 시간 스크러버를 드래그하면 위험영역이 프레임마다 바뀌는데 매 프레임
  // /isolation-check를 부르면 과하므로 디바운스 타이머를 여기 들고 있는다.
  const isolationDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [mapReady, setMapReady] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<AdminSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const searchSlow = useSlowLoading();
  const [selectedRegion, setSelectedRegion] = useState<AdminSearchResult | null>(null);
  // Module B(SFINCS)가 실제로 계산한 최대 침수심(m). null이면 미산출.
  const [modelFloodDepth, setModelFloodDepth] = useState<number | null>(null);
  // Module B 침수 폴리곤 원본 — 지도 소스에도 넣지만, 고립 판정의 hazard로도 써야
  // 해서 여기 들고 있는다(소스에서 되읽는 건 MapLibre 내부 API라 쓰지 않는다).
  const [floodFeatures, setFloodFeatures] = useState<Feature<Polygon | MultiPolygon>[]>([]);
  // 침수 폴리곤 안에 들어오는 렌더링된 건물 수(보조 지표). null이면 미산출.
  const [floodedBuildingCount, setFloodedBuildingCount] = useState<number | null>(null);
  const [hazardIsolatedCount, setHazardIsolatedCount] = useState<number | null>(null);

  // --- 시간축(§5 UI-3D) ---
  // "지금 보는 게 몇 월 며칠 몇 시의 예측인가"가 화면에 없으면 3D를 아무리 잘 그려도
  // 읽을 수가 없다. 트랙①의 프레임(39시간)과 폴리곤별 도달시각을 받아서, 스크러버가
  // 가리키는 시각까지 도달한 영역만 누적해 세운다.
  const [timeline, setTimeline] = useState<AlertTimeline | null>(null);
  // 시간축을 못 받았을 때 화면에 띄울 진단 문구. 상태코드가 아니라 /health를 찔러
  // 만든 문장이라 "재시작하면 되는 건지"까지 바로 읽힌다.
  const [timelineError, setTimelineError] = useState<string | null>(null);
  // 지금 화면에 세워진 위험영역의 경계. 폴리곤이 카메라에서 5~20km 떨어진 곳에
  // 있어서(대표지점이 생비량면이 아니다) 시각을 넘겨도 "아무 변화 없음"으로 보였다 —
  // 버튼 하나로 거기로 갈 수 있어야 한다.
  const [riskBounds, setRiskBounds] = useState<[[number, number], [number, number]] | null>(null);
  const [frameIdx, setFrameIdx] = useState(0);
  const [playing, setPlaying] = useState(false);

  // WebGL을 못 쓰는 환경(원격 데스크톱, 일부 가상머신, GPU 차단 정책, 헤드리스
  // 브라우저)에서는 MapLibre 생성자가 그대로 throw한다. 그게 잡히지 않으면 React가
  // 트리를 통째로 버려서 지도뿐 아니라 패널·메뉴까지 빈 화면이 된다 — 지도를 못
  // 그리는 것과 대시보드를 못 쓰는 것은 다르므로 여기서 끊고 안내를 띄운다.
  const [mapFailed, setMapFailed] = useState(false);

  // 지도 초기화 (1회)
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
      container: mapContainer.current,
      style: MAP_STYLE,
      center: INITIAL_CENTER,
      zoom: 12.5,
      pitch: DEFAULT_PITCH,
      bearing: -20,
      // 85° 근처의 극단적인 pitch는 지형(terrain) 활성화 상태에서 카메라 투영이
      // 불안정해져 줌 중 "튕기는" 현상의 흔한 원인이라 안전한 값으로 낮춤(70).
      // 2026-08-29: 한때 이 값을 55로 더 낮춘 적이 있다 — 큰 pitch일수록 화면에
      // 지평선까지 원근 투영되는 면적이 넓어져 위성 래스터 타일 요청이 폭증했기
      // 때문(실측: 산청 zoom17·pitch60에서 224개 타일·idle까지 4.5초). 하지만 그
      // 직후 산청·서울 AOI 위성사진을 통째로 로컬 캐싱해서(§AOI_SATELLITE_ZOOM,
      // ${region}-satellite 레이어가 라이브 Esri 위에 항상 덮인다) 그 두 지역
      // 안에서는 pitch를 아무리 올려도 화면에 뜨는 건 이미 로컬 타일이라 이 문제
      // 자체가 없어졌다 — 70으로 원복. AOI 밖(다른 지역 자유탐색)에서 극단적으로
      // 눕혀서 줌인하면 예전 그 렉이 다시 나올 수 있지만, 데모 스코프 밖이라 감수.
      maxPitch: 70,
      // 이 프로젝트는 대한민국 전용이라 카메라가 그 밖으로 나갈 이유가 없다 — 전세계
      // 뷰에서 오는 렉 방지(위 SOUTH_KOREA_BOUNDS 주석). minZoom은 maxBounds가 이미
      // 자동으로 강제하는 하한과 별개로, 컨테이너 리사이즈 도중에도 항상 그 하한을
      // 보장하기 위한 안전판.
      maxBounds: SOUTH_KOREA_BOUNDS,
      minZoom: 6,
      // 마우스로 자유롭게 회전/기울기(우클릭 또는 Ctrl+드래그) 조작 가능하도록 명시적으로 켬
      dragRotate: true,
      pitchWithRotate: true,
      touchZoomRotate: true,
      touchPitch: true,
      // 커서 위치 기준 줌은 지형 고도가 아직 로드 중일 때 그 지점의 고도값이 계속
      // 바뀌면서 카메라가 재계산돼 튕기는 원인이 된다 — 화면 중심 기준으로 고정
      scrollZoom: { around: "center" },
      });
    } catch (err) {
      console.error("[maplibre] 지도 초기화 실패 — 패널은 그대로 쓸 수 있다", err);
      setMapFailed(true);
      return;
    }
    map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
    // fitBounds는 bearing을 명시하지 않으면 0으로 되돌린다(공식 문서에 명시된 동작) —
    // 생성자에서 준 -20을 유지하려면 여기서도 다시 넘겨야 한다.
    map.fitBounds(INITIAL_BOUNDS, { padding: 40, duration: 0, bearing: -20 });
    mapRef.current = map;

    map.once("load", () => {
      // 지형(raster-dem)은 api_server.py의 /terrain-tiles 프록시를 거친다 — AWS
      // elevation-tiles-prod 버킷이 Access-Control-Allow-Origin을 안 보내서 브라우저가
      // 직접 요청하면 고도 픽셀을 못 읽어(캔버스 오염) 지형이 조용히 렌더링되지 않는다.
      map.addSource("terrain", {
        type: "raster-dem",
        tiles: [`${API_BASE}/terrain-tiles/{z}/{x}/{y}.png`],
        tileSize: 256,
        encoding: "terrarium",
        maxzoom: 15,
      });
      map.addLayer({ id: "hills", type: "hillshade", source: "terrain", paint: { "hillshade-exaggeration": 0.7 } });

      // 2026-08-28~29: 원래 여기서 줌에 따라 exaggeration을 1.3→0.12까지 실시간으로
      // 낮추는 taper가 있었다(z15+에서 DEM 오버줌 스파이크를 감추려는 의도). 그런데
      // 건물이 실제 height_m로 압출되기 시작한 뒤(2026-08-29) 실측해보니, 카메라를
      // 고정한 채 exaggeration만 1.3→0.12로 바꿨을 때 같은 건물이 화면에서 69px나
      // 움직였다 — exaggeration이 지형 메시의 실제 고도를 바꾸는 값이라, 경사면 위
      // 건물의 "땅" 자체가 줌에 따라 오르내리면서 건물이 "땅에 박혔다 솟았다"
      // 하는 것처럼 보이는 원인이었다(사용자 리포트로 재현·근본원인 확인). 문제는
      // "값이 줌마다 바뀐다"는 것이었지 값의 크기가 아니었으므로, 줌과 무관한
      // 고정값을 쓰기로 했다 — 그래야 건물이 지형에 대해 항상 같은 자리에 있다.
      //
      // 처음엔 절충한다고 0.55로 낮게 고정했는데, 주로 보게 되는 저~중간 줌(원래
      // taper가 1.3을 쓰던 구간)에서 산세가 실제 스케일보다도 낮아 보인다는 사용자
      // 리포트로 재조정 — 원래 taper의 최댓값(1.3)에 가깝게 1.2로 고정한다. z16+
      // 근접줌에서 DEM 오버줌 스파이크가 taper 최솟값(0.12)일 때보다는 더 보이겠지만,
      // 건물/도로는 이미 실제 벡터 데이터(압출 높이·폭)로 정밀하게 표현되고 있어
      // 지형 메시 자체의 완벽함보다는 산불·산사태 서사에 필요한 산세의 입체감이
      // 우선이다.
      const TERRAIN_EXAGGERATION = 1.2;
      map.setTerrain({ source: "terrain", exaggeration: TERRAIN_EXAGGERATION });

      // 대기감(하늘·안개) + 태양광 — 지형 메시 자체의 정밀도는 한계가 있으니(위 주석)
      // 대신 조명·대기 표현으로 "실사에 가까운 가상세계" 느낌을 낸다. atmosphere-blend·
      // fog-ground-blend는 3D terrain이 있을 때만 의미가 있는 속성(MapLibre 스펙).
      map.setSky({
        "sky-color": "#0b1a3a",
        "horizon-color": "#bcd4f2",
        "fog-color": "#dbe7f7",
        "fog-ground-blend": 0.6,
        "horizon-fog-blend": 0.7,
        "sky-horizon-blend": 0.6,
        "atmosphere-blend": 0.6,
      });
      // 오후 느낌의 낮은 태양 각도로 건물·교량 압출에 뚜렷한 음영을 줘 입체감을 강조.
      map.setLight({ anchor: "viewport", color: "#fff7ed", intensity: 0.5, position: [1.15, 210, 40] });

      // 행정경계 3계층(사용자 제공 BND_ADM_DONG_PG 기반, 시도/시군구는 그 원본을
      // dissolve해서 생성 — 전국) — 뷰포트 bbox로 api_server.py의 /boundaries에서
      // 그때그때 잘라 받는다(§4.1: 재투영은 여기 UI 출력 직전에만). 검색해서 선택한
      // 지역만 노란색으로 강조 — highlightUpdateRef를 통해 동적으로 갱신됨(아래 참조).
      for (const level of ["sido", "sigungu", "dong"] as AdminLevel[]) {
        const style = ADM_LAYER_STYLE[level];
        map.addSource(`adm-${level}`, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({
          id: `adm-${level}-line`,
          type: "line",
          source: `adm-${level}`,
          paint: {
            "line-color": style.color,
            "line-width": style.width,
            "line-opacity": style.opacity,
          },
        });
      }

      highlightUpdateRef.current = (code: string | null) => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        for (const level of ["sido", "sigungu", "dong"] as AdminLevel[]) {
          const style = ADM_LAYER_STYLE[level];
          const layerId = `adm-${level}-line`;
          if (code === null) {
            currentMap.setPaintProperty(layerId, "line-color", style.color);
            currentMap.setPaintProperty(layerId, "line-width", style.width);
            currentMap.setPaintProperty(layerId, "line-opacity", style.opacity);
          } else {
            currentMap.setPaintProperty(layerId, "line-color", ["case", ["==", ["get", "code"], code], "#facc15", style.color]);
            currentMap.setPaintProperty(layerId, "line-width", ["case", ["==", ["get", "code"], code], 3, style.width]);
            currentMap.setPaintProperty(layerId, "line-opacity", ["case", ["==", ["get", "code"], code], 0.95, style.opacity]);
          }
        }
      };

      const updateBoundaries = () => {
        // HMR(핫 리로드)로 컴포넌트가 재마운트되면 이 setTimeout 콜백은 이미 정리된
        // 옛 map 클로저를 참조할 수 있다 — 매번 mapRef.current로 살아있는 지도를 다시 읽는다.
        const currentMap = mapRef.current;
        if (!currentMap) return;
        const b = currentMap.getBounds();
        getBoundaries([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
          .then((byLevel) => {
            const liveMap = mapRef.current;
            if (!liveMap) return;
            for (const level of ["sido", "sigungu", "dong"] as AdminLevel[]) {
              const source = liveMap.getSource(`adm-${level}`) as GeoJSONSource | undefined;
              source?.setData(byLevel[level]);
            }
          })
          .catch(() => {
            // 뷰포트 이동 중 흔한 일시적 실패 — 다음 moveend에서 다시 시도되므로 조용히 무시
          });
      };

      // 산청·서울 AOI 정적 타일(2026-08-28) — 위성사진 → 토지피복 → 하천 → 도로 →
      // 건물 순으로 쌓는다(위성이 제일 아래). 처음엔 전부 숨겨두고, syncAOILayers()가
      // 카메라 위치를 보고 해당 AOI 것만 켠다. 두 지역 다 아니면 전부 숨긴 채로 기존
      // 실시간 V-World/Esri 레이어(아래)가 그 자리를 대신한다.
      // MapLibre의 타일/geojson-url 요청 내부 경로는 상대경로("/tiles/...")를 바로
      // Request()에 넘겨서 파싱 실패한다(브라우저 fetch와 달리 base URL을 안 붙여줌) —
      // 반드시 origin을 붙인 절대 URL이어야 한다(2026-08-28 실측 확인).
      // 타일(위성·벡터)만 tileBase()로 분리한다 — 744MB라 Vercel 배포 용량을 먹어서
      // 백엔드(EC2 Caddy)가 서빙한다(2026-09-19, api.ts의 tileBase() 주석 참조).
      // 하천 geojson(/aoi/, 5.6MB)은 작아서 그대로 Vercel에 둔다.
      const origin = window.location.origin;
      const tiles = tileBase();
      for (const region of AOI_KEYS) {
        // 위성사진(2026-08-29, scripts/fetch_aoi_satellite.py) — pitch·zoom이 겹치면
        // 라이브 Esri 요청이 한 번에 수백 개까지 튀는 게 원인이었던 확대 랙(§DEFAULT_PITCH
        // 주석)을 이 두 AOI 안에서는 아예 없앤다. beforeId로 "labels"(지명 텍스트) 바로
        // 아래에 꽂아서 라벨이 항상 그 위에 그려지게 함 — 다른 레이어들은 addLayer
        // 기본 동작대로 현재 스택 맨 위에 쌓여도 무방(§순서 코멘트 위 참고).
        map.addSource(`${region}-satellite-src`, {
          type: "raster",
          tiles: [`${tiles}/satellite/${region}/{z}/{x}/{y}.jpg`],
          tileSize: 256,
          bounds: AOI_BOUNDS[region],
          ...AOI_SATELLITE_ZOOM,
        });
        map.addLayer(
          {
            id: `${region}-satellite`,
            type: "raster",
            source: `${region}-satellite-src`,
            layout: { visibility: "none" },
          },
          "labels"
        );

        map.addSource(`${region}-landcover-src`, {
          type: "vector",
          tiles: [`${tiles}/tiles/${region}-landcover/{z}/{x}/{y}.pbf`],
          bounds: AOI_BOUNDS[region],
          ...AOI_TILE_ZOOM.landcover,
        });
        map.addLayer({
          id: `${region}-landcover-fill`,
          type: "fill",
          source: `${region}-landcover-src`,
          "source-layer": `${region}-landcover`,
          layout: { visibility: "none" },
          paint: {
            "fill-color": LANDCOVER_FILL_COLOR,
            // 멀리서는 뚜렷하게, 건물 단위로 확대할수록(§AOI_TILE_ZOOM.buildings.minzoom
            // 근방) 옅어져 3D 건물·도로 판독을 방해하지 않게 함
            "fill-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0.55, 13, 0.5, 16, 0.15],
          },
        });

        // 하천은 이미 완전히 받아둔 소량 데이터(2~4MB)라 타일링 없이 그대로 GeoJSON —
        // vworld-rivers처럼 뷰포트마다 누적할 필요 없이 처음부터 전체가 다 있다.
        map.addSource(`${region}-rivers-src`, { type: "geojson", data: `${origin}/aoi/${region}_rivers.geojson` });
        map.addLayer({
          id: `${region}-rivers-fill`,
          type: "fill",
          source: `${region}-rivers-src`,
          layout: { visibility: "none" },
          paint: { "fill-color": "#0e9aa7", "fill-opacity": 0.75 },
        });

        map.addSource(`${region}-roads-src`, {
          type: "vector",
          tiles: [`${tiles}/tiles/${region}-roads/{z}/{x}/{y}.pbf`],
          bounds: AOI_BOUNDS[region],
          ...AOI_TILE_ZOOM.roads,
        });
        map.addLayer({
          id: `${region}-roads-casing`,
          type: "line",
          source: `${region}-roads-src`,
          "source-layer": `${region}-roads`,
          layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
          paint: {
            "line-color": "#1e293b",
            "line-width": ["match", ["get", "rd_rank_h"], "특별·광역시도", 7, "일반국도", 6, 4],
          },
        });
        map.addLayer({
          id: `${region}-roads`,
          type: "line",
          source: `${region}-roads-src`,
          "source-layer": `${region}-roads`,
          filter: ["!=", ["get", "rd_type_h"], "터널"],
          layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
          paint: {
            "line-color": ["match", ["get", "rd_rank_h"], "특별·광역시도", "#f59e0b", "일반국도", "#fbbf24", "#e2e8f0"],
            "line-width": ["match", ["get", "rd_rank_h"], "특별·광역시도", 5, "일반국도", 4, 2.5],
          },
        });
        map.addLayer({
          id: `${region}-roads-tunnel`,
          type: "line",
          source: `${region}-roads-src`,
          "source-layer": `${region}-roads`,
          filter: ["==", ["get", "rd_type_h"], "터널"],
          layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
          paint: { "line-color": "#94a3b8", "line-dasharray": [2, 2], "line-width": 3, "line-opacity": 0.5 },
        });

        map.addSource(`${region}-buildings-src`, {
          type: "vector",
          tiles: [`${tiles}/tiles/${region}-buildings/{z}/{x}/{y}.pbf`],
          bounds: AOI_BOUNDS[region],
          ...AOI_TILE_ZOOM.buildings,
        });
        map.addLayer({
          id: `${region}-buildings-3d`,
          type: "fill-extrusion",
          source: `${region}-buildings-src`,
          "source-layer": `${region}-buildings`,
          layout: { visibility: "none" },
          paint: {
            "fill-extrusion-color": "#c9c3b3",
            "fill-extrusion-height": ["get", "height_m"],
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.9,
          },
        });
      }

      // 카메라 중심이 AOI 안으로 들어오면 위 정적 레이어를 켜고 아래 실시간
      // vworld-*/satellite 레이어는 끈다(반대로 나가면 원상복구) — 매 moveend마다
      // 부르지만 AOI가 안 바뀌었으면 아무 것도 안 건드리고 조용히 리턴.
      // "satellite"(라이브 Esri)는 여기 안 넣는다 — pitch/bearing 때문에 화면이
      // AOI 사각 bounds 살짝 밖까지 보일 때(2026-08-29 실측: 산청 초기 뷰 우하단에
      // 흰/음영 구멍) 그 자리를 채워줄 게 없어진다. 라이브 레이어를 계속 밑에 깔아두고
      // 캐시된 ${region}-satellite가 그 위를 덮는 쪽이 항상 안전 — AOI 안쪽 대부분은
      // 로컬 타일이 먼저 그려져 라이브 요청은 화면에 실제로 안 보이는 배경 작업일 뿐이다.
      const LIVE_LAYER_IDS = ["vworld-buildings-3d", "vworld-roads-casing", "vworld-roads", "vworld-roads-tunnel", "vworld-rivers-fill"];
      const STATIC_LAYER_SUFFIXES = ["satellite", "landcover-fill", "rivers-fill", "roads-casing", "roads", "roads-tunnel", "buildings-3d"];
      const syncAOILayers = () => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        const center = currentMap.getCenter();
        const aoi = getActiveAOI(center.lng, center.lat);
        if (aoi === aoiRef.current) return;
        aoiRef.current = aoi;
        for (const region of AOI_KEYS) {
          const visible = aoi === region;
          for (const suffix of STATIC_LAYER_SUFFIXES) {
            currentMap.setLayoutProperty(`${region}-${suffix}`, "visibility", visible ? "visible" : "none");
          }
        }
        const liveVisibility = aoi ? "none" : "visible";
        for (const id of LIVE_LAYER_IDS) {
          currentMap.setLayoutProperty(id, "visibility", liveVisibility);
        }
      };

      // VWorld 실폭하천(2026-08-28 신규) — 지금까지 지도에 하천이 아예 안 그려져
      // 있었다. 건물·도로보다 먼저 추가해 그 아래(땅 표면)에 깔리게 한다.
      // 색상은 실제 저수지에 가깝게 하늘색과 청록 사이 톤으로.
      map.addSource("vworld-rivers", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "vworld-rivers-fill",
        type: "fill",
        source: "vworld-rivers",
        paint: { "fill-color": "#0e9aa7", "fill-opacity": 0.75 },
      });

      // V-World Data API는 bbox 면적이 10km²를 넘으면 실패해서(§ api_server.py
      // _clamp_bbox_to_area) 화면 중심 근처의 좁은 창만 매번 갱신된다 — 하천은
      // 건물처럼 매번 그 창으로 통째로 교체하면 패닝할 때마다 "있다 없다"를
      // 반복하며 깜빡인다(2026-08-28 사용자 리포트). 하천은 개수가 적고 안
      // 움직이니, 지금까지 받은 걸 feature id 기준으로 계속 누적해서 한 번
      // 화면에 들어왔던 하천은 계속 남아있게 한다.
      const accumulatedRivers = new Map<string | number, Feature>();
      const updateVWorldRivers = () => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        // 산청·서울 AOI 안에서는 위의 정적 하천 GeoJSON이 이미 전체를 다 갖고 있으니
        // 실시간 fetch 자체를 건너뛴다(쿼터 절약 + 깜빡임 걱정 원천 차단).
        if (aoiRef.current) return;
        const b = currentMap.getBounds();
        getVWorldRivers([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
          .then((fc) => {
            const liveMap = mapRef.current;
            if (!liveMap) return;
            for (const feature of fc.features) {
              const key = feature.id ?? JSON.stringify(feature.properties);
              accumulatedRivers.set(key, feature as Feature);
            }
            (liveMap.getSource("vworld-rivers") as GeoJSONSource | undefined)?.setData({
              type: "FeatureCollection",
              features: Array.from(accumulatedRivers.values()),
            } as FeatureCollection);
          })
          .catch(() => {
            // 하천은 OSM 폴백이 없다 — 실패해도 이미 누적된 데이터는 그대로
            // 남아있으니 조용히 무시(다음 moveend에서 재시도됨).
          });
      };

      // VWorld 건물통합정보(§2.3 1순위) — OSM보다 훨씬 촘촘한 실제 건물 데이터.
      // fill-extrusion-height는 원본에 없는 값이라 height_m(층수×3m, api_server.py에서
      // 계산)을 쓴다 — 실측 높이가 아니라 통상값 근사임을 UI에 명시(§6).
      map.addSource("vworld-buildings", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "vworld-buildings-3d",
        type: "fill-extrusion",
        source: "vworld-buildings",
        paint: {
          "fill-extrusion-color": "#c9c3b3",
          "fill-extrusion-height": ["get", "height_m"],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.9,
        },
      });

      const updateVWorldBuildings = () => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        // 산청·서울 AOI 안에서는 정적 벡터타일(위 ${region}-buildings-3d)이 대신하므로
        // 실시간 fetch를 건너뛴다.
        if (aoiRef.current) return;
        // 건물 압출은 어차피 minzoom 13 근처에서만 의미가 있고, VWorld 쿼터도 아껴야
        // 하니 많이 줌아웃된 상태에서는 요청하지 않는다.
        if (currentMap.getZoom() < 13) return;
        const b = currentMap.getBounds();
        getVWorldBuildings([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
          .then((fc) => {
            const liveMap = mapRef.current;
            if (!liveMap) return;
            (liveMap.getSource("vworld-buildings") as GeoJSONSource | undefined)?.setData(fc);
          })
          .catch(() => {
            // 실패 시 OSM 폴백 레이어를 대신 보여준다
            const liveMap = mapRef.current;
            liveMap?.setLayoutProperty("buildings-3d-osm", "visibility", "visible");
          });
      };

      // VWorld 표준노드링크(§2.6) 도로 — OSM z14 한계로 뒤틀려 보이던 문제 해결.
      map.addSource("vworld-roads", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "vworld-roads-casing",
        type: "line",
        source: "vworld-roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#1e293b",
          "line-width": ["match", ["get", "rd_rank_h"], "특별·광역시도", 7, "일반국도", 6, 4],
        },
      });
      map.addLayer({
        id: "vworld-roads",
        type: "line",
        source: "vworld-roads",
        filter: ["!=", ["get", "rd_type_h"], "터널"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["match", ["get", "rd_rank_h"], "특별·광역시도", "#f59e0b", "일반국도", "#fbbf24", "#e2e8f0"],
          "line-width": ["match", ["get", "rd_rank_h"], "특별·광역시도", 5, "일반국도", 4, 2.5],
        },
      });
      map.addLayer({
        id: "vworld-roads-tunnel",
        type: "line",
        source: "vworld-roads",
        filter: ["==", ["get", "rd_type_h"], "터널"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#94a3b8", "line-dasharray": [2, 2], "line-width": 3, "line-opacity": 0.5 },
      });

      // 교량(brunnel=='bridge')/고가차도는 MapLibre line 레이어로는 지형 위에 그대로
      // 드레이프될 뿐이라 실제로 "떠 있는" 느낌이 안 난다 — LineString을 폭만큼
      // 버퍼링해 얇은 폴리곤으로 만들고 fill-extrusion으로 지면에서 띄워 올려 진짜
      // 입체 교량 데크를 만든다.
      map.addSource("bridges", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "bridges-3d",
        type: "fill-extrusion",
        source: "bridges",
        paint: {
          "fill-extrusion-color": "#9ca3af",
          "fill-extrusion-height": BRIDGE_DECK_HEIGHT_M,
          "fill-extrusion-base": BRIDGE_DECK_BASE_M,
          "fill-extrusion-opacity": 0.95,
        },
      });

      // OSM brunnel 태그 기반 폴백(§ VWorld 요청 실패 시에만 사용) — 예전 로직 그대로 유지.
      const updateBridgesFromOSM = () => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        const raw = currentMap.querySourceFeatures("osm_vectors", {
          sourceLayer: "transportation",
          filter: ["==", ["get", "brunnel"], "bridge"],
        }) as unknown as Feature<LineString>[];
        const seen = new Set<string | number>();
        const osmBridgeFeatures: Feature<Polygon | MultiPolygon>[] = [];
        for (const feat of raw) {
          const key = feat.id ?? JSON.stringify(feat.geometry.coordinates);
          if (seen.has(key)) continue;
          seen.add(key);
          const roadClass = (feat.properties?.class as string) ?? "";
          const halfWidth = BRIDGE_HALF_WIDTH_M[roadClass] ?? DEFAULT_BRIDGE_HALF_WIDTH_M;
          try {
            const poly = buffer(feat, halfWidth, { units: "meters", steps: 4 });
            if (poly) osmBridgeFeatures.push(poly);
          } catch {
            // 극단적으로 짧거나 기형인 geometry는 버퍼링이 실패할 수 있음 — 건너뜀
          }
        }
        (currentMap.getSource("bridges") as GeoJSONSource | undefined)?.setData({
          type: "FeatureCollection",
          features: osmBridgeFeatures,
        } as FeatureCollection);
      };

      const updateVWorldRoads = () => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        if (currentMap.getZoom() < 11) return;
        // AOI 안에서도 계속 fetch는 한다 — 정적 도로 타일엔 교량 데크가 없어서
        // (geojson-vt로 자른 타일 경계 때문에 LineString을 안정적으로 재조립하기
        // 까다로움) 교량만큼은 여전히 이 실시간 결과로 만든다. 대신 메인 도로
        // 라인(vworld-roads 소스)은 AOI 안이면 정적 타일이 이미 그리고 있으니
        // 중복으로 덮어쓰지 않는다.
        const b = currentMap.getBounds();
        getVWorldRoads([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
          .then((fc) => {
            const liveMap = mapRef.current;
            if (!liveMap) return;
            if (!aoiRef.current) {
              (liveMap.getSource("vworld-roads") as GeoJSONSource | undefined)?.setData(fc);
            }

            // rd_type_h에 교량/고가차도가 명시돼 있어 OSM의 brunnel 태그보다 신뢰도
            // 높게 판별 가능 — 두 종류 다 지면에서 띄운 데크로 그린다.
            const bridgeFeatures: Feature<Polygon | MultiPolygon>[] = [];
            for (const feat of fc.features as Feature<LineString | MultiLineString>[]) {
              const type = feat.properties?.rd_type_h as string | undefined;
              if (type !== "교량" && type !== "고가차도") continue;
              try {
                const poly = buffer(feat, 6, { units: "meters", steps: 4 });
                if (poly) bridgeFeatures.push(poly);
              } catch {
                // 극단적으로 짧거나 기형인 geometry는 버퍼링이 실패할 수 있음 — 건너뜀
              }
            }
            (liveMap.getSource("bridges") as GeoJSONSource | undefined)?.setData({
              type: "FeatureCollection",
              features: bridgeFeatures,
            } as FeatureCollection);
          })
          .catch(() => {
            if (aoiRef.current) return; // AOI 안은 정적 도로 타일이 이미 신뢰성 있게 커버 — OSM 폴백 불필요
            // 실패 시 OSM 폴백 도로 레이어를 보여주고, 교량도 OSM brunnel 태그로 대체
            const liveMap = mapRef.current;
            for (const id of ["roads-osm", "roads-casing-osm", "roads-tunnel-osm"]) {
              liveMap?.setLayoutProperty(id, "visibility", "visible");
            }
            updateBridgesFromOSM();
          });
      };

      syncAOILayers();
      updateBoundaries();
      updateVWorldRivers();
      updateVWorldBuildings();
      updateVWorldRoads();
      let moveendTimer: ReturnType<typeof setTimeout> | undefined;
      map.on("moveend", () => {
        clearTimeout(moveendTimer);
        moveendTimer = setTimeout(() => {
          syncAOILayers();
          updateBoundaries();
          updateVWorldRivers();
          updateVWorldBuildings();
          updateVWorldRoads();
        }, 200);
      });

      // 시간축 위험영역 3D — bridges와 동일한 이유로 deck.gl이 아니라 MapLibre 네이티브
      // fill-extrusion을 쓴다(지형·건물과 깊이 오클루전이 맞아야 함). 데이터는 트랙①의
      // 사전계산 레이어이고, 시간 스크러버가 arrival_hour로 걸러서 setData 한다 —
      // 시각을 넘길수록 폴리곤이 누적돼 "번져가는" 것이 보인다.
      //
      // 높이는 고정(RISK_WALL_HEIGHT_M)이다. 토사 퇴적깊이 모형이 없으므로 높이에
      // 의미를 부여하지 않는다 — 있는 척하면 침수(실측 수심)와 구분이 안 된다.
      map.addSource("landslide-risk", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "landslide-risk-3d",
        type: "fill-extrusion",
        source: "landslide-risk",
        paint: {
          // age = 현재 프레임 − arrival_hour (스크러버가 속성으로 써 넣는다)
          "fill-extrusion-color": [
            "case",
            ["==", ["get", "level"], "critical"],
            ["step", ["number", ["get", "age"], 99], RISK_CRIT_NEW, 1, RISK_CRIT_RECENT, 6, RISK_CRIT_OLD],
            ["step", ["number", ["get", "age"], 99], RISK_COLOR_NEW, 1, RISK_COLOR_RECENT, 6, RISK_COLOR_OLD],
          ],
          "fill-extrusion-height": [
            "case",
            ["==", ["get", "level"], "critical"],
            RISK_WALL_HEIGHT_CRITICAL_M,
            RISK_WALL_HEIGHT_M,
          ],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.75,
        },
      });


      // Module B 실산출 침수 — 위의 flood-water와 달리 슬라이더가 아니라 SFINCS/ANUGA
      // 최대침수심 래스터에서 나온 값이다(module_b_flood/fim.py가 깊이 구간별로 폴리곤화,
      // api_server의 /alerts/{id}/geojson이 4326으로 재투영). 높이는 그 구간의 실제
      // 침수심 90분위(depth_p90_m)이고, 색은 구간(band)으로 정한다 — what-if 볼륨과
      // 섞이면 안 되므로 소스·레이어를 따로 둔다.
      map.addSource("flood-model", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "flood-model-3d",
        type: "fill-extrusion",
        source: "flood-model",
        paint: {
          "fill-extrusion-color": [
            "match",
            ["get", "band"],
            0, "#bae6fd",
            1, "#38bdf8",
            2, "#0284c7",
            3, "#1e3a8a",
            "#38bdf8",
          ],
          // 지형 기복 위에 얹히므로 수심을 그대로 쓰면 얕은 구간이 안 보인다 —
          // 최소 높이를 두되 과장하지 않는다(실제 수심 값은 팝업에 그대로 표기).
          // ["number", x, fallback]으로 감싸는 이유: 속성이 없거나 null이면 ["max"]가
          // null을 돌려주고 MapLibre가 그 폴리곤을 조용히 안 그린다(스타일 스펙
          // 검증기로 확인). 침수 구역이 이유 없이 사라지는 것보다 최소 높이가 낫다.
          "fill-extrusion-height": ["max", ["number", ["get", "depth_p90_m"], 0.5], 0.5],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.72,
        },
      });

      // 대피 경로(§6.9) — 지금은 직선거리 근사라 "실제 도로 경로 아님"이 시각적으로도
      // 드러나게 점선으로 그린다. 실경로 API가 붙으면 LineString 좌표만 실제 폴리라인으로
      // 바뀌고 이 레이어 자체는 그대로 재사용된다.
      // 대피경로 — 위성영상 위에서도 한눈에 잡히도록 네 겹으로 쌓는다.
      // 예전에는 시안색 점선 한 겹(width 5)이라 지형·도로와 섞여 안 보였다.
      //   glow   바깥 번짐 — 배경이 밝든 어둡든 선이 떠 보이게 한다
      //   casing 짙은 테두리 — 밝은 위성영상 위에서 형태를 잡아준다
      //   line   본선(solid) — 점선은 "잠정"처럼 읽혀서 실선으로 바꿨다
      //   flow   그 위를 덮는 흰 파선 — 길의 방향감을 준다
      // 폭은 줌에 따라 보간해 넓게 볼 때도 가늘어지지 않게 한다.
      // zoom 보간은 최상위에만 올 수 있다 — ["*", ["interpolate", ...], 2] 처럼 감싸면
      // MapLibre가 거부한다("zoom expression may only be used as input to a top-level
      // step/interpolate"). 스타일 스펙 검증기로 확인했고, 그래서 배율을 stops에 미리
      // 곱해 겹마다 따로 만든다.
      const routeWidth = (scale: number): ExpressionSpecification => [
        "interpolate", ["linear"], ["zoom"],
        10, 4 * scale,
        14, 8 * scale,
        17, 14 * scale,
      ];
      map.addSource("evacuation-route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "evacuation-route-glow",
        type: "line",
        source: "evacuation-route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#22d3ee",
          "line-width": routeWidth(3.2),
          "line-opacity": 0.22,
          "line-blur": 8,
        },
      });
      map.addLayer({
        id: "evacuation-route-casing",
        type: "line",
        source: "evacuation-route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#083344",
          "line-width": routeWidth(1.7),
          "line-opacity": 0.95,
        },
      });
      map.addLayer({
        id: "evacuation-route-line",
        type: "line",
        source: "evacuation-route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#22d3ee", "line-width": routeWidth(1), "line-opacity": 1 },
      });
      map.addLayer({
        id: "evacuation-route-flow",
        type: "line",
        source: "evacuation-route",
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: {
          "line-color": "#ecfeff",
          "line-width": routeWidth(0.34),
          "line-opacity": 0.9,
          "line-dasharray": [1.4, 2.2],
        },
      });
      // 통행 불가 도로 — 위험영역과 겹쳐 도로망 그래프에서 제거된 구간이다.
      // 대피경로(시안 점선)보다 아래, 고립 구역(마젠타)과는 색으로 구분한다.
      // 케이싱을 먼저 깔아 배경 도로 위에서도 선이 끊겨 보이지 않게 한다.
      map.addSource("blocked-roads", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "blocked-roads-casing",
        type: "line",
        source: "blocked-roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#450a0a", "line-width": 9, "line-opacity": 0.75 },
      });
      map.addLayer({
        id: "blocked-roads-line",
        type: "line",
        source: "blocked-roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ef4444", "line-width": 5, "line-opacity": 0.95 },
      });

      // 대피소 — 경로를 고르기 전에도 "어디로 갈 수 있는지"가 먼저 보여야 해서
      // 현재 지역 대피소를 전부 상시 표시한다. 글리프(텍스트) 없이 원만 겹쳐
      // 핀처럼 보이게 만든다 — 스타일의 폰트 엔드포인트가 한글을 보장하지 않아
      // 라벨을 심볼로 넣으면 지역에 따라 통째로 사라질 수 있다.
      const shelterRadius = (scale: number): ExpressionSpecification => [
        "interpolate", ["linear"], ["zoom"],
        9, 4 * scale,
        13, 8 * scale,
        17, 13 * scale,
      ];
      map.addSource("shelters", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "shelters-halo",
        type: "circle",
        source: "shelters",
        paint: {
          "circle-radius": shelterRadius(2.1),
          "circle-color": "#22c55e",
          "circle-opacity": 0.18,
          "circle-blur": 0.5,
        },
      });
      map.addLayer({
        id: "shelters-dot",
        type: "circle",
        source: "shelters",
        paint: {
          "circle-radius": shelterRadius(1),
          "circle-color": "#16a34a",
          "circle-stroke-width": 2.5,
          "circle-stroke-color": "#ecfdf5",
          "circle-opacity": 0.95,
        },
      });
      // 안쪽 흰 점 — 멀리서 보면 초록 원, 가까이서 보면 핀처럼 읽힌다
      map.addLayer({
        id: "shelters-core",
        type: "circle",
        source: "shelters",
        minzoom: 12,
        paint: {
          "circle-radius": shelterRadius(0.34),
          "circle-color": "#ffffff",
          "circle-opacity": 0.95,
        },
      });

      map.addSource("evacuation-markers", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "evacuation-markers-circle",
        type: "circle",
        source: "evacuation-markers",
        paint: {
          "circle-radius": 8,
          "circle-color": ["match", ["get", "role"], "origin", "#38bdf8", "destination", "#f472b6", "#ffffff"],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#0f172a",
        },
      });

      // 고립마을 자동탐지(§7) — 대피소까지 도로가 하나도 안 남은 건물 클러스터.
      // 건물 1채짜리 클러스터는 Point, 여러 채는 convex hull Polygon으로 오므로
      // geometry-type으로 나눠 각각 원/채움영역으로 그린다(마젠타 — 기존 빨강 위험
      // 폴리곤·파랑 대피경로와 구분).
      map.addSource("isolated-areas", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "isolated-areas-fill",
        type: "fill",
        source: "isolated-areas",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#d946ef", "fill-opacity": 0.3 },
      });
      map.addLayer({
        id: "isolated-areas-outline",
        type: "line",
        source: "isolated-areas",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "line-color": "#d946ef", "line-width": 2 },
      });
      map.addLayer({
        id: "isolated-areas-points",
        type: "circle",
        source: "isolated-areas",
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 6, "circle-color": "#d946ef", "circle-stroke-width": 1.5, "circle-stroke-color": "#0f172a" },
      });
      // 고립 구역을 클릭하면 몇 채인지 팝업으로 바로 보여준다 — 지도 위 도형만 봐서는
      // "이게 뭔지" 알 길이 없다는 문제(2026-09-03 피드백)를 직접 해결하는 부분.
      const isolationPopup = new Popup({ closeButton: false, closeOnClick: false, offset: 10 });
      const showIsolationPopup = (e: { lngLat: { lng: number; lat: number }; features?: MapGeoJSONFeature[] }) => {
        const feature = e.features?.[0];
        const count = feature?.properties?.building_count;
        if (count == null) return;
        map.getCanvas().style.cursor = "pointer";
        isolationPopup
          .setLngLat(e.lngLat)
          .setHTML(`<div style="font:12px sans-serif;color:#1e1b2e;">고립 구역 · 약 ${count}채<br/>대피소 도달 가능 경로 0개</div>`)
          .addTo(map);
      };
      const hideIsolationPopup = () => {
        map.getCanvas().style.cursor = "";
        isolationPopup.remove();
      };
      map.on("mouseenter", "isolated-areas-fill", showIsolationPopup);
      map.on("mouseleave", "isolated-areas-fill", hideIsolationPopup);
      map.on("mouseenter", "isolated-areas-points", showIsolationPopup);
      map.on("mouseleave", "isolated-areas-points", hideIsolationPopup);

      // 대피소·통행 불가 도로 — 점만 찍어두면 뭔지 모르므로 올리면 이름·수용인원을
      // 띄운다. 라벨을 심볼 레이어로 상시 노출하지 않는 이유는 스타일의 폰트
      // 엔드포인트가 한글 글리프를 보장하지 않기 때문이다(레이어 통째로 사라질 위험).
      const infoPopup = new Popup({ closeButton: false, closeOnClick: false, offset: 12 });
      const showInfo = (html: string) =>
        (e: { lngLat: { lng: number; lat: number }; features?: MapGeoJSONFeature[] }) => {
          const p = e.features?.[0]?.properties;
          if (!p) return;
          map.getCanvas().style.cursor = "pointer";
          infoPopup.setLngLat(e.lngLat).setHTML(html.replace(/\{(\w+)\}/g, (_, k) => String(p[k] ?? "—"))).addTo(map);
        };
      const hideInfo = () => {
        map.getCanvas().style.cursor = "";
        infoPopup.remove();
      };
      map.on("mouseenter", "shelters-dot", showInfo(
        '<div style="font:12px sans-serif;color:#0f172a;">' +
        '<b>{name}</b><br/>대피소 · 수용 {capacity}명</div>'
      ));
      map.on("mouseleave", "shelters-dot", hideInfo);
      map.on("mouseenter", "blocked-roads-line", showInfo(
        '<div style="font:12px sans-serif;color:#0f172a;">' +
        '<b style="color:#b91c1c;">통행 불가</b><br/>위험영역과 겹치는 구간</div>'
      ));
      map.on("mouseleave", "blocked-roads-line", hideInfo);

      setMapReady(true);
    });
    map.on("error", (e) => console.error("[maplibre error]", e.error?.message ?? e));

    // 컨테이너가 flex 레이아웃 안이라 초기 마운트 시 높이 측정이 늦게 확정되는 경우가
    // 있어(캔버스가 기본 300px로 굳는 버그), 컨테이너 크기 변화를 직접 감시해 재조정한다.
    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(mapContainer.current);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  const flyTo = useCallback((center: [number, number], zoom: number) => {
    mapRef.current?.flyTo({ center, zoom, pitch: DEFAULT_PITCH, bearing: -20, duration: 2000 });
    setSelectedRegion(null);
  }, []);

  // 검색어 입력 300ms 디바운스 — 시/군/구/읍/면/동 이름 부분일치 (api_server.py /search)
  useEffect(() => {
    const q = searchQuery.trim();
    if (!q) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 입력이 비었을 때 즉시 목록을 비우는 동기 초기화
      setSearchResults([]);
      return;
    }
    setSearching(true);
    searchSlow.start();
    const id = setTimeout(() => {
      searchAdmin(q)
        .then(setSearchResults)
        .catch(() => setSearchResults([]))
        .finally(() => {
          searchSlow.stop();
          setSearching(false);
        });
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- searchSlow.start/stop은 useSlowLoading이 매 렌더 새 함수를 반환하지 않게 안정적으로 관리
  }, [searchQuery]);

  const goToSearchResult = useCallback((result: AdminSearchResult) => {
    const map = mapRef.current;
    if (!map) return;
    const [minLon, minLat, maxLon, maxLat] = result.bbox;
    map.fitBounds(
      [
        [minLon, minLat],
        [maxLon, maxLat],
      ],
      { padding: 60, bearing: -20, pitch: DEFAULT_PITCH, duration: 1500 }
    );
    setSelectedRegion(result);
    setSearchQuery("");
    setSearchResults([]);
  }, []);

  // 선택된 지역(검색으로 이동한 곳)이 바뀔 때마다 노란색 강조를 다시 그린다
  useEffect(() => {
    if (!mapReady) return;
    highlightUpdateRef.current?.(selectedRegion?.code ?? null);
  }, [mapReady, selectedRegion]);

  // §7 고립 판정 — 이제 슬라이더가 만든 what-if 볼륨이 아니라 모형이 실제로 낸
  // 위험영역(Module A 시간축 폴리곤 + Module B 침수 폴리곤)을 그대로 hazard로 넘긴다.
  // 도로망에서 그 지오메트리와 겹치는 엣지를 끊고 대피소 도달 가능성을 다시 푼다.
  // 스크러버를 드래그하면 프레임마다 바뀌므로 디바운스한다.
  const scheduleIsolationCheck = useCallback((hazards: Feature<Polygon | MultiPolygon>[]) => {
    if (isolationDebounceRef.current) clearTimeout(isolationDebounceRef.current);

    const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
    const setLayer = (id: string, data: GeoJSON.FeatureCollection) =>
      (mapRef.current?.getSource(id) as GeoJSONSource | undefined)?.setData(data);

    // MultiPolygon 하나로 합쳐 보낸다 — 좌표 배열을 이어 붙이는 것이라 union 연산이
    // 아니고, 겹쳐도 도로 교차 판정 결과는 같다(비용만 아낀다).
    const rings: GeoJSON.Position[][][] = [];
    for (const f of hazards) {
      if (f.geometry.type === "Polygon") rings.push(f.geometry.coordinates);
      else rings.push(...f.geometry.coordinates);
    }
    if (rings.length === 0) {
      setLayer("isolated-areas", EMPTY);
      setLayer("blocked-roads", EMPTY);
      setHazardIsolatedCount(null);
      return;
    }
    const hazardGeometry: GeoJSON.MultiPolygon = { type: "MultiPolygon", coordinates: rings };

    isolationDebounceRef.current = setTimeout(() => {
      const activeRegion = DEMO_REGIONS[isolationRegionRef.current];
      checkIsolation(
        activeRegion.isolationBbox,
        activeRegion.shelters.map(({ lon, lat }) => ({ lon, lat })),
        hazardGeometry
      )
        .then((result) => {
          setLayer("isolated-areas", result.isolated_areas);
          setLayer("blocked-roads", result.blocked_roads ?? EMPTY);
          setHazardIsolatedCount(result.isolated_building_count);
        })
        .catch(() => {
          setLayer("blocked-roads", EMPTY);
          setHazardIsolatedCount(null);
        });
    }, 600);
  }, []);

  // 시간축 데이터는 경보 하나당 한 번만 받는다(프레임 39 + 폴리곤 한 자릿수).
  // 스크럽할 때마다 서버를 부르면 끊기므로 통째로 들고 클라이언트에서 거른다.
  useEffect(() => {
    let cancelled = false;
    getAlertTimeline(SANGCHEONG_DEMO_INPUT.alert_id)
      .then((t) => {
        if (cancelled) return;
        setTimeline(t);
        if (t.httpStatus !== undefined) {
          // 서버가 200을 안 줬다 — 왜인지는 /health가 알고 있다.
          diagnoseFailure("시간축 조회", TIMELINE_ROUTE).then((msg) => {
            if (!cancelled) setTimelineError(msg);
          });
        } else {
          setTimelineError(null);
        }
        // 처음 보이는 시각은 "탐지 시각"으로 맞춘다 — 빈 지도로 시작하면 무엇을
        // 보고 있는지 알 수 없고, 마지막 프레임으로 시작하면 번져가는 과정이 안 보인다.
        const detected = t.markers?.detected;
        const idx = detected ? t.frames.findIndex((f) => f.time === detected) : -1;
        setFrameIdx(idx >= 0 ? idx : Math.max(t.frames.length - 1, 0));
      })
      .catch(() => {
        if (cancelled) return;
        setTimeline(null);
        diagnoseFailure("시간축 조회", TIMELINE_ROUTE).then((msg) => {
          if (!cancelled) setTimelineError(msg);
        });
      });
    return () => {
      cancelled = true;
    };
  }, [alertNonce]);

  const frames = timeline?.frames ?? [];
  const currentFrame = frames[frameIdx] ?? null;
  // 막대 높이 기준. 0으로 나누지 않도록 하한을 둔다(전 구간 무강우면 막대가 다 최소높이).
  const maxFrameRain = Math.max(1, ...frames.map((f) => f.rn_mm));
  // 현재 시각까지 도달한 위험영역 개수 — 스크럽하면 이 숫자가 올라가는 것이
  // '점차 증가한다'를 숫자로도 보여 준다.
  // 시간 스크러버를 띄울 조건 — 프레임과 위험영역이 있고, 그 데이터의 AOI(산청)를
  // 보고 있을 때만. 다른 지역에서 산청 시간축을 띄우면 그 지역 수치처럼 읽힌다.
  const showScrubber =
    shelterRegion === "sancheong" && (timeline?.available ?? false) && frames.length > 0;
  // 침수 폴리곤이 없으면 카운트 자체가 의미 없으므로 파생값에서 null로 눌러 준다.
  const floodedInRange = floodFeatures.length === 0 ? null : floodedBuildingCount;
  const riskReachedCount = (timeline?.risk.features ?? []).filter(
    (f) => currentFrame !== null && Number(f.properties?.arrival_hour) <= currentFrame.hour
  ).length;
  // 위험영역이 새로 생기는 시각들 — 39프레임 중 6개뿐이라 표시가 없으면 어디를 봐야
  // 할지 알 수 없다. 막대 아래에 점으로 찍는다.
  // 범례에 쓸 한 줄 — 두 임계의 면적 차이가 크다는 걸 숫자로 보여 준다(0.0103 vs
  // 0.2377km²). 서버가 준 값만 쓰고 화면에서 계산하지 않는다.
  const riskLevelNote = (() => {
    const w = timeline?.levels?.find((l) => l.level === "warning");
    const c = timeline?.levels?.find((l) => l.level === "critical");
    if (!w?.area_km2 || !c?.area_km2) return null;
    return `(${w.area_km2}km² / ${c.area_km2}km²)`;
  })();

  const arrivalHours = new Set(
    (timeline?.risk.features ?? []).map((f) => Number(f.properties?.arrival_hour))
  );

  // 재생 — 1초에 한 프레임씩. 마지막에 닿으면 자동으로 멈춘다(되감기 없음:
  // 루프가 돌면 "지금이 언제인지"가 다시 흐려진다).
  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const id = setInterval(() => {
      setFrameIdx((i) => {
        if (i >= frames.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 900);
    return () => clearInterval(id);
  }, [playing, frames.length]);

  // 현재 시각까지 도달한 위험영역만 누적해서 3D로 세운다.
  useEffect(() => {
    if (!mapReady) return;
    const source = mapRef.current?.getSource("landslide-risk") as GeoJSONSource | undefined;
    if (!source) return;
    const hour = currentFrame?.hour;
    const reached =
      hour === undefined
        ? []
        : (timeline?.risk.features ?? []).filter((f) => {
            const h = Number(f.properties?.arrival_hour);
            return Number.isFinite(h) && h <= hour;
          });
    const withAge = reached.map((f) => ({
      ...f,
      properties: { ...f.properties, age: (hour ?? 0) - Number(f.properties?.arrival_hour) },
    })) as Feature<Polygon | MultiPolygon>[];
    source.setData({ type: "FeatureCollection", features: withAge } as FeatureCollection);
    setRiskBounds(featuresBounds(withAge));

    // 고립 판정은 산사태 위험영역 + 침수 범위를 함께 본다. 침수는 시간축이 없어
    // (SFINCS 최대침수심) 프레임과 무관하게 항상 최대 범위로 들어간다.
    scheduleIsolationCheck([...withAge, ...floodFeatures]);
  }, [mapReady, timeline, currentFrame, floodFeatures, scheduleIsolationCheck]);

  // 대피소 찾기 패널(EvacuationPanel)에서 고른 경로 — app/page.tsx가 상태를 끌어올려
  // route prop으로 내려주는 구조(§6.9)라, 여기서는 그 prop이 바뀔 때마다 그리기만 한다.
  useEffect(() => {
    if (!mapReady) return;
    const currentMap = mapRef.current;
    if (!currentMap) return;
    const routeSource = currentMap.getSource("evacuation-route") as GeoJSONSource | undefined;
    const markerSource = currentMap.getSource("evacuation-markers") as GeoJSONSource | undefined;
    if (!route) {
      routeSource?.setData({ type: "FeatureCollection", features: [] });
      markerSource?.setData({ type: "FeatureCollection", features: [] });
      return;
    }
    const { origin, destination, label, path } = route;
    const lineCoordinates = path && path.length > 1 ? path : [origin, destination];
    routeSource?.setData({
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: lineCoordinates } },
      ],
    } as FeatureCollection);
    markerSource?.setData({
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: { role: "origin" }, geometry: { type: "Point", coordinates: origin } },
        { type: "Feature", properties: { role: "destination", label }, geometry: { type: "Point", coordinates: destination } },
      ],
    } as FeatureCollection);
    const lons = [origin[0], destination[0]];
    const lats = [origin[1], destination[1]];
    currentMap.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 120, pitch: DEFAULT_PITCH, bearing: -20, duration: 1500 }
    );
  }, [mapReady, route]);

  useEffect(() => {
    if (!mapReady) return;
    const areasSource = mapRef.current?.getSource("isolated-areas") as GeoJSONSource | undefined;
    areasSource?.setData(isolatedAreas ?? { type: "FeatureCollection", features: [] });
  }, [mapReady, isolatedAreas]);

  useEffect(() => {
    if (!mapReady) return;
    const source = mapRef.current?.getSource("blocked-roads") as GeoJSONSource | undefined;
    source?.setData(blockedRoads ?? { type: "FeatureCollection", features: [] });
  }, [mapReady, blockedRoads]);

  // 현재 지역 대피소 전체를 지도에 상시 표시한다(산청 8 / 강남 15).
  useEffect(() => {
    if (!mapReady) return;
    const source = mapRef.current?.getSource("shelters") as GeoJSONSource | undefined;
    if (!source) return;
    source.setData({
      type: "FeatureCollection",
      features: DEMO_REGIONS[shelterRegion].shelters.map((s) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
        properties: { shelter_id: s.id, name: s.name, capacity: s.capacity },
      })),
    });
  }, [mapReady, shelterRegion]);

  // Module B의 실제 침수 폴리곤을 받아 3D로 세운다. 경보가 아직 등록되지 않았거나
  // (트리거 전) 침수심 래스터가 없는 AOI면 404/빈 배열이 오는데, 그건 오류가 아니라
  // "계산된 침수가 없음"이므로 조용히 비워 둔다 — 콘솔 에러로 올리지 않는다.
  useEffect(() => {
    if (!mapReady) return;
    let cancelled = false;

    getAlertGeojson(SANGCHEONG_DEMO_INPUT.alert_id)
      .then((fc) => {
        if (cancelled) return;
        const source = mapRef.current?.getSource("flood-model") as GeoJSONSource | undefined;
        if (!source) return;
        const inundation = fc.features.filter(
          (f) => f.properties?.kind === "inundation"
        ) as Feature<Polygon | MultiPolygon>[];
        source.setData({ type: "FeatureCollection", features: inundation });
        setFloodFeatures(inundation);
        const depths = inundation
          .map((f) => Number(f.properties?.depth_p90_m))
          .filter((v) => Number.isFinite(v));
        setModelFloodDepth(depths.length ? Math.max(...depths) : null);
      })
      .catch(() => {
        if (cancelled) return;
        const source = mapRef.current?.getSource("flood-model") as GeoJSONSource | undefined;
        source?.setData({ type: "FeatureCollection", features: [] });
        setFloodFeatures([]);
        setModelFloodDepth(null);
      });

    return () => {
      cancelled = true;
    };
  }, [mapReady, alertNonce]);

  // 침수 범위 안에 들어오는 건물 수 — 3D 볼륨이 건물을 덮는 게 주된 증거이고 이건
  // 보조 지표다. 예전에는 슬라이더가 만든 what-if 폴리곤을 기준으로 셌는데, 이제는
  // Module B가 실제로 낸 침수 폴리곤을 그대로 쓴다.
  //
  // 화면에 그려진 건물만 셀 수 있으므로(queryRenderedFeatures) 카메라가 멀면 과소
  // 계수된다 — "약 N개"로 표기하는 이유다. 타일이 다 올라온 뒤에 세려고 idle을 기다린다.
  useEffect(() => {
    if (!mapReady) return;
    const currentMap = mapRef.current;
    if (!currentMap) return;
    // 침수가 없으면 아예 세지 않는다 — 표시는 아래 floodedInRange가 null로 처리한다
    // (effect 본문에서 setState 하면 렌더가 한 번 더 도는 것을 막기 위해 파생값으로 둠).
    if (floodFeatures.length === 0) return;
    let cancelled = false;
    const count = () => {
      if (cancelled) return;
      try {
        const rendered = currentMap.queryRenderedFeatures(undefined, {
          layers: ["vworld-buildings-3d", "buildings-3d-osm"].filter((id) => currentMap.getLayer(id)),
        });
        const seen = new Set<string | number>();
        let n = 0;
        for (const f of rendered) {
          const key = f.id ?? JSON.stringify(f.properties);
          if (seen.has(key)) continue;
          seen.add(key);
          const c = centroid(f as unknown as Feature<Polygon | MultiPolygon>);
          if (floodFeatures.some((poly) => booleanPointInPolygon(c, poly))) n++;
        }
        setFloodedBuildingCount(n);
      } catch {
        setFloodedBuildingCount(null);
      }
    };
    currentMap.once("idle", count);
    return () => {
      cancelled = true;
      currentMap.off("idle", count);
    };
  }, [mapReady, floodFeatures]);

  useEffect(() => {
    if (!mapReady || !focusBbox) return;
    const currentMap = mapRef.current;
    if (!currentMap) return;
    const [minLon, minLat, maxLon, maxLat] = focusBbox.bbox;
    currentMap.fitBounds(
      [
        [minLon, minLat],
        [maxLon, maxLat],
      ],
      { padding: 100, pitch: DEFAULT_PITCH, bearing: -20, duration: 1200, maxZoom: 17 }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, focusBbox?.nonce]);

  // §6.8 폴백 ① — 지도 클릭으로 출발지 선택. pickOrigin이 켜져 있는 동안만 커서를
  // 십자선으로 바꾸고 다음 클릭 한 번만 잡아서 부모(EvacuationPanel)로 올려보낸다.
  useEffect(() => {
    if (!mapReady || !pickOrigin) return;
    const currentMap = mapRef.current;
    if (!currentMap) return;
    currentMap.getCanvas().style.cursor = "crosshair";
    const handler = (e: { lngLat: { lng: number; lat: number } }) => {
      onOriginPicked?.([e.lngLat.lng, e.lngLat.lat]);
    };
    currentMap.once("click", handler);
    return () => {
      currentMap.off("click", handler);
      currentMap.getCanvas().style.cursor = "";
    };
  }, [mapReady, pickOrigin, onOriginPicked]);

  return (
    <div className="relative h-full min-h-[600px] w-full">
      <div ref={mapContainer} className="h-full w-full" />

      {mapFailed && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950 p-8 text-center">
          <div className="max-w-md space-y-2">
            <p className="text-sm font-semibold text-slate-200">3D 지도를 표시할 수 없습니다</p>
            <p className="text-xs text-slate-400">
              이 브라우저·기기에서 WebGL을 쓸 수 없어 지도만 꺼졌습니다. 원격 데스크톱,
              GPU 가속이 꺼진 환경, 일부 가상머신에서 발생합니다. 위·오른쪽 메뉴의
              분석 패널은 그대로 사용할 수 있습니다.
            </p>
          </div>
        </div>
      )}

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-4 pt-20">
        <div className="pointer-events-auto flex flex-col items-start gap-2">
          <button
            onClick={() => setSearchOpen((v) => !v)}
            aria-label="주소 검색 열기/닫기"
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-sky-300/20 bg-sky-500/60 text-white shadow-lg backdrop-blur-xl transition-transform hover:scale-105 hover:bg-sky-400/70"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.3-4.3" />
            </svg>
          </button>

          {searchOpen && (
            <div className="max-w-sm rounded-xl border border-white/15 bg-slate-950/60 p-4 shadow-lg backdrop-blur-xl">
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="시/군/구/읍/면/동 검색 (예: 산청군, 생비량면, 강남동)"
                  className="w-full rounded-md border border-slate-700 bg-slate-900/60 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-sky-600 focus:outline-none"
                />
                {searching && (
                  <span className="absolute right-2 top-1.5 text-xs text-slate-500">
                    {searchSlow.slow ? "서버 깨우는 중…" : "검색 중…"}
                  </span>
                )}
                {searchResults.length > 0 && (
                  <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-slate-700 bg-slate-900 shadow-lg">
                    {searchResults.map((r) => (
                      <li key={`${r.level}-${r.code}`}>
                        <button
                          onClick={() => goToSearchResult(r)}
                          className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs text-slate-200 hover:bg-sky-950/60"
                        >
                          <span
                            className={`shrink-0 rounded px-1 py-0.5 text-[10px] ${
                              r.level === "sido"
                                ? "bg-sky-900 text-sky-300"
                                : r.level === "sigungu"
                                  ? "bg-emerald-900 text-emerald-300"
                                  : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {r.level === "sido" ? "도" : r.level === "sigungu" ? "시군구" : "읍면동"}
                          </span>
                          <span className="truncate">{r.full_name}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {selectedRegion && (
                <p className="mt-2 text-xs">
                  <span className="rounded bg-amber-900/50 px-1.5 py-0.5 text-amber-300">노란 경계</span>{" "}
                  <span className="text-slate-300">{selectedRegion.full_name}</span>
                </p>
              )}

              <p className="mt-2 text-xs text-slate-400">
                §5 Module UI-3D — MapLibre GL(지형) + 행정경계 시도/시군구/읍면동 3계층(사용자 제공
                데이터, 전국)을 뷰포트 기준으로 실시간 표시. 검색해서 선택한 지역만 노란색으로 강조됩니다.
              </p>
              <p className="mt-2 text-xs text-slate-500">
                🖱 좌클릭 드래그: 이동 · 스크롤: 줌 · <span className="text-slate-300">우클릭(또는 Ctrl) 드래그: 회전/기울기</span>
              </p>
              <p className="mt-2 text-xs text-amber-300/70">
                건물·도로 모두 브이월드 실데이터(§2.3, §2.6) — 건물은 건물통합정보(층수×3m 근사
                높이), 도로는 국가교통정보센터 표준노드링크(교량·고가차도는 지면에서 띄운 데크).
              </p>
              <div className="mt-2 flex gap-1.5">
                {TEST_LOCATIONS.map((loc) => (
                  <button
                    key={loc.label}
                    onClick={() => {
                      flyTo(loc.center, loc.zoom);
                      isolationRegionRef.current = loc.regionKey;
                      setShelterRegion(loc.regionKey);
                      onRegionSelect?.(loc.regionKey);
                    }}
                    className="flex-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-sky-600 hover:text-sky-300"
                  >
                    {loc.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="pointer-events-auto w-72 rounded-xl border border-white/15 bg-slate-950/60 p-4 text-xs shadow-lg backdrop-blur-xl">
          <p className="font-semibold text-slate-200">지금 지도에 올라와 있는 것</p>
          <p className="mt-1 text-slate-400">{DEMO_REGIONS[shelterRegion].label}</p>

          {shelterRegion === "sancheong" ? (
            <div className="mt-3 space-y-2">
              <div className="flex items-start gap-2">
                <span className="mt-0.5 flex shrink-0 flex-col gap-0.5">
                  <span className="block h-3 w-3 rounded-sm" style={{ background: RISK_COLOR_RECENT }} />
                  <span className="block h-3 w-3 rounded-sm" style={{ background: RISK_CRIT_RECENT }} />
                </span>
                <div>
                  <p className="text-slate-200">산사태 위험영역 · Module A</p>
                  <p className="text-slate-500">
                    시각별 도달 영역. <span style={{ color: RISK_COLOR_NEW }}>주황 P≥0.5</span>(대응 시작 기준)
                    안에 <span style={{ color: RISK_CRIT_NEW }}>빨강 P≥0.7</span>이 들어 있습니다.
                    {riskLevelNote && <> {riskLevelNote}</>}
                  </p>
                  <p className="mt-0.5 text-slate-500">
                    <span className="text-amber-300/80">높이는 표시용</span> — 토사 퇴적깊이 모형이
                    없어 높이에 뜻이 없습니다. 0.7을 더 높게 세운 건 0.5에 가려지지 않게 하려는 것뿐입니다.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="mt-0.5 h-3 w-3 shrink-0 rounded-sm bg-sky-500" />
                <div>
                  <p className="text-slate-200">침수 범위 · Module B</p>
                  <p className="text-slate-500">
                    SFINCS <span className="text-sky-300">최대</span> 침수심
                    {modelFloodDepth !== null && <> (최심 {modelFloodDepth.toFixed(1)}m)</>} — 시간축이 없어
                    프레임과 무관하게 항상 최대 범위입니다.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="mt-0.5 h-3 w-3 shrink-0 rounded-sm bg-red-600" />
                <p className="text-slate-200">
                  통행 불가 도로 <span className="text-slate-500">· 위험영역과 겹쳐 끊긴 구간</span>
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="mt-0.5 h-3 w-3 shrink-0 rounded-full bg-emerald-400" />
                <p className="text-slate-200">대피소 {DEMO_REGIONS[shelterRegion].shelters.length}곳</p>
              </div>
            </div>
          ) : (
            // 서울 강남은 건물·도로·대피소는 다 있는데 재해 모형이 없다. 빈 지도만
            // 보여주면 "고장난 건가"로 읽히므로, 무엇이 있고 무엇이 없는지를 그 자리에 쓴다.
            <div className="mt-3 space-y-2">
              <p className="rounded-md bg-slate-800/60 px-2 py-1.5 text-slate-300">
                이 지역은 <span className="text-amber-300">재해 모형 미구축</span>입니다.
              </p>
              <ul className="space-y-1 text-slate-400">
                <li>○ 없음 — 산사태 위험영역(Module A 사전계산은 산청 AOI만), 침수심 래스터(SFINCS 격자 미구축)</li>
                <li>
                  ● 있음 — 건물·도로 3D(브이월드 실데이터), 대피소{" "}
                  {DEMO_REGIONS[shelterRegion].shelters.length}곳, 경로 탐색, 고립 판정
                </li>
              </ul>
              <p className="text-slate-500">
                고립 분석 패널에서 위험영역을 직접 지정하면 이 지역에서도 끊긴 도로·고립 건물이 그대로
                계산됩니다 — 없는 것은 입력이지 기능이 아닙니다.
              </p>
            </div>
          )}

          {floodedInRange !== null && (
            <p className="mt-3 rounded-md bg-sky-950/50 px-2 py-1.5 text-sky-300">
              침수 범위 안 건물 약 <span className="font-bold">{floodedInRange}</span>개
            </p>
          )}
          {hazardIsolatedCount !== null && (
            <p className="mt-2 rounded-md bg-fuchsia-950/50 px-2 py-1.5 text-fuchsia-300">
              §7 고립 위험 건물 약 <span className="font-bold">{hazardIsolatedCount}</span>개 (대피소 도달 불가)
            </p>
          )}
        </div>
      </div>

      {/* 시간 스크러버 — "지금 보는 게 언제의 예측인가"를 화면에서 읽을 수 있게 하는 가장
          중요한 요소라 가운데 아래에 넓게 깔았다. 날짜·요일·시각을 그대로 쓰고, 그 시각의
          시간강우와 24시간 누적을 같이 보여 준다. 막대는 프레임별 시간강우이고, 우리 탐지 /
          공식 경보 시각을 같은 줄에 적어 "언제 잡았고 공식은 언제였는지"가 한 화면에서 비교된다. */}
      {/* 시간축은 산청 AOI의 사전계산 결과다. 서울로 옮겨 놓고 그대로 띄워 두면
          '강남에 위험영역 2곳'처럼 읽히므로 지역이 바뀌면 내린다. */}
      {showScrubber && timeline && currentFrame && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center p-4">
          <div className="pointer-events-auto w-full max-w-3xl rounded-xl border border-white/15 bg-slate-950/75 p-4 shadow-lg backdrop-blur-xl">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-slate-500">예측 시각</p>
                <p className="font-mono text-2xl font-bold text-slate-100">{frameLabel(currentFrame.time)}</p>
              </div>
              <div className="flex items-end gap-4 text-right">
                <div>
                  <p className="text-[11px] text-slate-500">시간강우</p>
                  <p className="font-mono text-lg text-sky-300">{currentFrame.rn_mm.toFixed(1)}mm</p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-500">24h 누적</p>
                  <p className="font-mono text-lg text-sky-200">{currentFrame.cum24_mm.toFixed(0)}mm</p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-500">위험영역</p>
                  <p className="font-mono text-lg text-red-400">{riskReachedCount}곳</p>
                </div>
              </div>
            </div>

            {/* 시간강우 막대 — 클릭하면 그 시각으로 점프한다 */}
            <div className="mt-3 flex h-12 items-end gap-[2px]">
              {frames.map((f, i) => (
                <button
                  key={f.time}
                  onClick={() => {
                    setPlaying(false);
                    setFrameIdx(i);
                  }}
                  title={`${frameLabel(f.time)} · ${f.rn_mm.toFixed(1)}mm`}
                  aria-label={`${frameLabel(f.time)}로 이동`}
                  className="group relative h-full flex-1"
                >
                  <span
                    className={`absolute bottom-0 block w-full rounded-sm transition-colors ${
                      i === frameIdx
                        ? "bg-amber-300"
                        : i < frameIdx
                          ? "bg-sky-500/70 group-hover:bg-sky-400"
                          : "bg-slate-700 group-hover:bg-slate-500"
                    }`}
                    style={{ height: `${Math.max((f.rn_mm / maxFrameRain) * 100, 4)}%` }}
                  />
                  {/* 이 시각에 위험영역이 새로 생긴다 — 39개 중 6개뿐이라 이 표시가
                      없으면 어느 시각을 봐야 하는지 알 수 없다 */}
                  {arrivalHours.has(f.hour) && (
                    <span className="absolute -bottom-1.5 left-1/2 block h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-orange-400" />
                  )}
                </button>
              ))}
            </div>

            <input
              type="range"
              min={0}
              max={frames.length - 1}
              step={1}
              value={frameIdx}
              onChange={(e) => {
                setPlaying(false);
                setFrameIdx(Number(e.target.value));
              }}
              aria-label="예측 시각 이동"
              className="mt-2 w-full accent-amber-400"
            />

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPlaying((v) => !v)}
                  className="rounded-md border border-slate-700 px-3 py-1 text-slate-200 hover:border-amber-500 hover:text-amber-300"
                >
                  {playing ? "❚❚ 정지" : "▶ 시간 재생"}
                </button>
                <button
                  onClick={() => {
                    setPlaying(false);
                    setFrameIdx(0);
                  }}
                  className="rounded-md border border-slate-700 px-2 py-1 text-slate-400 hover:text-slate-200"
                >
                  ↺ 처음
                </button>
                <button
                  onClick={() => {
                    if (!riskBounds) return;
                    mapRef.current?.fitBounds(riskBounds, {
                      padding: 160,
                      pitch: DEFAULT_PITCH,
                      bearing: -20,
                      duration: 1600,
                      maxZoom: 15.5,
                    });
                  }}
                  disabled={!riskBounds}
                  className="rounded-md border border-orange-700/60 px-2 py-1 text-orange-300 hover:border-orange-500 hover:text-orange-200 disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-600"
                  title={riskBounds ? "이 시각의 위험영역이 다 들어오게 카메라를 옮긴다" : "이 시각에는 위험영역이 없다"}
                >
                  ⤢ 위험영역으로
                </button>
              </div>
              <div className="flex items-center gap-3 text-[11px] text-slate-400">
                <span>
                  🟡 우리 탐지 <span className="font-mono text-amber-300">{hhmm(timeline.markers.detected)}</span>
                </span>
                <span>
                  📨 발송 <span className="font-mono text-slate-300">{hhmm(timeline.markers.alert_sent)}</span>
                </span>
                <span>
                  🏛 공식 경보{" "}
                  <span className="font-mono text-slate-300">{hhmm(timeline.markers.official_warning)}</span>
                </span>
              </div>
            </div>

            <p className="mt-2 text-[11px] text-slate-500">
              MODEL · 트랙① 사전계산 위험영역({timeline.scenario} {timeline.level})을 실측 강우로 시간마다 구동한
              결과입니다. 막대는 그 시각의 시간강우. 침수는 시간축이 없어 최대 범위로 고정됩니다.
            </p>
          </div>
        </div>
      )}

      {!showScrubber && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center p-4">
          <p className="pointer-events-auto rounded-lg border border-white/10 bg-slate-950/75 px-3 py-2 text-xs text-slate-400 backdrop-blur-xl">
            {shelterRegion !== "sancheong"
              ? "시간축 없음 — 시각별 위험영역은 산청 AOI만 사전계산돼 있습니다"
              : (timelineError ?? `시간축 없음 — ${timeline?.reason ?? "시계열 위험영역 레이어가 없습니다"}`)}
          </p>
        </div>
      )}
    </div>
  );
}
