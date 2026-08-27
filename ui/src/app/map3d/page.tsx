"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { GeoJsonLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { API_BASE, SANGCHEONG_DEMO_INPUT, getAlertGeojson, getAoi, triggerAlert } from "@/lib/api";
import type { ModuleOEnvelope } from "@/lib/types";

// 산청군 생비량면(§9 데모 AOI) 중심 — data/vector/saengbiryang_myeon_5179.geojson 실측 centroid
const AOI_CENTER: [number, number] = [128.0559, 35.3505];
const AOI_BOUNDS: [[number, number], [number, number]] = [
  [128.00826, 35.30385],
  [128.1152, 35.39634],
];

// 지형(raster-dem)은 스타일 JSON에 선언하지 않고 'load' 이후 명령형으로 추가한다 — 아래 참조.
const MAP_STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

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

  const [aoi, setAoi] = useState<GeoJSON.FeatureCollection | null>(null);
  const [alertGeojson, setAlertGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [envelope, setEnvelope] = useState<ModuleOEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sliderPct, setSliderPct] = useState(0);
  const [mapReady, setMapReady] = useState(false);

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
      maxPitch: 85,
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
      map.setTerrain({ source: "terrain", exaggeration: 1.6 });

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

  // AOI 경계는 페이지 진입 시 바로 로드
  useEffect(() => {
    getAoi("saengbiryang")
      .then(setAoi)
      .catch((e) => setError(`AOI 로드 실패: ${e instanceof Error ? e.message : String(e)}`));
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

    if (aoi) {
      layers.push(
        new GeoJsonLayer({
          id: "aoi",
          data: aoi,
          stroked: true,
          filled: false,
          getLineColor: [250, 204, 21, 220],
          lineWidthUnits: "pixels",
          getLineWidth: 2,
        })
      );
    }

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
  }, [mapReady, aoi, alertGeojson, reachedKeys, events.length]);

  const alertPackage = envelope?.data.alert_package;

  return (
    <div className="relative h-full min-h-[600px] w-full">
      <div ref={mapContainer} className="h-full w-full" />

      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between p-4">
        <div className="pointer-events-auto max-w-sm rounded-xl border border-slate-800 bg-slate-950/85 p-4 backdrop-blur">
          <h1 className="text-lg font-bold">3D 지도 — 산청군 생비량면 AOI</h1>
          <p className="mt-1 text-xs text-slate-400">
            §5 Module UI-3D — MapLibre GL(지형) + deck.gl. 노란 선은 행정동 경계 실데이터(EPSG:5179 →
            4326 재투영), 나머지 위험/경로 지오메트리는 §5 명시대로 목업 단계 placeholder입니다.
          </p>
          <button
            onClick={runDemo}
            disabled={loading}
            className="mt-3 w-full rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {loading ? "실행 중…" : "산청 시나리오 실행"}
          </button>
          {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
        </div>

        {alertPackage && (
          <div className="pointer-events-auto max-w-xs rounded-xl border border-slate-800 bg-slate-950/85 p-4 text-xs backdrop-blur">
            <p className="text-slate-400">산사태 위험확률</p>
            <p className="text-xl font-bold text-red-300">{(alertPackage.landslide.landslide_prob * 100).toFixed(0)}%</p>
            <p className="mt-2 text-slate-400">대피소 · ETA</p>
            <p className="text-sm text-emerald-300">
              {"shelter_id" in alertPackage.shelter_route ? alertPackage.shelter_route.shelter_id : "—"} ·{" "}
              {"eta_min" in alertPackage.shelter_route ? `${alertPackage.shelter_route.eta_min?.toFixed(1)}분` : "—"}
            </p>
          </div>
        )}
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
