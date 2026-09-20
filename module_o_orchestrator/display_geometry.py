"""표시용 기하 — 화면에 그릴 때만 쓰는, 부드럽게 다듬은 폴리곤.

**계산에는 절대 쓰지 않는다.** 노출자산·고립 판정·피해액은 모듈이 낸 원본 기하를
그대로 쓰고, 여기서 만든 것은 지도에만 올라간다. 두 개가 갈라져 있는 이유는 분명하다 —
래스터를 폴리곤화하면 격자 한 칸이 그대로 계단이 되는데, 그 계단은 지형 정보가 아니라
격자 해상도의 흔적이다. 확대할수록 커지기만 하고 아무것도 더 알려주지 않는다.
(사용자 표현: "마인크래프트 같다", "확대하면 깨지는 형상이 계속된다", 2026-09-20)

그래서 표시용으로는 두 가지를 한다.

1. **깊이장을 먼저 보간한다** — 50m 격자를 12.5m로 쌍선형 업샘플한 뒤 구간을 나눈다.
   구간 경계가 격자 모서리가 아니라 실제 등수심선을 따라가게 된다. 침수심은 연속량이므로
   이 보간은 값을 지어내는 게 아니라 원래 연속면을 되살리는 쪽이다.
2. **바깥 범위는 원본으로 자른다** — 보간만 하면 젖은 셀과 마른 셀 사이를 이어서
   침수 범위가 13.7% 넓어진다. 안쪽 등수심선을 매끄럽게 하려던 것이 바깥 범위까지
   바꾸면 그건 다른 예측이므로, 원본 발자국을 최근접 업샘플해 거기로 자른다.
3. **모서리를 깎는다** — Chaikin corner-cutting. 남은 12.5m 계단이 곡선이 된다.

**정직성 한계**: 원본은 여전히 50m SFINCS 산출이다. 부드럽게 보인다고 해상도가 올라간
게 아니다. 산청 데모 실측(2026-09-20): 침수 범위 931.1ha로 원본 933.2ha 대비 **−0.2%**,
**IoU 0.929**. 차이는 전부 경계에서 모서리가 깎이고 채워진 것(빠짐 35.1ha / 생김 33.0ha)
으로 원본 셀 한 변(50m) 안쪽이다. 이 수치는 snapshot 메타에 실어 화면이 근거를 댄다.
"""
from __future__ import annotations

from typing import Any, Iterable

# 업샘플 배율. 50m → 12.5m. 더 올리면 자잘한 조각이 급증하고(4배에서 987개, 8배면
# 그 두 배) 얻는 매끄러움은 거의 없었다(2026-09-20 실측).
UPSAMPLE = 4
# 이보다 작은 조각은 버린다. 12.5m 셀 6~7개 크기로, 이 밑은 보간이 만든 티끌이다.
MIN_PART_AREA_M2 = 1000.0
# Chaikin 반복. 3회면 계단이 사라지고 꼭짓점은 8배가 된다 — 그 이상은 차이가 안 보인다.
CHAIKIN_ITERATIONS = 3
# 스무딩 뒤 단순화 허용오차(m). 꼭짓점 수를 줄이되 눈에는 차이가 없는 범위.
SIMPLIFY_TOLERANCE_M = 2.0

# 침수심 구간. 예전에는 4단(0.3/1/2/5)이라 이 지역 침수심 중앙값이 5.7m·최대 15.5m인
# 탓에 대부분이 맨 위 한 칸에 몰려 단색 덩어리로 보였다. 10단으로 늘려 색이 이어지게 한다.
DISPLAY_DEPTH_BANDS_M: tuple[float, ...] = (
    0.3, 0.6, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 14.0,
)


def chaikin(ring: list[tuple[float, float]], iterations: int = CHAIKIN_ITERATIONS
            ) -> list[tuple[float, float]]:
    """닫힌 고리의 모서리를 반복해서 깎는다(Chaikin corner-cutting).

    한 번 돌 때마다 각 변을 1:3, 3:1 지점에서 잘라 꼭짓점이 두 배가 되고 각이 둥글어진다.
    새 점은 항상 원래 변 위에 있으므로 도형이 원본 볼록껍질 밖으로 나가지 않는다 —
    볼록한 모서리는 깎이고 오목한 곳은 채워져서 면적 변화가 서로 상쇄된다(실측 −0.2%).
    """
    points = list(ring)
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    for _ in range(max(0, iterations)):
        if len(points) < 4:
            break
        cut: list[tuple[float, float]] = []
        for i, p in enumerate(points):
            q = points[(i + 1) % len(points)]
            cut.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
            cut.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
        points = cut
    return points + [points[0]] if points else []


def smooth_geometry(geometry: dict[str, Any] | None,
                    iterations: int = CHAIKIN_ITERATIONS,
                    simplify_m: float = SIMPLIFY_TOLERANCE_M) -> dict[str, Any] | None:
    """Polygon/MultiPolygon의 모든 고리를 다듬어 돌려준다. 다른 타입은 그대로.

    구멍(내부 고리)도 같이 깎는다 — 바깥만 다듬으면 구멍만 각져서 더 어색해진다.
    """
    if not isinstance(geometry, dict):
        return geometry
    kind = geometry.get("type")
    if kind not in ("Polygon", "MultiPolygon"):
        return geometry

    from shapely.geometry import MultiPolygon, Polygon, shape
    from shapely.geometry import mapping

    parts = geometry["coordinates"] if kind == "MultiPolygon" else [geometry["coordinates"]]
    smoothed = []
    for part in parts:
        if not part:
            continue
        rings = [chaikin(list(r), iterations) for r in part]
        rings = [r for r in rings if len(r) >= 4]
        if not rings:
            continue
        try:
            poly = Polygon(rings[0], rings[1:])
            if simplify_m > 0:
                poly = poly.simplify(simplify_m, preserve_topology=True)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                smoothed.append(poly)
        except Exception:  # noqa: BLE001 - 한 조각이 이상해도 나머지는 그린다
            continue
    if not smoothed:
        return geometry  # 전부 실패하면 원본을 그대로 — 안 그리는 것보다 낫다

    merged = smoothed[0] if len(smoothed) == 1 else MultiPolygon(
        [g for p in smoothed for g in (p.geoms if p.geom_type == "MultiPolygon" else [p])]
    )
    return mapping(merged)


def smooth_featurecollection(collection: dict[str, Any] | None) -> dict[str, Any]:
    """FeatureCollection의 모든 feature 기하를 다듬는다. 속성은 그대로 둔다."""
    if not isinstance(collection, dict):
        return {"type": "FeatureCollection", "features": []}
    out = []
    for feature in collection.get("features") or []:
        if not isinstance(feature, dict):
            continue
        out.append({**feature, "geometry": smooth_geometry(feature.get("geometry"))})
    return {**collection, "features": out}


def flood_display_featurecollection(depth_path: str,
                                    thr: float = 0.3,
                                    bands: Iterable[float] | None = None,
                                    upsample: int = UPSAMPLE,
                                    min_part_area_m2: float = MIN_PART_AREA_M2
                                    ) -> dict[str, Any]:
    """최대침수심 래스터 → **표시용** 침수 폴리곤(EPSG:5179).

    module_b_flood.fim.raster_to_featurecollection과 달리 격자를 먼저 보간하고 모서리를
    깎는다. 계산에는 fim 쪽 원본을 쓰고 이건 지도에만 올린다 — 둘을 바꿔 쓰면 노출자산·
    고립 판정이 IoU 0.929짜리 다른 도형으로 계산된다.

    properties는 fim 쪽과 같은 이름을 쓴다(depth_min_m/depth_max_m/depth_p90_m/band).
    UI가 어느 쪽을 받든 같은 코드로 그릴 수 있어야 하기 때문이다.
    """
    import numpy as np
    import rasterio
    from rasterio.features import shapes
    from rasterio.transform import Affine
    from shapely.geometry import mapping, shape

    edges = tuple(bands) if bands is not None else DISPLAY_DEPTH_BANDS_M
    edges = tuple(e for e in edges if e >= thr) or (thr,)

    with rasterio.open(depth_path) as ds:
        depth = ds.read(1).astype("float32")
        transform = ds.transform

    finite = np.isfinite(depth)
    observed_max = float(depth[finite].max()) if finite.any() else thr
    # 결측은 0(침수 없음)으로 둔다 — 보간할 때 NaN이 섞이면 주변까지 NaN이 번진다.
    depth = np.where(finite, depth, 0.0)

    # 원본 격자에서의 침수 발자국. 아래에서 보간 결과를 여기로 잘라낸다.
    footprint = depth >= thr

    if upsample and upsample > 1:
        from scipy.ndimage import zoom
        depth = zoom(depth, upsample, order=1)  # order=1 = 쌍선형
        # 발자국은 최근접(order=0)으로 올린다 — 셀 하나가 그대로 셀 n개가 되므로
        # 원본 범위가 한 뼘도 안 늘어난다.
        footprint = zoom(footprint.astype("uint8"), upsample, order=0).astype(bool)
        transform = Affine(transform.a / upsample, transform.b, transform.c,
                           transform.d, transform.e / upsample, transform.f)

    # 구간은 "그 구간만"이 아니라 **누적**(depth >= lo)으로 만들고, 화면에서는 얕은
    # 것부터 깊은 것 순으로 겹쳐 그린다(깊은 쪽이 위를 덮는다).
    #
    # 배타 구간으로 잘라 두면 이웃한 둘이 경계선을 공유하는데, 각자 안쪽으로 깎이면서
    # 그 사이에 틈이 벌어진다 — 색 띠 사이로 지형이 비친다. 누적끼리 차집합을 내서
    # 배타로 되돌리는 방법도 써 봤지만(틈은 없어진다) 가느다란 띠가 잔뜩 생겨
    # 폴리곤이 87개에서 3,120개로, 전송량이 1.4MB에서 3.4MB로 늘었다. 평면으로 그리는
    # 한 겹침은 문제가 되지 않으므로(위가 아래를 덮는다) 누적 그대로 둔다.
    from shapely.ops import unary_union

    cumulative: list[Any] = []
    for lo in edges:
        mask = ((depth >= lo) & footprint).astype("uint8")
        parts = []
        if mask.any():
            for geom, value in shapes(mask, mask=mask > 0, transform=transform):
                if value != 1:
                    continue
                poly = shape(geom)
                if poly.area < min_part_area_m2:
                    continue  # 보간이 만든 티끌
                smoothed = smooth_geometry(mapping(poly))
                if smoothed is not None:
                    parts.append(shape(smoothed))
        cumulative.append(unary_union(parts) if parts else None)

    features: list[dict[str, Any]] = []
    for i, lo in enumerate(edges):
        current = cumulative[i]
        if current is None or current.is_empty:
            continue
        hi = edges[i + 1] if i + 1 < len(edges) else float("inf")
        values = depth[((depth >= lo) & (depth < hi) & footprint)]
        props = {
            "flooded": 1,
            "depth_thr_m": thr,
            "depth_min_m": round(lo, 2),
            "depth_max_m": round(min(hi, observed_max), 2),
            "depth_p90_m": round(float(np.percentile(values, 90)), 2) if values.size else round(lo, 2),
            "band": i,
            "band_count": len(edges),
            # 누적이다 — 이 폴리곤은 "깊이 lo 이상인 곳 전부"이지 "lo~hi 구간만"이 아니다.
            # 화면은 band 오름차순으로 겹쳐 그려야 색이 맞는다.
            "cumulative": True,
        }
        geoms = current.geoms if current.geom_type == "MultiPolygon" else [current]
        for part in geoms:
            if part.is_empty:
                continue
            features.append({"type": "Feature", "geometry": mapping(part),
                             "properties": dict(props)})

    return {
        "type": "FeatureCollection",
        "features": features,
        "crs": {"type": "name", "properties": {"name": "EPSG:5179"}},
    }


# --- 시간축 침수 ---------------------------------------------------------
#
# SFINCS 산출물은 "최대" 침수심 래스터 한 장이라 시각별 침수가 없다. 그런데 같은
# 모의가 경호교 지점의 **시간별 수위**도 남겼다(module_b_flood/data/sfincs_reach_wse.csv,
# 2025-07-18 02:00 ~ 07-20 12:00 매시). 이걸로 시각별 침수를 준정적(bathtub)으로 만든다.
#
#     깊이(t) = 최대깊이 − (첨두수위 − 수위(t))        음수는 0
#
# 여기서 핵심은 **기하를 시각마다 다시 만들 필요가 없다**는 것이다.
#
#     깊이(t) ≥ b   ⟺   최대깊이 ≥ b + 수위강하(t)
#
# 즉 어느 시각의 어느 수심 등고선도 전부 "최대깊이 래스터의 등고선"이다. 그래서
# 등고선을 촘촘히 한 벌만 만들어 두고, 화면이 시각마다 수위강하만큼 골라내고
# 색만 다시 매기면 된다. 39프레임치 폴리곤을 보내지 않아도 된다.
#
# **정직성**: 이건 SFINCS를 시각마다 다시 돌린 게 아니다. 수면이 한 덩어리로
# 오르내린다고 가정한 준정적 근사이고, 실제 홍수파는 구간을 따라 경사를 갖는다.
# 다만 그 수위 곡선은 같은 SFINCS 모의가 낸 값이라 엔진을 섞지는 않았다.
# 화면은 이 구분을 MODEL/ASSUMPTION 배지로 표기해야 한다.

# 경호교 하상고(EPSG:5179, reach_hydrograph_meta.json의 gdt). 수심 = WSE − 이 값.
GYEONGHO_BED_M = 85.446

# 등고선 레벨(m). 0.3(침수 판정 하한)부터 래스터 최댓값까지 0.5m 간격.
# 시각별 수위강하가 0.65~4.8m이고 표시 구간이 0.3~14m이므로 그 합만큼 필요하다.
CONTOUR_STEP_M = 0.5


def reach_stage_series(csv_path: str, bed_m: float = GYEONGHO_BED_M) -> dict[str, float]:
    """시각 -> 하천 수심(m). 값이 빈 행은 건너뛴다.

    CSV는 UTF-8 BOM으로 저장돼 있어 utf-8-sig로 읽지 않으면 첫 열 이름이 깨진다.
    """
    import csv

    series: dict[str, float] = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw = (row.get("WSE_sim") or "").strip()
            if not raw:
                continue
            try:
                series[row["dt"].strip()] = float(raw) - bed_m
            except ValueError:
                continue
    return series


def flood_contours(depth_path: str, thr: float = 0.3,
                   step_m: float = CONTOUR_STEP_M,
                   upsample: int = UPSAMPLE,
                   min_part_area_m2: float = MIN_PART_AREA_M2) -> dict[str, Any]:
    """최대침수심 래스터의 누적 등고선 한 벌(EPSG:5179).

    feature마다 properties.level_m = 그 등고선의 최대침수심 기준값. 화면은 시각 t에서
    level_m >= 수위강하(t) + thr 인 것만 골라 그리고, 색은 level_m − 수위강하(t)로
    칠한다 — 그게 그 시각의 실제 침수심이다.

    flood_display_featurecollection과 같은 다듬기를 쓴다(보간 → 발자국으로 클립 →
    Chaikin). 누적이라 깊은 등고선이 얕은 등고선 안에 포개진다.
    """
    import numpy as np
    import rasterio
    from rasterio.features import shapes
    from rasterio.transform import Affine
    from shapely.geometry import mapping, shape

    with rasterio.open(depth_path) as ds:
        depth = ds.read(1).astype("float32")
        transform = ds.transform

    finite = np.isfinite(depth)
    observed_max = float(depth[finite].max()) if finite.any() else thr
    depth = np.where(finite, depth, 0.0)
    footprint = depth >= thr

    if upsample and upsample > 1:
        from scipy.ndimage import zoom
        depth = zoom(depth, upsample, order=1)
        footprint = zoom(footprint.astype("uint8"), upsample, order=0).astype(bool)
        transform = Affine(transform.a / upsample, transform.b, transform.c,
                           transform.d, transform.e / upsample, transform.f)

    levels = [thr]
    level = step_m * (int(thr / step_m) + 1)
    while level <= observed_max:
        levels.append(round(level, 2))
        level += step_m

    features: list[dict[str, Any]] = []
    for lo in levels:
        mask = ((depth >= lo) & footprint).astype("uint8")
        if not mask.any():
            continue
        for geom, value in shapes(mask, mask=mask > 0, transform=transform):
            if value != 1:
                continue
            poly = shape(geom)
            if poly.area < min_part_area_m2:
                continue
            smoothed = smooth_geometry(mapping(poly))
            if smoothed is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": smoothed,
                "properties": {
                    "kind": "inundation",
                    "level_m": round(lo, 2),
                    "cumulative": True,
                    # 5179는 미터 좌표계라 넓이가 곧 m². 화면이 "지금 몇 ha 잠겼나"를
                    # 쓰려면 필요하다 — 4326으로 재투영된 뒤에는 도(°) 넓이가 돼서
                    # 브라우저가 다시 계산할 수 없다.
                    "area_m2": round(shape(smoothed).area, 1),
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
        "crs": {"type": "name", "properties": {"name": "EPSG:5179"}},
        "levels": levels,
        "observed_max_m": round(observed_max, 2),
    }
