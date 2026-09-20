"""데모 시나리오를 한 번 계산해서 통째로 저장한다.

**왜**: 산청 데모는 입력이 고정돼 있다(contracts/module_o.example.json). 같은 입력에
같은 결과가 나오는데도 버튼을 누를 때마다 전 모듈을 다시 돌리고, 노출자산 GeoJSON을
다시 읽고, 침수 래스터를 다시 폴리곤화했다. 배포 서버(2코어·RAM 908MB)에서 이게
수십 초가 걸려 시연 중에 멈춘 것처럼 보였다. 값이 바뀌지 않는 계산을 실시간으로
할 이유가 없다.

**무엇이 저장되나**: 경보 봉투(모듈 A~H 출력 전부), 지도용 GeoJSON, 시간축. 전부
실제 파이프라인이 낸 값이며 손으로 고친 값은 하나도 없다 — 이 스크립트는 `run()`을
부르고 그 결과를 받아 적기만 한다.

**정직성 장치**: 저장본에 입력 해시와 코드 커밋을 같이 적고,
`tests/test_demo_snapshot.py`가 파이프라인을 다시 돌려 저장본과 대조한다. 모듈이
바뀌면 그 테스트가 깨지면서 "다시 만들라"고 알려준다. 그래서 저장본은 언제나
**지금 코드가 내는 값**이지, 어느 시점에 잘 나왔던 값이 아니다.

실행:
    python scripts/build_demo_snapshot.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# .env를 읽어야 Module E가 네이버 Directions를 실제로 부른다.
#
# 이게 빠져 있어서 키를 .env에 넣어도 스냅샷은 **직선거리 근사**를 구운 채로 나왔다.
# 저장본은 한 번 구우면 화면이 계속 그걸 쓰므로, 여기서 키를 못 읽으면 실도로 경로가
# 영영 안 들어간다 — api_server.py는 load_dotenv()를 부르는데 이 스크립트만 빠져 있었다.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from module_o_orchestrator.snapshot import SNAPSHOT_PATH, input_fingerprint  # noqa: E402

DEMO_INPUT_PATH = REPO_ROOT / "contracts" / "module_o.example.json"


def demo_input() -> dict:
    with open(DEMO_INPUT_PATH, encoding="utf-8") as f:
        return json.load(f)["input"]


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"],
                             cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build(verbose: bool = True) -> dict:
    # 저장본은 **실모듈** 결과여야 한다. 목업 모드(기본값)로 만들면 contracts의 예시
    # 출력이 그대로 저장되고, 화면은 모형이 낸 적 없는 숫자를 실측인 양 보여준다.
    # 배포 서버도 AQUAGUARD_MOCK_MODE=0으로 돈다(/health의 mock_mode: false).
    os.environ["AQUAGUARD_MOCK_MODE"] = "0"

    from module_o_orchestrator import display_geometry, geo
    from module_o_orchestrator.exposure_layers import flood_depth_raster, resolve_aoi
    from module_o_orchestrator.orchestrator import run as run_orchestrator

    payload = demo_input()

    if not (os.environ.get("NAVER_CLIENT_ID") and os.environ.get("NAVER_CLIENT_SECRET")):
        print("  [경고] NAVER_CLIENT_ID/SECRET이 없습니다 — 대피 경로가 직선거리 근사로 "
              "구워집니다. .env에 키를 넣고 다시 만드십시오.")

    # 시간축 프레임(트랙①의 사전계산 강우 시계열) — 침수 수위를 여기에 맞춰 붙인다.
    frames = []
    try:
        from module_a_landslide import risk_layers
        index_path = (Path(risk_layers.__file__).resolve().parent
                      / "data" / "risk_polygons" / "risk_landslide_index.json")
        if index_path.exists():
            with open(index_path, encoding="utf-8") as f:
                frames = json.load(f).get("frames") or []
    except ImportError:
        pass

    t0 = time.perf_counter()
    envelope = run_orchestrator(payload)
    pipeline_s = time.perf_counter() - t0
    if verbose:
        print(f"  파이프라인 {pipeline_s:.1f}s  status={envelope.get('status')}")

    # 표시용 침수 — 계산에 쓰인 것과 별개다(display_geometry 참고).
    location = payload.get("trigger_location") or {}
    aoi = resolve_aoi(location.get("x_5179"), location.get("y_5179"))
    raster_path, raster_warning = flood_depth_raster(aoi)

    flood_display = {"type": "FeatureCollection", "features": []}
    flood_stats: dict = {"available": False, "reason": raster_warning}
    if raster_path:
        t0 = time.perf_counter()
        fc_5179 = display_geometry.flood_display_featurecollection(raster_path)
        flood_display = {
            "type": "FeatureCollection",
            "features": [
                {**f, "properties": {**f["properties"], "kind": "inundation"}}
                for f in geo.featurecollection_5179_to_lonlat(fc_5179)
            ],
        }
        flood_stats = {
            "available": True,
            "source_raster": Path(raster_path).name,
            "source_resolution_m": 50,
            "display_resolution_m": 50 / display_geometry.UPSAMPLE,
            "bands": list(display_geometry.DISPLAY_DEPTH_BANDS_M),
            "cumulative": True,
            "polygons": len(flood_display["features"]),
            "build_seconds": round(time.perf_counter() - t0, 2),
        }
        if verbose:
            print(f"  표시용 침수 {flood_stats['polygons']}개 폴리곤 "
                  f"{flood_stats['build_seconds']}s")

    # 시간축 침수 — 등고선 한 벌 + 시각별 수위강하.
    #
    # SFINCS는 "최대" 침수심 한 장만 내지만 같은 모의가 경호교 시간별 수위도 남겼다.
    # 깊이(t) ≥ b ⟺ 최대깊이 ≥ b + 수위강하(t) 이므로, 등고선을 한 벌만 보내 두면
    # 화면이 시각마다 골라 쓰고 색만 다시 매길 수 있다(display_geometry 참고).
    flood_series: dict = {"available": False}
    if raster_path:
        t0 = time.perf_counter()
        contours_5179 = display_geometry.flood_contours(raster_path)
        contours = {
            "type": "FeatureCollection",
            "features": geo.featurecollection_5179_to_lonlat(contours_5179),
        }
        wse_csv = REPO_ROOT / "module_b_flood" / "data" / "sfincs_reach_wse.csv"
        stage_by_time = (
            display_geometry.reach_stage_series(str(wse_csv)) if wse_csv.exists() else {}
        )
        if stage_by_time:
            peak = max(stage_by_time.values())
            # 첨두 시각은 **전체 수위 곡선**에서 찾는다. 프레임(7/18 00:00~7/19 14:00)
            # 안에서만 찾으면 구간 끝의 국소 최대를 첨두라고 부르게 되는데, 실제
            # SFINCS 첨두는 7/19 16:00으로 프레임 밖이다 — 화면이 "첨두 지남"이라고
            # 말하면 그건 틀린 말이다.
            peak_time = max(stage_by_time, key=lambda k: stage_by_time[k])
            # 프레임 시각(ISO+09:00)을 수위 CSV의 키("YYYY-MM-DD HH:MM:SS")로 맞춘다
            drop_by_hour = {}
            for frame in frames:
                key = frame["time"][:19].replace("T", " ")
                stage = stage_by_time.get(key)
                if stage is not None:
                    drop_by_hour[str(frame["hour"])] = round(peak - stage, 3)
            flood_series = {
                "available": True,
                "contours": contours,
                "levels": contours_5179["levels"],
                "observed_max_m": contours_5179["observed_max_m"],
                "peak_stage_m": round(peak, 3),
                # ISO+09:00 로 맞춰 둔다 — 화면이 프레임 시각과 직접 빼서 쓴다.
                "peak_time": peak_time.replace(" ", "T") + "+09:00",
                "stage_drop_by_hour": drop_by_hour,
                "gauge": "경호교",
                "build_seconds": round(time.perf_counter() - t0, 2),
                "한계": [
                    "SFINCS를 시각마다 다시 돌린 것이 아니다 — 최대침수심 한 장에 "
                    "같은 모의의 경호교 시간별 수위를 빼서 만든 준정적(bathtub) 근사다.",
                    "수면이 한 덩어리로 오르내린다고 가정했다. 실제 홍수파는 구간을 "
                    "따라 경사를 가지므로 상·하류 시차가 이 방식에는 없다.",
                    "수위 곡선은 침수심 래스터와 같은 SFINCS 모의 산출이라 엔진을 섞지는 않았다.",
                ],
            }
            if verbose:
                print(f"  시간축 침수 등고선 {len(contours['features'])}개 · "
                      f"{len(drop_by_hour)}시각 {flood_series['build_seconds']}s")

    # 표시용 산사태 위험영역 — 5m 격자에서 나온 20~75m 조각이라 각이 그대로 보인다.
    risk_display = {"type": "FeatureCollection", "features": []}
    try:
        from module_a_landslide import risk_layers
        scenario = risk_layers.DEFAULT_SCENARIO
        feats = []
        for level in ("warning", "critical"):
            collection = risk_layers.load(scenario, level)
            for feature in geo.featurecollection_5179_to_lonlat(collection):
                props = feature["properties"]
                feats.append({
                    "type": "Feature",
                    "geometry": display_geometry.smooth_geometry(feature["geometry"]),
                    "properties": {
                        "kind": "landslide_risk",
                        "level": level,
                        "arrival_hour": props.get("arrival_hour"),
                        "arrival_time": props.get("arrival_time"),
                        "area_m2": props.get("area_m2"),
                    },
                })
        risk_display = {"type": "FeatureCollection", "features": feats}
        if verbose:
            print(f"  표시용 위험영역 {len(feats)}개")
    except ImportError:
        pass

    isolation = build_isolation(verbose=verbose, flood_hazard=_flood_hazard(flood_display))

    return {
        "schema": 1,
        "alert_id": payload["alert_id"],
        "input_sha": input_fingerprint(payload),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_commit": git_commit(),
        "pipeline_seconds": round(pipeline_s, 2),
        "mock_mode": False,
        # 시각별 강우. 화면의 시간 스크러버가 이걸로 막대를 그린다.
        "frames": frames,
        "envelope": envelope,
        "flood_display": flood_display,
        "flood_display_meta": flood_stats,
        "flood_series": flood_series,
        "isolation": isolation,
        "risk_display": risk_display,
        "정직성": [
            "envelope 은 orchestrator.run() 이 낸 값 그대로다 — 손으로 고친 값이 없다.",
            "flood_display / risk_display 는 화면 전용이다. 노출자산·고립·피해액은 "
            "envelope 안의 원본 기하로 계산돼 있고 이 둘은 거기에 관여하지 않는다.",
            "tests/test_demo_snapshot.py 가 파이프라인을 다시 돌려 이 파일과 대조한다 — "
            "모듈이 바뀌면 깨지므로 이 값은 항상 '지금 코드가 내는 값'이다.",
        ],
    }


# 프론트엔드가 자기 오리진에서 바로 읽을 정적 사본.
#
# **왜 프론트에도 두나**: 브라우저는 한 오리진에 동시 요청 수가 제한된다. 지도가
# EC2로 지형·벡터 타일을 수백 장 쏟아붓는 동안 경보 요청이 그 줄 뒤에 서면서,
# 서버가 0.013초에 답하는데도 화면에서는 200초가 걸렸다(2026-09-21 실측).
# 저장해 둔 값을 굳이 그 줄에 세울 이유가 없다 — Vercel CDN에서 바로 읽으면
# 오리진이 달라 타일과 경쟁하지 않는다.
#
# 백엔드 사본(data/precomputed)도 그대로 둔다. `?fresh=1` 실시간 경로와 API를
# 직접 쓰는 쪽이 여전히 그걸 쓴다.
UI_DEMO_DIR = REPO_ROOT / "ui" / "public" / "demo"


def write_ui_copies(snapshot: dict, verbose: bool = True) -> None:
    """화면이 쓰는 세 덩어리를 따로 떼어 정적 파일로 쓴다.

    한 덩어리로 두면 대시보드가 등고선 2MB까지 같이 받아야 해서, 화면에 처음
    숫자가 뜨는 시각이 그만큼 늦어진다. 쓰는 쪽에 맞춰 잘라 둔다.
    """
    UI_DEMO_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "alert_id": snapshot["alert_id"],
        "built_at": snapshot["built_at"],
        "built_commit": snapshot["built_commit"],
        "pipeline_seconds": snapshot["pipeline_seconds"],
        "input_sha": snapshot["input_sha"],
    }
    data = snapshot["envelope"]["data"]
    agent = data.get("timeline_agent") or {}
    actual = data.get("timeline_actual") or {}
    # 탐지 시각은 시간축의 기준점이다 — "이 프레임은 탐지 +N시간"을 쓰려면 필요하다.
    markers = {
        "detected": agent.get("detected"),
        "alert_sent": agent.get("alert_sent"),
        "official_warning": actual.get("warning_escalated"),
        "report_start": actual.get("report_start"),
    }
    envelope = json.loads(json.dumps(snapshot["envelope"]))
    envelope["meta"] = {**envelope.get("meta", {}), "served_from": "snapshot", **{
        f"snapshot_{k}": v for k, v in meta.items() if k != "alert_id"
    }}

    parts = {
        "envelope.json": envelope,
        "geojson.json": {"type": "FeatureCollection",
                         "features": snapshot["flood_display"]["features"]},
        "isolation.json": snapshot.get("isolation") or {},
        "timeline.json": {"frames": snapshot.get("frames") or [],
                          "markers": markers,
                          "flood_series": snapshot["flood_series"],
                          "risk_display": snapshot["risk_display"],
                          "meta": meta},
    }
    for name, payload in parts.items():
        path = UI_DEMO_DIR / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        if verbose:
            print(f"  ui/public/demo/{name}  {path.stat().st_size / 1e6:.2f}MB")


# 고립 분석 — 지역 x 시나리오 네 가지를 미리 돌려 둔다.
#
# 이 계산은 VWorld에서 도로망과 건물을 bbox 타일로 나눠 받아 networkx 그래프를 세운
# 다음 연결성을 푸는 것이라, 화면에서 누르면 한참 걸린다. 입력(지역 bbox·대피소·
# 시나리오 지오메트리)이 전부 고정이므로 결과도 고정이다 — 매번 다시 풀 이유가 없다.
#
# 시나리오 지오메트리는 화면(IsolationPanel)이 쓰는 것과 **같은 식**으로 만들어야 한다.
# 다르면 화면이 저장본을 못 찾고 조용히 다시 계산한다.
# 2026-09-21 예선 제출 계획 변경: 강남·서초는 빼고 산청군 전체로 넓히는 쪽으로 갔다
# (고립마을 위험·대피소 찾기, 김동현 작업 중). 여기서 강남을 같이 구우면 150초를
# 더 쓰면서 쓰이지도 않는다.
ISOLATION_REGIONS = ("sancheong", "sancheong_all")


def _demo_hazard(bbox):
    """bbox 한가운데를 세로로 가르는 좁고 긴 폴리곤 — 진입로가 끊긴 상황.

    IsolationPanel.tsx의 buildDemoHazard와 같은 식이다(폭 = 경도폭의 2%).
    한쪽만 바꾸면 저장본 키가 어긋나므로 같이 고칠 것.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    mid = (min_lon + max_lon) / 2
    half = (max_lon - min_lon) * 0.02
    return {
        "type": "Polygon",
        "coordinates": [[
            [mid - half, min_lat], [mid + half, min_lat],
            [mid + half, max_lat], [mid - half, max_lat], [mid - half, min_lat],
        ]],
    }


def _read_demo_regions() -> dict:
    """ui/src/lib/demoShelters.ts 에서 지역별 bbox·대피소를 읽는다.

    TS를 파싱하는 건 깨지기 쉽지만, 지역 정의를 파이썬에 따로 적어 두면 둘이 어긋날 때
    화면과 저장본이 **다른 지역을 계산**하게 된다 — 그쪽이 더 나쁘다. 대신 읽어낸
    개수를 아래에서 검증해서, 형식이 바뀌면 조용히 넘어가지 않고 경고를 낸다.
    """
    import re

    source = (REPO_ROOT / "ui" / "src" / "lib" / "demoShelters.ts").read_text(encoding="utf-8")
    # 각 지역 블록: "  key: {" ~ "  }," (다음 지역 시작 전까지)
    regions: dict = {}
    for match in re.finditer(r"^  (\w+): \{$(.*?)^  \},$", source, re.S | re.M):
        key, body = match.group(1), match.group(2)
        bbox_match = re.search(r"isolationBbox: \[([^\]]+)\]", body)
        if not bbox_match:
            continue
        bbox = tuple(float(v) for v in bbox_match.group(1).split(","))
        shelters = [
            (float(lon), float(lat))
            for lon, lat in re.findall(r"lon: (-?[\d.]+), lat: (-?[\d.]+)", body)
        ]
        if len(bbox) == 4 and shelters:
            regions[key] = {"bbox": bbox, "shelters": shelters}
    return regions


# 읽기가 성공했는지 확인할 기준값 — 이 숫자가 바뀌면 지역 정의가 바뀐 것이므로
# 여기도 같이 고쳐야 한다(자동으로 맞추면 파싱 실패를 알아챌 방법이 없어진다).
EXPECTED_SHELTERS = {"sancheong": 8, "sancheong_all": 104}


def _flood_hazard(flood_display: dict):
    """Module B의 실제 침수범위(표시용 폴리곤 중 최저 수심 구간) — 고립분석의 "실제 침수" 시나리오 입력.

    표시용 폴리곤은 누적 구간이라 band 0(수심 0.3m 이상)이 가장 넓은 범위를 통째로 덮는다.
    승용차가 못 지나가는 수심을 0.3m로 본 가정이다(depth_thr_m). 화면 전용이라던 폴리곤을 쓰는
    이유: 계산에 쓰인 원본 기하는 5179 격자 폴리곤 수백 개라 lon/lat 변환·병합이 이쪽이 이미 돼 있다.
    """
    feats = [f for f in (flood_display or {}).get("features", []) if (f.get("properties") or {}).get("band") == 0]
    return feats[0]["geometry"] if feats else None


def build_isolation(verbose: bool = True, flood_hazard: dict | None = None) -> dict:
    from module_e_routing import isolation as iso

    regions = _read_demo_regions()
    out: dict = {}
    for region in ISOLATION_REGIONS:
        info = regions.get(region)
        expected = EXPECTED_SHELTERS.get(region)
        if not info or (expected and len(info["shelters"]) != expected):
            print(f"  [경고] 고립 {region}: 지역 정의를 못 읽었습니다"
                  f"(대피소 {len(info['shelters']) if info else 0}곳, {expected}곳 기대) — "
                  f"demoShelters.ts 형식이 바뀌었는지 확인하십시오. 이 지역은 건너뜁니다.")
            continue

        scenarios = [("base", None), ("hazard", _demo_hazard(info["bbox"]))]
        # 실제 침수범위는 산청 AOI(경호강 일대)라 군 전체 범위에서만 의미가 있다.
        if region == "sancheong_all" and flood_hazard:
            scenarios.append(("flood", flood_hazard))
        for scenario, hazard in scenarios:
            t0 = time.perf_counter()
            try:
                result = iso.check_isolation(info["bbox"], info["shelters"], hazard)
            except Exception as exc:  # noqa: BLE001 - 한 조합이 실패해도 나머지는 굽는다
                print(f"  [경고] 고립 {region}:{scenario} 실패 — {exc}")
                continue
            # bbox와 대피소 수를 같이 적어 둔다. 산청을 군 전체로 넓히는 작업이
            # 진행 중이라 bbox가 바뀔 텐데, 그때 이 저장본을 그대로 쓰면 화면이
            # **다른 범위**의 고립 결과를 보여주게 된다. 화면은 자기 bbox와 대조해
            # 안 맞으면 저장본을 버리고 실제로 계산한다.
            out[f"{region}:{scenario}"] = {
                "bbox": list(info["bbox"]),
                "shelter_count": len(info["shelters"]),
                "result": result,
            }
            if verbose:
                print(f"  고립 {region}:{scenario} 고립건물 {result.get('isolated_building_count')}동 "
                      f"{time.perf_counter() - t0:.1f}s")
    return out


def main() -> int:
    print(f"데모 스냅샷 생성 → {SNAPSHOT_PATH.relative_to(REPO_ROOT)}")
    snapshot = build()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, separators=(",", ":"))
    size_mb = SNAPSHOT_PATH.stat().st_size / 1e6
    print(f"완료: {size_mb:.2f}MB  input_sha={snapshot['input_sha']}  "
          f"commit={snapshot['built_commit']}")
    write_ui_copies(snapshot)

    # 구운 결과가 실제로 실도로 경로인지 마지막에 다시 확인한다 — 빌드는 성공했는데
    # 내용이 근사인 채로 배포되는 게 제일 나쁜 경우다.
    route = (snapshot["envelope"]["data"]["alert_package"].get("shelter_route") or {})
    if route.get("fallback_used"):
        print("  [경고] 대피 경로가 직선거리 근사입니다 — tests/test_demo_snapshot.py가 "
              "이걸 실패로 잡습니다.")
    else:
        pts = len((route.get("route_5179") or {}).get("coordinates") or [])
        print(f"  대피 경로: 실도로 {pts}점, ETA {route.get('eta_min')}분")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
