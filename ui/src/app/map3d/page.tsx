"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { GeoJsonLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import buffer from "@turf/buffer";
import centroid from "@turf/centroid";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import { lineString as turfLineString } from "@turf/helpers";
import type { Feature, FeatureCollection, LineString, Polygon, MultiPolygon } from "geojson";
import {
  API_BASE,
  SANGCHEONG_DEMO_INPUT,
  getAlertGeojson,
  getBoundaries,
  searchAdmin,
  triggerAlert,
  type AdminLevel,
  type AdminSearchResult,
} from "@/lib/api";
import type { ModuleOEnvelope } from "@/lib/types";

// 산청군 생비량면(§9 데모 AOI) — data/vector/adm_dong_5179.geojson 실측 centroid/ADM_CD
const AOI_CENTER: [number, number] = [128.0559, 35.3505];
const AOI_BOUNDS: [[number, number], [number, number]] = [
  [128.00826, 35.30385],
  [128.1152, 35.39634],
];
const AOI_ADM_CD = "38570390";

// 지형(raster-dem)은 스타일 JSON에 선언하지 않고 'load' 이후 명령형으로 추가한다 — 아래 참조.
// 위성영상: Esri World Imagery(무료, API 키 불필요, CORS 허용 확인됨). §2.3 1순위인
// V-World API 키가 생기면 이 소스만 바꿔치기하면 된다.
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
      maxzoom: 19,
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
    // 도로 케이싱(어두운 밑깔개) — 위에 밝은 선을 얹으면 도로가 도드라져 보이는 카토그래피 기법
    {
      id: "roads-casing",
      type: "line",
      source: "osm_vectors",
      "source-layer": "transportation",
      minzoom: 11,
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      layout: { "line-cap": "round", "line-join": "round" },
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
      id: "roads",
      type: "line",
      source: "osm_vectors",
      "source-layer": "transportation",
      minzoom: 11,
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      layout: { "line-cap": "round", "line-join": "round" },
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
      id: "roads-tunnel",
      type: "line",
      source: "osm_vectors",
      "source-layer": "transportation",
      minzoom: 11,
      filter: ["==", ["get", "brunnel"], "tunnel"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#94a3b8", "line-dasharray": [2, 2], "line-width": 2, "line-opacity": 0.5 },
    },
    {
      id: "buildings-3d",
      type: "fill-extrusion",
      source: "osm_vectors",
      "source-layer": "building",
      minzoom: 13,
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

const BRIDGE_DECK_HEIGHT_M = 8;
const BRIDGE_DECK_BASE_M = 3;
const BRIDGE_HALF_WIDTH_M = { motorway: 12, trunk: 10, primary: 8, secondary: 7 } as Record<string, number>;
const DEFAULT_BRIDGE_HALF_WIDTH_M = 4;

// --- 토사 유실 / 침수 볼륨 시뮬레이터 ---
// Module A/B가 아직 목업이라 risk_polygons/inundation_extent_5179 지오메트리가 없다
// (contracts/module_a·b.example.json 참조) — 실제 예측값이 아니라 §9 데모 AOI(상능마을)
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

// 산사태 지점(§9 데모 트리거 위치)에서 남동쪽 사면 아래로 흐르는 짧고 가파른 경로
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
        poly.properties = { depth: Math.max(depthM * band.depthFactor, 0.15), color: band.color };
        out.push(poly);
      }
    } catch {
      // 극단적인 슬라이더 값(0에 가까움) 등으로 버퍼링이 실패하면 그 밴드는 건너뜀
    }
  }
  return out;
}

// 건물 압출은 AOI 한정이 아니라 전국(사실상 전세계) 벡터타일이라 아무 데서나 보인다 —
// 건물 밀집지로 빠르게 이동해 확인할 수 있는 테스트 지점들
const TEST_LOCATIONS: { label: string; center: [number, number]; zoom: number }[] = [
  { label: "산청 (AOI)", center: AOI_CENTER, zoom: 12.5 },
  { label: "서울 강남", center: [127.0276, 37.4979], zoom: 16 },
  { label: "부산 해운대", center: [129.1603, 35.1587], zoom: 16 },
];

interface TimelineEvent {
  key: string;
  label: string;
  time: number;
  who: "actual" | "agent";
}

export default function Map3DPage() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const simUpdateRef = useRef<((debrisM: number, floodM: number) => void) | null>(null);

  const [alertGeojson, setAlertGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [envelope, setEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sliderPct, setSliderPct] = useState(0);
  const [mapReady, setMapReady] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<AdminSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [debrisDepth, setDebrisDepth] = useState(0);
  const [floodDepth, setFloodDepth] = useState(0);
  const [floodedBuildingCount, setFloodedBuildingCount] = useState<number | null>(null);

  // 지도 초기화 (1회)
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    const map = new MapLibreMap({
      container: mapContainer.current,
      style: MAP_STYLE,
      center: AOI_CENTER,
      zoom: 12.5,
      pitch: 60,
      bearing: -20,
      // 85° 근처의 극단적인 pitch는 지형(terrain) 활성화 상태에서 카메라 투영이
      // 불안정해져 줌 중 "튕기는" 현상의 흔한 원인이라 안전한 값으로 낮춤
      maxPitch: 70,
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
    map.fitBounds(AOI_BOUNDS, { padding: 40, duration: 0, bearing: -20 });
    mapRef.current = map;

    // deck.gl interleaved 모드는 스타일이 완전히 로드된 뒤 overlay를 추가해야 한다 —
    // load 이전에 addControl하면 렌더 파이프라인이 깨져 스타일/타일 로딩이 멈춘다.
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
      map.setTerrain({ source: "terrain", exaggeration: 1.3 });

      // 행정경계 3계층(사용자 제공 BND_ADM_DONG_PG 기반, 시도/시군구는 그 원본을
      // dissolve해서 생성 — 전국) — 뷰포트 bbox로 api_server.py의 /boundaries에서
      // 그때그때 잘라 받는다(§4.1: 재투영은 여기 UI 출력 직전에만). 데모 AOI(생비량면)만
      // 노란색으로 강조, 나머지는 계층별 굵기를 달리한 하늘색 경계선.
      const ADM_LAYER_STYLE: Record<AdminLevel, { color: string; width: number; opacity: number }> = {
        sido: { color: "#0ea5e9", width: 2.5, opacity: 0.6 },
        sigungu: { color: "#38bdf8", width: 1.5, opacity: 0.55 },
        dong: { color: "#38bdf8", width: 1, opacity: 0.45 },
      };
      for (const level of ["sido", "sigungu", "dong"] as AdminLevel[]) {
        const style = ADM_LAYER_STYLE[level];
        map.addSource(`adm-${level}`, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({
          id: `adm-${level}-line`,
          type: "line",
          source: `adm-${level}`,
          paint: {
            "line-color": ["case", ["==", ["get", "code"], AOI_ADM_CD], "#facc15", style.color],
            "line-width": ["case", ["==", ["get", "code"], AOI_ADM_CD], 3, style.width],
            "line-opacity": ["case", ["==", ["get", "code"], AOI_ADM_CD], 0.9, style.opacity],
          },
        });
      }

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
      updateBoundaries();
      let moveendTimer: ReturnType<typeof setTimeout> | undefined;
      map.on("moveend", () => {
        clearTimeout(moveendTimer);
        moveendTimer = setTimeout(updateBoundaries, 200);
      });

      // 교량(brunnel=='bridge')은 MapLibre line 레이어로는 지형 위에 그대로 드레이프될
      // 뿐이라 실제로 "떠 있는" 느낌이 안 난다 — LineString을 폭만큼 버퍼링해 얇은
      // 폴리곤으로 만들고 fill-extrusion으로 지면에서 띄워 올려 진짜 입체 교량 데크를 만든다.
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

      const seenBridgeIds = new Set<string | number>();
      const bridgeFeatures: Feature<Polygon | MultiPolygon>[] = [];
      const updateBridges = () => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        const raw = currentMap.querySourceFeatures("osm_vectors", {
          sourceLayer: "transportation",
          filter: ["==", ["get", "brunnel"], "bridge"],
        }) as unknown as Feature<LineString>[];

        for (const feat of raw) {
          const key = feat.id ?? JSON.stringify(feat.geometry.coordinates);
          if (seenBridgeIds.has(key)) continue;
          seenBridgeIds.add(key);
          const roadClass = (feat.properties?.class as string) ?? "";
          const halfWidth = BRIDGE_HALF_WIDTH_M[roadClass] ?? DEFAULT_BRIDGE_HALF_WIDTH_M;
          try {
            const poly = buffer(feat, halfWidth, { units: "meters", steps: 4 });
            if (poly) bridgeFeatures.push(poly);
          } catch {
            // 극단적으로 짧거나 기형인 geometry는 버퍼링이 실패할 수 있음 — 건너뜀
          }
        }

        const source = currentMap.getSource("bridges") as GeoJSONSource | undefined;
        source?.setData({
          type: "FeatureCollection",
          features: bridgeFeatures,
        } as FeatureCollection);
      };

      let idleTimer: ReturnType<typeof setTimeout> | undefined;
      map.on("idle", () => {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(updateBridges, 150);
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

        const debrisFeatures = debrisM > 0 ? buildFlowBands(AOI_CENTER, DEBRIS_CENTERLINE_M, 90, debrisM, DEBRIS_BANDS) : [];
        const floodFeatures = floodM > 0 ? buildFlowBands(AOI_CENTER, FLOOD_CENTERLINE_M, 130, floodM, FLOOD_BANDS) : [];

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
          const rendered = currentMap.queryRenderedFeatures(bbox, { layers: ["buildings-3d"] });
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

      // interleaved:true는 deck.gl이 지형 depth와 맞물려 렌더링하도록 map.transform의
      // 내부 지형 API를 직접 읽는데, maplibre-gl v6(§AGENTS.md가 경고하는 대로 이전
      // 버전과 API가 다름)에서 deck.gl 9.3이 기대하는 형태와 어긋나 "Cannot read
      // properties of undefined (reading 'elevation')"로 죽는다. 우리 레이어(선/점)는
      // 지형에 깊이 오클루전될 필요가 없으니 기본(오버레이) 모드로 충분하다.
      const overlay = new MapboxOverlay({ layers: [] });
      map.addControl(overlay);
      overlayRef.current = overlay;
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
      overlayRef.current = null;
    };
  }, []);


  const flyTo = useCallback((center: [number, number], zoom: number) => {
    mapRef.current?.flyTo({ center, zoom, pitch: 60, bearing: -20, duration: 2000 });
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
    const id = setTimeout(() => {
      searchAdmin(q)
        .then(setSearchResults)
        .catch(() => setSearchResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(id);
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
    setSearchQuery("");
    setSearchResults([]);
  }, []);

  const runDemo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const env = await triggerAlert(SANGCHEONG_DEMO_INPUT);
      setEnvelope(env);
      const gj = await getAlertGeojson(SANGCHEONG_DEMO_INPUT.alert_id);
      setAlertGeojson(gj);
      setSliderPct(0);
    } catch (e) {
      setError(
        `백엔드 연결 실패 — api_server.py가 떠 있는지 확인하세요. (${e instanceof Error ? e.message : String(e)})`
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const events: TimelineEvent[] = useMemo(() => {
    const d = envelope?.data;
    if (!d) return [];
    const toMs = (iso?: string) => (iso ? new Date(iso).getTime() : NaN);
    return [
      { key: "advisory", label: "산림청 대피 권고", time: toMs(d.timeline_actual.advisory), who: "actual" as const },
      { key: "report_start", label: "주민 신고 시작", time: toMs(d.timeline_actual.report_start), who: "actual" as const },
      { key: "detected", label: "에이전트 탐지 (Module A)", time: toMs(d.timeline_agent.detected), who: "agent" as const },
      { key: "alert_sent", label: "에이전트 경보 발송", time: toMs(d.timeline_agent.alert_sent), who: "agent" as const },
      { key: "warning_escalated", label: "관 경보 격상 (실제)", time: toMs(d.timeline_actual.warning_escalated), who: "actual" as const },
    ].filter((e) => !Number.isNaN(e.time));
  }, [envelope]);

  const currentTime = useMemo(() => {
    if (events.length === 0) return null;
    const min = events[0].time;
    const max = events[events.length - 1].time;
    return min + ((max - min) * sliderPct) / 100;
  }, [events, sliderPct]);

  const reachedKeys = useMemo(
    () => new Set(events.filter((e) => currentTime !== null && currentTime >= e.time).map((e) => e.key)),
    [events, currentTime]
  );

  // deck.gl 레이어 재구성 — 슬라이더 시각에 도달한 이벤트에 따라 레이어를 단계적으로 노출
  useEffect(() => {
    if (!mapReady || !overlayRef.current) return;

    const layers = [];

    if (alertGeojson) {
      const showRisk = events.length === 0 || reachedKeys.has("detected");
      const showRoute = events.length === 0 || reachedKeys.has("alert_sent");

      const filtered = {
        type: "FeatureCollection" as const,
        features: alertGeojson.features.filter((f) => {
          const kind = f.properties?.kind;
          if (kind === "risk_buffer_placeholder" || kind === "landslide_point") return showRisk;
          if (kind === "route_placeholder" || kind === "shelter_point") return showRoute;
          return true;
        }),
      };

      layers.push(
        new GeoJsonLayer({
          id: "alert-features",
          data: filtered,
          pointType: "circle",
          stroked: true,
          filled: true,
          extruded: false,
          getFillColor: (f: GeoJSON.Feature) => {
            const kind = f.properties?.kind;
            if (kind === "landslide_point") return [239, 68, 68, 230];
            if (kind === "risk_buffer_placeholder") return [239, 68, 68, 60];
            if (kind === "shelter_point") return [52, 211, 153, 230];
            return [56, 189, 248, 200];
          },
          getLineColor: (f: GeoJSON.Feature) => {
            const kind = f.properties?.kind;
            if (kind === "route_placeholder") return [56, 189, 248, 220];
            return [255, 255, 255, 180];
          },
          getLineWidth: (f: GeoJSON.Feature) => (f.properties?.kind === "route_placeholder" ? 3 : 1.5),
          lineWidthUnits: "pixels",
          getPointRadius: (f: GeoJSON.Feature) => (f.properties?.kind === "landslide_point" ? 10 : 8),
          pointRadiusUnits: "pixels",
          pickable: true,
        })
      );
    }

    overlayRef.current.setProps({ layers });
  }, [mapReady, alertGeojson, reachedKeys, events.length]);

  // 토사/침수 깊이 슬라이더가 바뀔 때마다 3D 볼륨 재계산
  useEffect(() => {
    if (!mapReady) return;
    simUpdateRef.current?.(debrisDepth, floodDepth);
  }, [mapReady, debrisDepth, floodDepth]);

  const alertPackage = envelope?.data.alert_package;

  return (
    <div className="relative h-full min-h-[600px] w-full">
      <div ref={mapContainer} className="h-full w-full" />

      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between p-4">
        <div className="pointer-events-auto max-w-sm rounded-xl border border-slate-800 bg-slate-950/85 p-4 backdrop-blur">
          <h1 className="text-lg font-bold">3D 지도 — 산청군 생비량면 AOI</h1>

          <div className="relative mt-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="시/군/구/읍/면/동 검색 (예: 생비량면, 강남동)"
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-sky-600 focus:outline-none"
            />
            {searching && <span className="absolute right-2 top-1.5 text-xs text-slate-500">검색 중…</span>}
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

          <p className="mt-2 text-xs text-slate-400">
            §5 Module UI-3D — MapLibre GL(지형) + deck.gl. 행정경계 시도/시군구/읍면동 3계층
            (사용자 제공 데이터, 전국)을 뷰포트 기준으로 실시간 표시 — 노란 선이 데모 AOI(생비량면),
            나머지는 계층별 굵기로 구분. 위험/경로 지오메트리는 §5 명시대로 목업 단계 placeholder입니다.
          </p>
          <p className="mt-2 text-xs text-slate-500">
            🖱 좌클릭 드래그: 이동 · 스크롤: 줌 · <span className="text-slate-300">우클릭(또는 Ctrl) 드래그: 회전/기울기</span>
          </p>
          <p className="mt-2 text-xs text-amber-300/70">
            건물(실제 높이 압출)·도로망·교량(지면에서 띄운 데크)까지 전국 OSM 데이터로 입체화됨.
            산청 AOI는 산간마을이라 매핑이 드문드문 있음 — 프로덕션 전환 시 §2.6 건축물대장/도로망
            표준노드링크로 교체 예정.
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
          <button
            onClick={runDemo}
            disabled={loading}
            className="mt-3 w-full rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {loading ? "실행 중…" : "산청 시나리오 실행"}
          </button>
          {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
        </div>

        <div className="pointer-events-auto flex flex-col gap-3">
          {alertPackage && (
            <div className="max-w-xs rounded-xl border border-slate-800 bg-slate-950/85 p-4 text-xs backdrop-blur">
              <p className="text-slate-400">산사태 위험확률</p>
              <p className="text-xl font-bold text-red-300">{(alertPackage.landslide.landslide_prob * 100).toFixed(0)}%</p>
              <p className="mt-2 text-slate-400">대피소 · ETA</p>
              <p className="text-sm text-emerald-300">
                {"shelter_id" in alertPackage.shelter_route ? alertPackage.shelter_route.shelter_id : "—"} ·{" "}
                {"eta_min" in alertPackage.shelter_route ? `${alertPackage.shelter_route.eta_min?.toFixed(1)}분` : "—"}
              </p>
            </div>
          )}

          <div className="w-64 rounded-xl border border-slate-800 bg-slate-950/85 p-4 text-xs backdrop-blur">
            <p className="font-semibold text-slate-200">토사 유실 · 침수 시뮬레이터</p>
            <p className="mt-1 text-amber-300/70">
              실제 예측값 아님 — Module A/B 실모델 연동 전 what-if 깊이 슬라이더 (§6 불확실성 표기 원칙).
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
                {floodedBuildingCount === 0 && " (범위 안에 매핑된 OSM 건물 없음 — 산간 AOI 특성)"}
              </p>
            )}
          </div>
        </div>
      </div>

      {events.length > 0 && (
        <div className="pointer-events-auto absolute inset-x-0 bottom-0 border-t border-slate-800 bg-slate-950/90 p-4 backdrop-blur">
          <div className="mx-auto max-w-3xl">
            <div className="mb-2 flex justify-between text-xs text-slate-400">
              {events.map((e) => (
                <span key={e.key} className={reachedKeys.has(e.key) ? (e.who === "agent" ? "text-sky-300" : "text-amber-300") : ""}>
                  {new Date(e.time).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })} {e.label}
                </span>
              ))}
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={sliderPct}
              onChange={(e) => setSliderPct(Number(e.target.value))}
              className="w-full accent-sky-500"
            />
            <p className="mt-1 text-center text-xs text-slate-500">
              시간 슬라이더 — 끌어서 재연: 에이전트(파란색)가 관의 실제 경보(주황색)보다 먼저 도달하는 걸 확인하세요
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
