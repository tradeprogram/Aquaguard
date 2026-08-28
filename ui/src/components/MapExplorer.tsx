"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
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
  getVWorldRoads,
  searchAdmin,
  type AdminLevel,
  type AdminSearchResult,
} from "@/lib/api";
import { useSlowLoading } from "@/lib/useSlowLoading";

// 산청군 생비량면 — data/vector/adm_dong_5179.geojson 실측 centroid. 초기 카메라 위치일
// 뿐, 이제 이 페이지는 검색으로 어디든 이동할 수 있는 범용 3D 지도다(고정 AOI 아님).
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
// 밖으로 못 나가게 막으면 그 낭비가 원천 차단된다(제주·독도 포함 여유 있게).
const SOUTH_KOREA_BOUNDS: [[number, number], [number, number]] = [
  [124.5, 32.9],
  [131.9, 38.9],
];

// 지형(raster-dem)은 스타일 JSON에 선언하지 않고 'load' 이후 명령형으로 추가한다 — 아래 참조.
// 위성영상: V-World WMTS 위성 레이어(§2.3 1순위, api_server.py의 /vworld/imagery 프록시
// 경유 — CORS 우회는 /terrain-tiles와 동일 이유). 2026-08-28: Esri World Imagery에서
// 교체 — Esri는 산간·농촌 지역에서 "Image Not Available" 회색 타일을 자주 반환했는데,
// V-World는 국토지리정보원 소관 국내 정사영상이라 국내 커버리지가 훨씬 촘촘하다
// (z19까지 커버리지 확인됨, api_server.py 프록시 주석 참조).
const MAP_STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    satellite: {
      type: "raster",
      tiles: [`${API_BASE}/vworld/imagery/{z}/{x}/{y}.jpeg`],
      tileSize: 256,
      maxzoom: 19,
      attribution: "VWorld(국토교통부 국토지리정보원)",
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

// 건물 압출은 특정 AOI 한정이 아니라 전국(사실상 전세계) 벡터타일이라 아무 데서나
// 보인다 — 건물 밀집지로 빠르게 이동해 확인할 수 있는 테스트 지점들
const TEST_LOCATIONS: { label: string; center: [number, number]; zoom: number }[] = [
  { label: "산청 상능마을", center: INITIAL_CENTER, zoom: 12.5 },
  { label: "서울 강남", center: [127.0276, 37.4979], zoom: 16 },
  { label: "부산 해운대", center: [129.1603, 35.1587], zoom: 16 },
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
      pitch: 60,
      bearing: -20,
      // 85° 근처의 극단적인 pitch는 지형(terrain) 활성화 상태에서 카메라 투영이
      // 불안정해져 줌 중 "튕기는" 현상의 흔한 원인이라 안전한 값으로 낮춤
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
      map.addLayer({ id: "hills", type: "hillshade", source: "terrain", paint: { "hillshade-exaggeration": 0.7 } });

      // DEM 소스가 z15까지밖에 없어서(전세계 공개 SRTM 계열 지형타일의 실제 해상도
      // 한계 — 30m급이라 그 이상은 어차피 새 정보가 없다) 그보다 확대(건물 단위 줌)
      // 하면 MapLibre가 같은 타일을 억지로 늘려 써야 한다 — 이때 벌어지는 "혹처럼
      // 부풀어 보이는" 왜곡은 exaggeration이 오버줌으로 생긴 타일 경계 스파이크까지
      // 그대로 증폭해서 생긴다. 2026-08-28 재조정: 건물/도로 단위 정밀도(몇 m 물 높이
      // 차이)는 실측 지형 굴곡이 아니라 아래 debris-flow-3d/flood-water-3d/건물 압출의
      // 실제 depth 값으로 이미 표현하고 있으므로, 이 구간(z16+)에서는 지형을 과감히
      // 평탄에 가깝게 눕혀 왜곡 자체를 없애는 쪽이 "더 정밀해 보인다" — 대신 taper를
      // z17까지로 앞당기고 바닥값도 0.35→0.12로 낮춰 스파이크가 눈에 띄지 않게 한다.
      // hillshade도 같은 커브로 함께 낮춰야 한다 — 안 그러면 지형 exaggeration은
      // 죽었는데 음영기복만 남아 위성사진 위에 얼룩진 것처럼 보인다.
      const TERRAIN_TAPER_START_ZOOM = 15;
      const TERRAIN_TAPER_END_ZOOM = 17;
      const TERRAIN_MAX_EXAGGERATION = 1.3;
      const TERRAIN_MIN_EXAGGERATION = 0.12;
      const HILLSHADE_MAX_EXAGGERATION = 0.7;
      const HILLSHADE_MIN_EXAGGERATION = 0.15;
      let lastExaggeration: number | null = null;
      const syncTerrainForZoom = () => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        const zoom = currentMap.getZoom();
        const t = Math.min(
          1,
          Math.max(0, (zoom - TERRAIN_TAPER_START_ZOOM) / (TERRAIN_TAPER_END_ZOOM - TERRAIN_TAPER_START_ZOOM))
        );
        const exaggeration = TERRAIN_MAX_EXAGGERATION - t * (TERRAIN_MAX_EXAGGERATION - TERRAIN_MIN_EXAGGERATION);
        if (lastExaggeration === null || Math.abs(exaggeration - lastExaggeration) >= 0.02) {
          lastExaggeration = exaggeration;
          currentMap.setTerrain({ source: "terrain", exaggeration });
        }
        const hillshadeExaggeration =
          HILLSHADE_MAX_EXAGGERATION - t * (HILLSHADE_MAX_EXAGGERATION - HILLSHADE_MIN_EXAGGERATION);
        currentMap.setPaintProperty("hills", "hillshade-exaggeration", hillshadeExaggeration);
      };
      syncTerrainForZoom();
      map.on("zoomend", syncTerrainForZoom);

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
        const b = currentMap.getBounds();
        getVWorldRoads([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
          .then((fc) => {
            const liveMap = mapRef.current;
            if (!liveMap) return;
            (liveMap.getSource("vworld-roads") as GeoJSONSource | undefined)?.setData(fc);

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
            // 실패 시 OSM 폴백 도로 레이어를 보여주고, 교량도 OSM brunnel 태그로 대체
            const liveMap = mapRef.current;
            for (const id of ["roads-osm", "roads-casing-osm", "roads-tunnel-osm"]) {
              liveMap?.setLayoutProperty(id, "visibility", "visible");
            }
            updateBridgesFromOSM();
          });
      };

      updateBoundaries();
      updateVWorldBuildings();
      updateVWorldRoads();
      let moveendTimer: ReturnType<typeof setTimeout> | undefined;
      map.on("moveend", () => {
        clearTimeout(moveendTimer);
        moveendTimer = setTimeout(() => {
          updateBoundaries();
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
    mapRef.current?.flyTo({ center, zoom, pitch: 60, bearing: -20, duration: 2000 });
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
      { padding: 60, bearing: -20, pitch: 60, duration: 1500 }
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
      { padding: 120, pitch: 60, bearing: -20, duration: 1500 }
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
