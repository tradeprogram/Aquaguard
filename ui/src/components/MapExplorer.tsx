"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Map as MapLibreMap,
  NavigationControl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import buffer from "@turf/buffer";
import centroid from "@turf/centroid";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import { lineString as turfLineString } from "@turf/helpers";
import type { Feature, FeatureCollection, LineString, MultiLineString, Polygon, MultiPolygon } from "geojson";
import {
  API_BASE,
  getBoundaries,
  getVWorldBuildings,
  getVWorldRivers,
  getVWorldRoads,
  searchAdmin,
  type AdminLevel,
  type AdminSearchResult,
} from "@/lib/api";
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
const AOI_KEYS = ["sancheong", "seoul"] as const;
type AOIKey = (typeof AOI_KEYS)[number];
const AOI_BOUNDS: Record<AOIKey, [number, number, number, number]> = {
  sancheong: [127.688782, 35.219031, 128.114735, 35.576211],
  seoul: [126.764484, 37.428985, 127.183795, 37.701455],
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

// --- 토사 유실 / 침수 볼륨 시뮬레이터 ---
// Module A/B가 아직 목업이라 risk_polygons/inundation_extent_5179 지오메트리가 없다
// (contracts/module_a·b.example.json 참조) — 실제 예측값이 아니라 산청 상능마을
// 지형에 맞춰 손으로 배치한 흐름 경로이고, 깊이는 슬라이더로 사용자가 직접 조작하는
// what-if 값이다. 실제 물리모델이 아님을 항상 명시할 것(문서 §6 불확실성 표기 원칙).
//
// 지역 미터 오프셋 → 위경도 근사 변환(적도 기준 111.32km/1°, 이 위도대에서 수백m~1km
// 규모 흐름 시각화에는 충분한 정밀도).
function metersToLonLat(origin: [number, number], dxM: number, dyM: number): [number, number] {
  const [lon, lat] = origin;
  const dLon = dxM / (111320 * Math.cos((lat * Math.PI) / 180));
  const dLat = dyM / 110540;
  return [lon + dLon, lat + dLat];
}

// 산청 상능마을(산사태 트리거 지점)에서 남동쪽 사면 아래로 흐르는 짧고 가파른 경로
const DEBRIS_CENTERLINE_M: [number, number][] = [
  [0, 0],
  [140, -90],
  [300, -160],
  [420, -280],
];
// 같은 계곡을 따라 더 길게 흘러가는 하천범람 경로(Module B 트리거 방향)
const FLOOD_CENTERLINE_M: [number, number][] = [
  [50, -250],
  [180, -420],
  [420, -560],
  [700, -650],
  [980, -700],
];

interface FlowBandSpec {
  fractionOfWidth: number; // 바깥쪽부터 안쪽 순서
  depthFactor: number; // 슬라이더 깊이값에 곱해지는 비율
  color: [number, number, number, number];
}
// 바깥(옅은 노랑) → 안(진한 빨강): 토사, 바깥(옅은 하늘) → 안(진한 파랑): 침수
const DEBRIS_BANDS: FlowBandSpec[] = [
  { fractionOfWidth: 1.0, depthFactor: 0.3, color: [253, 224, 71, 200] },
  { fractionOfWidth: 0.66, depthFactor: 0.6, color: [249, 115, 22, 220] },
  { fractionOfWidth: 0.35, depthFactor: 1.0, color: [220, 38, 38, 235] },
];
const FLOOD_BANDS: FlowBandSpec[] = [
  { fractionOfWidth: 1.0, depthFactor: 0.35, color: [125, 211, 252, 170] },
  { fractionOfWidth: 0.66, depthFactor: 0.65, color: [56, 189, 248, 195] },
  { fractionOfWidth: 0.35, depthFactor: 1.0, color: [29, 78, 216, 220] },
];

function buildFlowBands(
  origin: [number, number],
  centerlineM: [number, number][],
  baseWidthM: number,
  depthM: number,
  bands: FlowBandSpec[]
): Feature<Polygon | MultiPolygon>[] {
  const linePts = centerlineM.map(([dx, dy]) => metersToLonLat(origin, dx, dy));
  const line = turfLineString(linePts);
  const out: Feature<Polygon | MultiPolygon>[] = [];
  for (const band of bands) {
    const width = (baseWidthM * band.fractionOfWidth) / 2;
    try {
      const poly = buffer(line, width, { units: "meters", steps: 8 });
      if (poly) {
        // MapLibre의 fill-extrusion-color는 CSS 색상 문자열이 필요하다 — [r,g,b,a] 배열을
        // GeoJSON 속성에 그대로 넣으면(deck.gl 스타일) 색상 평가가 실패해 색이 안 먹는다.
        const [r, g, b, a] = band.color;
        poly.properties = {
          depth: Math.max(depthM * band.depthFactor, 0.15),
          color: `rgba(${r}, ${g}, ${b}, ${a / 255})`,
        };
        out.push(poly);
      }
    } catch {
      // 극단적인 슬라이더 값(0에 가까움) 등으로 버퍼링이 실패하면 그 밴드는 건너뜀
    }
  }
  return out;
}

// 데모 AOI(산청·서울) 빠른 이동 버튼 — 이 두 지역만 정적 벡터타일로 완전히
// 캐싱돼 있다(§AOI_BOUNDS). 부산 등 다른 지역도 라이브 V-World 폴백으로 여전히
// 뜨긴 하지만, 데모 스코프 밖이라 2026-08-29 사용자 요청으로 버튼에서 제외.
const TEST_LOCATIONS: { label: string; center: [number, number]; zoom: number }[] = [
  { label: "산청 상능마을", center: INITIAL_CENTER, zoom: 12.5 },
  { label: "서울 강남", center: [127.0276, 37.4979], zoom: 16 },
];

// EvacuationPanel(§6)에서 선택한 대피 경로 — 카카오/네이버 실경로 API 붙기 전까지는
// 출발지→대피소 직선(하버사인 근사)만 표시한다(HANDOFF.md §6.9).
export interface EvacuationRoute {
  origin: [number, number]; // [lon, lat]
  destination: [number, number]; // [lon, lat]
  label: string;
}

interface MapExplorerProps {
  route?: EvacuationRoute | null;
  // §6.8 폴백 ① — 위치 권한이 없어도 지도를 클릭해 출발지를 고를 수 있게. true인
  // 동안 커서가 십자선으로 바뀌고, 다음 클릭 좌표를 onOriginPicked로 한 번 올려보낸다.
  pickOrigin?: boolean;
  onOriginPicked?: (lonLat: [number, number]) => void;
}

export default function MapExplorer({ route = null, pickOrigin = false, onOriginPicked }: MapExplorerProps = {}) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const simUpdateRef = useRef<((debrisM: number, floodM: number) => void) | null>(null);
  const highlightUpdateRef = useRef<((code: string | null) => void) | null>(null);
  // 현재 카메라 중심이 산청·서울 AOI 안인지 — 안이면 정적 타일을 보여주고 실시간
  // V-World fetch는 건너뛴다(아래 syncAOILayers/updateVWorld* 참조).
  const aoiRef = useRef<AOIKey | null>(null);

  const [mapReady, setMapReady] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<AdminSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const searchSlow = useSlowLoading();
  const [selectedRegion, setSelectedRegion] = useState<AdminSearchResult | null>(null);
  const [debrisDepth, setDebrisDepth] = useState(0);
  const [floodDepth, setFloodDepth] = useState(0);
  const [floodedBuildingCount, setFloodedBuildingCount] = useState<number | null>(null);

  // 지도 초기화 (1회)
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    const map = new MapLibreMap({
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
      map.addLayer({ id: "hills", type: "hillshade", source: "terrain", paint: { "hillshade-exaggeration": 0.5 } });

      // 2026-08-28~29: 원래 여기서 줌에 따라 exaggeration을 1.3→0.12까지 실시간으로
      // 낮추는 taper가 있었다(z15+에서 DEM 오버줌 스파이크를 감추려는 의도). 그런데
      // 건물이 실제 height_m로 압출되기 시작한 뒤(2026-08-29) 실측해보니, 카메라를
      // 고정한 채 exaggeration만 1.3→0.12로 바꿨을 때 같은 건물이 화면에서 69px나
      // 움직였다 — exaggeration이 지형 메시의 실제 고도를 바꾸는 값이라, 경사면 위
      // 건물의 "땅" 자체가 줌에 따라 오르내리면서 건물이 "땅에 박혔다 솟았다"
      // 하는 것처럼 보이는 원인이었다(사용자 리포트로 재현·근본원인 확인).
      // 지형 exaggeration은 줌과 무관하게 고정값을 쓴다 — 그래야 건물이 지형에 대해
      // 항상 같은 자리에 있다(3D 지도의 기본 기대치). 1.3(원경 드라마틱함)과
      // 0.12(근접 스파이크 억제) 사이에서 산세는 여전히 드러나면서 스파이크 증폭은
      // 최소화되는 절충값 0.55로 고정 — 건물/도로 단위 정밀도는 어차피 지형 메시가
      // 아니라 실제 벡터 데이터(압출 높이·폭)로 표현되므로 지형이 완전히 평탄할
      // 필요는 없다.
      const TERRAIN_EXAGGERATION = 0.55;
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
      const origin = window.location.origin;
      for (const region of AOI_KEYS) {
        // 위성사진(2026-08-29, scripts/fetch_aoi_satellite.py) — pitch·zoom이 겹치면
        // 라이브 Esri 요청이 한 번에 수백 개까지 튀는 게 원인이었던 확대 랙(§DEFAULT_PITCH
        // 주석)을 이 두 AOI 안에서는 아예 없앤다. beforeId로 "labels"(지명 텍스트) 바로
        // 아래에 꽂아서 라벨이 항상 그 위에 그려지게 함 — 다른 레이어들은 addLayer
        // 기본 동작대로 현재 스택 맨 위에 쌓여도 무방(§순서 코멘트 위 참고).
        map.addSource(`${region}-satellite-src`, {
          type: "raster",
          tiles: [`${origin}/satellite/${region}/{z}/{x}/{y}.jpg`],
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
          tiles: [`${origin}/tiles/${region}-landcover/{z}/{x}/{y}.pbf`],
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
          tiles: [`${origin}/tiles/${region}-roads/{z}/{x}/{y}.pbf`],
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
          tiles: [`${origin}/tiles/${region}-buildings/{z}/{x}/{y}.pbf`],
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

      // 토사 유실 / 침수 볼륨 — bridges와 동일한 이유로 deck.gl이 아니라 MapLibre 네이티브
      // fill-extrusion을 쓴다: 지형 위에 실제로 떠서/파묻혀서 렌더링되려면(건물·도로와
      // 제대로 깊이 오클루전되려면) 이미 검증된 이 패턴이 맞다. depth를 슬라이더로 조절하면
      // 밴드(바깥 옅은색~안쪽 진한색)가 다시 계산돼 실시간으로 갱신된다.
      map.addSource("debris-flow", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "debris-flow-3d",
        type: "fill-extrusion",
        source: "debris-flow",
        paint: {
          "fill-extrusion-color": ["get", "color"],
          "fill-extrusion-height": ["get", "depth"],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.88,
        },
      });
      map.addSource("flood-water", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "flood-water-3d",
        type: "fill-extrusion",
        source: "flood-water",
        paint: {
          "fill-extrusion-color": ["get", "color"],
          "fill-extrusion-height": ["get", "depth"],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.8,
        },
      });

      simUpdateRef.current = (debrisM: number, floodM: number) => {
        const currentMap = mapRef.current;
        if (!currentMap) return;

        const debrisFeatures = debrisM > 0 ? buildFlowBands(INITIAL_CENTER, DEBRIS_CENTERLINE_M, 90, debrisM, DEBRIS_BANDS) : [];
        const floodFeatures = floodM > 0 ? buildFlowBands(INITIAL_CENTER, FLOOD_CENTERLINE_M, 130, floodM, FLOOD_BANDS) : [];

        (currentMap.getSource("debris-flow") as GeoJSONSource | undefined)?.setData({
          type: "FeatureCollection",
          features: debrisFeatures,
        } as FeatureCollection);
        (currentMap.getSource("flood-water") as GeoJSONSource | undefined)?.setData({
          type: "FeatureCollection",
          features: floodFeatures,
        } as FeatureCollection);

        // 침수 범위(가장 바깥 밴드) 안에 들어오는 렌더링된 건물 수를 세서 "몇 개 건물이
        // 잠기는지"를 텍스트로도 보여준다 — 3D 볼륨 자체가 건물을 시각적으로 덮는 게
        // 주된 증거이고, 이 카운트는 보조 지표(대략적인 수평 포함 여부 기준).
        const outer = floodFeatures[0];
        if (!outer) {
          setFloodedBuildingCount(floodM > 0 ? 0 : null);
          return;
        }
        try {
          const coords = outer.geometry.type === "Polygon" ? outer.geometry.coordinates[0] : outer.geometry.coordinates[0][0];
          const xs = coords.map((c) => currentMap.project(c as [number, number]).x);
          const ys = coords.map((c) => currentMap.project(c as [number, number]).y);
          const bbox: [[number, number], [number, number]] = [
            [Math.min(...xs), Math.min(...ys)],
            [Math.max(...xs), Math.max(...ys)],
          ];
          const rendered = currentMap.queryRenderedFeatures(bbox, { layers: ["vworld-buildings-3d", "buildings-3d-osm"] });
          let count = 0;
          const seen = new Set<string | number>();
          for (const f of rendered) {
            const key = f.id ?? JSON.stringify(f.properties);
            if (seen.has(key)) continue;
            seen.add(key);
            const c = centroid(f as unknown as Feature<Polygon | MultiPolygon>);
            if (booleanPointInPolygon(c, outer)) count++;
          }
          setFloodedBuildingCount(count);
        } catch {
          setFloodedBuildingCount(null);
        }
      };

      // 대피 경로(§6.9) — 지금은 직선거리 근사라 "실제 도로 경로 아님"이 시각적으로도
      // 드러나게 점선으로 그린다. 실경로 API가 붙으면 LineString 좌표만 실제 폴리라인으로
      // 바뀌고 이 레이어 자체는 그대로 재사용된다.
      map.addSource("evacuation-route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "evacuation-route-line",
        type: "line",
        source: "evacuation-route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#22d3ee", "line-width": 5, "line-dasharray": [2, 1.5], "line-opacity": 0.9 },
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

  // 토사/침수 깊이 슬라이더가 바뀔 때마다 3D 볼륨 재계산
  useEffect(() => {
    if (!mapReady) return;
    simUpdateRef.current?.(debrisDepth, floodDepth);
  }, [mapReady, debrisDepth, floodDepth]);

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
    const { origin, destination, label } = route;
    routeSource?.setData({
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [origin, destination] } },
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
                    onClick={() => flyTo(loc.center, loc.zoom)}
                    className="flex-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-sky-600 hover:text-sky-300"
                  >
                    {loc.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="pointer-events-auto w-64 rounded-xl border border-white/15 bg-slate-950/60 p-4 text-xs shadow-lg backdrop-blur-xl">
          <p className="font-semibold text-slate-200">토사 유실 · 침수 시뮬레이터</p>
          <p className="mt-1 text-amber-300/70">
            실제 예측값 아님 — Module A/B 실모델 연동 전 what-if 깊이 슬라이더 (§6 불확실성 표기 원칙, 산청 상능마을 기준).
          </p>

          <div className="mt-3">
            <div className="flex items-center justify-between">
              <span className="text-red-300">🟥 토사 깊이</span>
              <span className="font-mono text-slate-300">{debrisDepth.toFixed(1)}m</span>
            </div>
            <input
              type="range"
              min={0}
              max={4}
              step={0.1}
              value={debrisDepth}
              onChange={(e) => setDebrisDepth(Number(e.target.value))}
              className="mt-1 w-full accent-red-500"
            />
          </div>

          <div className="mt-3">
            <div className="flex items-center justify-between">
              <span className="text-sky-300">🟦 침수 수위</span>
              <span className="font-mono text-slate-300">{floodDepth.toFixed(1)}m</span>
            </div>
            <input
              type="range"
              min={0}
              max={5}
              step={0.1}
              value={floodDepth}
              onChange={(e) => setFloodDepth(Number(e.target.value))}
              className="mt-1 w-full accent-sky-500"
            />
          </div>

          {floodedBuildingCount !== null && (
            <p className="mt-3 rounded-md bg-sky-950/50 px-2 py-1.5 text-sky-300">
              침수 범위 안 건물 약 <span className="font-bold">{floodedBuildingCount}</span>개
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
