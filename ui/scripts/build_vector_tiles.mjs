// data/precomputed/*.geojson (산청·서울 AOI 정적 데이터) 중 용량이 큰 레이어를
// 벡터 타일(.pbf, {z}/{x}/{y})로 잘라서 ui/public/tiles/{layer}/ 아래 저장한다.
// (2026-08-28) — 건물 492MB·155MB 짜리 GeoJSON을 브라우저가 통째로 내려받아
// 파싱하는 건 불가능하다. tippecanoe(표준 도구)는 Windows 네이티브 설치가
// 까다로워서 대신 geojson-vt(MapLibre가 GeoJSON 소스를 렌더링할 때 내부적으로
// 쓰는 것과 같은 라이브러리) + vt-pbf로 직접 슬라이싱한다.
// 2026-08-28 수정: 원래 여기서 gzipSync로 직접 압축하고 next.config.ts에
// Content-Encoding: gzip 헤더를 강제로 달아 브라우저가 자동으로 풀게 하는
// 방식이었는데, AOI 사각 bbox 안에서 실제 폴리곤과 안 겹쳐 애초에 안 만든
// 타일(z/x/y)을 MapLibre가 요청하면 Next가 404 HTML(gzip 아님)을 돌려주는데도
// 그 헤더 매칭 규칙이 경로만 보고 무조건 Content-Encoding: gzip을 붙여버려서
// "gzip이라매 실제로는 아니잖아" 디코딩 에러(fetch에서는 그냥 "Failed to
// fetch"로만 보임)가 터졌다 — 실측: 산청 진입 시 콘솔에 반복 스팸, 실제
// 존재하는 타일(예: sancheong-buildings z13/7008/3237)은 렌더링 자체는
// 정상이었지만 없는 타일 요청마다 매번 에러가 났다. gzip을 직접 하지 않고
// Vercel/Next가 응답 시점에 알아서 압축(Transfer-/Content-Encoding을 실제
// 상태코드에 맞게 정확히 붙임)하게 맡기면 404는 있는 그대로 404로 내려가고
// 문제가 사라진다 — 원본 대비 용량은 늘지만(gzip 없이 저장) 안정성이 우선.
import fs from "node:fs";
import path from "node:path";
import geojsonvt from "geojson-vt";
import vtpbf from "vt-pbf";

const UI_DIR = path.resolve(import.meta.dirname, "..");
const REPO_ROOT = path.resolve(UI_DIR, "..");
const SRC_DIR = path.join(REPO_ROOT, "data", "precomputed");
const OUT_DIR = path.join(UI_DIR, "public", "tiles");

// [소스 파일, 출력 레이어명, {minzoom, maxzoom}] — 건물·토지피복이 용량 문제였던
// 파일들. 하천은 이미 작아서(<4MB) 타일링 없이 그대로 GeoJSON 소스로 씀.
const JOBS = [
  { file: "sancheong_buildings.geojson", layer: "sancheong-buildings", minzoom: 10, maxzoom: 16 },
  { file: "seoul_buildings.geojson", layer: "seoul-buildings", minzoom: 10, maxzoom: 16 },
  { file: "sancheong_roads.geojson", layer: "sancheong-roads", minzoom: 9, maxzoom: 16 },
  { file: "seoul_roads.geojson", layer: "seoul-roads", minzoom: 9, maxzoom: 16 },
  { file: "sancheong_landcover.geojson", layer: "sancheong-landcover", minzoom: 8, maxzoom: 15 },
  { file: "seoul_landcover.geojson", layer: "seoul-landcover", minzoom: 8, maxzoom: 15 },
];

function lonLatToTile(lon, lat, z) {
  const n = 2 ** z;
  const x = Math.floor(((lon + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n
  );
  return [Math.max(0, Math.min(n - 1, x)), Math.max(0, Math.min(n - 1, y))];
}

function computeBbox(fc) {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  const walk = (coords) => {
    if (typeof coords[0] === "number") {
      const [lon, lat] = coords;
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    } else {
      for (const c of coords) walk(c);
    }
  };
  for (const f of fc.features) walk(f.geometry.coordinates);
  return [minLon, minLat, maxLon, maxLat];
}

function processJob({ file, layer, minzoom, maxzoom }) {
  const srcPath = path.join(SRC_DIR, file);
  if (!fs.existsSync(srcPath)) {
    console.log(`  [skip] ${file} not found`);
    return;
  }
  console.log(`[${layer}] reading ${file}...`);
  const fc = JSON.parse(fs.readFileSync(srcPath, "utf-8"));
  console.log(`[${layer}] ${fc.features.length} features, building tile index (geojson-vt)...`);

  // indexMaxZoom을 maxzoom과 같게 주면 geojson-vt가 전체 데이터를 최대 줌까지
  // "즉시(eager)" 재귀 분할해버려서 65만 피처(서울 건물)에서 힙 4GB를 넘겨
  // OOM으로 죽었다. 기본값(5)로 두면 얕은 레벨만 즉시 만들고 나머지는
  // getTile() 호출 시점에 필요한 만큼만 지연 생성해 메모리를 크게 아낀다.
  const tileIndex = geojsonvt(fc, {
    maxZoom: maxzoom,
    tolerance: 3,
    extent: 4096,
    buffer: 64,
    indexMaxPoints: 100000,
  });

  const [minLon, minLat, maxLon, maxLat] = computeBbox(fc);
  const outDir = path.join(OUT_DIR, layer);
  fs.mkdirSync(outDir, { recursive: true });

  let tileCount = 0;
  let totalBytes = 0;
  for (let z = minzoom; z <= maxzoom; z++) {
    const [minX, maxY] = lonLatToTile(minLon, minLat, z);
    const [maxX, minY] = lonLatToTile(maxLon, maxLat, z);
    for (let x = minX; x <= maxX; x++) {
      for (let y = minY; y <= maxY; y++) {
        const tile = tileIndex.getTile(z, x, y);
        if (!tile || tile.features.length === 0) continue;
        const buf = Buffer.from(vtpbf.fromGeojsonVt({ [layer]: tile }, { version: 2 }));
        const dir = path.join(outDir, String(z), String(x));
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, `${y}.pbf`), buf);
        tileCount++;
        totalBytes += buf.length;
      }
    }
    console.log(`[${layer}] z${z} done (running total: ${tileCount} tiles, ${(totalBytes / 1e6).toFixed(1)} MB)`);
  }
  console.log(`[${layer}] DONE: ${tileCount} tiles, ${(totalBytes / 1e6).toFixed(1)} MB total`);
}

for (const job of JOBS) {
  processJob(job);
}
console.log("all jobs done");
