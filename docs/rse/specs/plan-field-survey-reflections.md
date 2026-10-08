# Implementation Plan: 현장조사 반영 — 고립 대피 시한 · 도로 보정 · 통제 구간 · 침수 계산 범위

---
**Date:** 2026-10-08
**Author:** AI Assistant
**Status:** Complete (병합·배포 대기)
**Related Documents:**
- 현장조사 절 `C:\Users\user\Desktop\하수범_공모전\Aquaguard.AI\아쿠아가드_현장조사.docx` — "시스템에 반영할 점" 5항목 (팀 합의 완료)

---

## Overview

산청읍 송경천 현장조사(2026-09-25)에서 확인한 내용을 시스템에 반영한다. 현장조사 절의 "시스템에 반영할 점" 다섯 가지가 대상이다.

1. **고립 예상 마을의 경보를 앞당긴다.** 시간별 침수로 고립 판정을 다시 돌려, 마을마다 진입로가 끊기는 시각을 구한다. 그 시각보다 1시간 앞을 대피 시한으로 표시한다.
2. **지도에 없는 도로 속성을 보강한다.** 현장 보정 기록 파일과 높이 제한으로 구조차량 진입 곤란 건물을 판정한다. 끊긴 도로에는 도로명·교량 여부·등급을 붙인다.
3. **복구·통제 구간을 반영한다.** 통제 구간 파일을 두고, 고립 판정과 대피 경로에 적용한다.
4. **침수 계산 범위를 넓힌다.** 여러 침수 모형 영역을 받을 수 있게 하고, 덕천강 모형 구축 스크립트를 준비한다. 실행은 G: 드라이브 PC에서 한다.
5. **계산하지 않은 곳을 표시한다.** 침수 모형이 덮지 않은 범위를 지도와 경로·고립 결과에 표시한다.

**Goal:** 위 다섯 가지가 저장본·API·화면에 반영되고, 기존 수치(고립 2,445동, 경보 봉투)는 바뀌지 않는다.

**Motivation:** 현장에서 확인한 "길은 한순간에 닫힌다", "지도에 없는 길의 성질이 고립을 좌우한다", "계산하지 않은 곳이 안전해 보인다"를 시스템이 실제로 다루게 한다.

### 팀 결정 (2026-10-08)
| 항목 | 결정 |
|---|---|
| ① 경보 방식 | 진입로가 끊기는 시각 기준 (확률 임계 낮추기 아님) |
| ① 여유 시간 | 단절 1시간 전 — `policies/module_e.json`에 TEAM_DECISION으로 기록 |
| ② 마을안길 | 이번에는 도로망에 넣지 않음 — 한계로 명시 |
| ④ 덕천강 | 기반·스크립트만 만들고 실행은 G: PC에서 |

### 조사 중 확인한 사실 (설계 전제)
- **도로 데이터(표준노드링크)에는 차로 수·도로 폭이 없다.** `rest_w`는 전 링크 0이다. 쓸 수 있는 속성은 `rd_rank_h`, `rd_type_h`(교량·터널·고가차도), `rest_veh_h`, `rest_h`(높이 제한 cm), `max_spd`, `road_name`이다.
- **`rest_veh_h = "이륜차"`는 이륜차 통행 금지라는 뜻이다.** 150개 중 140개가 고속국도라 구조차량 판정에는 쓸 수 없다.
- **높이 제한은 산청에서 모두 4.0m 이상**이다(221개 링크). 구조차량 높이 가정값 3.8m에서는 산청에서 걸러지는 링크가 없다. 도시로 확장할 때(지하차도) 의미가 생긴다.
- **마을안길은 표준노드링크에 없다.** 현장 사진 4의 길 주변 수백 m 안에 링크가 0개였다. 도로명주소 도로 레이어(`LT_L_SPRD`)에는 있지만 `rn`(도로명) 속성만 있다.
- **교량은 고립 수치에 거의 영향이 없다.** 침수 범위와 겹쳐 제거되는 교량 구간은 121개다. 이 구간을 살려도 고립 건물은 2,445동에서 2,441동이 될 뿐이다. 상판 높이 자료가 없으므로 현행 처리(겹치면 통행 불가)를 유지하고, 화면에 교량이라고 표시한다.
- **시간별 침수의 최저 수위 시각에도 하천 본류는 침수로 잡힌다.** 최대침수심에서 수위강하를 빼는 방식이라 본류 수로가 늘 남는다(7/19 00:00 기준 460 ha). 그래서 대피 시한은 "첨두를 포함하는 고립 구간이 시작된 시각"으로 정의한다(Phase 5).

## Current State Analysis

**Existing Implementation:**
- `module_e_routing/isolation.py:183-196` — `build_road_graph`. 엣지에 `link_id`와 `rd_type_h`만 싣는다. 이후 어디서도 읽지 않는다.
- `module_e_routing/isolation.py:199-221` — `remove_hazard_edges`. 위험 도형과 `intersects`하는 2점 세그먼트를 제거한다.
- `module_e_routing/isolation.py:246-258` — `blocked_road_features`. 속성이 `{"kind": "blocked_road"}`뿐이다.
- `module_e_routing/isolation.py:382-471` — `check_isolation`. 호출할 때마다 그래프와 건물 매핑을 새로 만든다.
- `module_e_routing/__init__.py:65-87` — `_shelter_blocked_by_risk`. FeatureCollection을 `shapely.geometry.shape`에 넘겨 예외가 나고, 그 예외가 무시된다. **그래서 Module B 침수범위(FeatureCollection)가 대피소를 한 번도 걸러내지 못했다.**
- `api_server.py:1146-1166` — `_sancheong_flood_shape`. 스냅샷 band 0 중 첫 번째 피처만 읽는다.
- `api_server.py:1169-1198` — `_apply_flood_to_route`. 경로 전체를 침수와 교차 검사한다.
- `api_server.py:1201-1217` — `/isolation-check`.
- `scripts/build_demo_snapshot.py:62-247` — `build()`. 침수 래스터 1장, 경호교 수위 1개 기준이다.
- `scripts/build_demo_snapshot.py:361-369` — `_flood_hazard`. band 0 첫 피처만 쓴다.
- `scripts/build_demo_snapshot.py:249-294` — `write_ui_copies`. `ui/public/demo/{envelope,geojson,timeline,isolation}.json`을 쓴다.
- `module_o_orchestrator/exposure_layers.py:479-494` — `flood_depth_raster(aoi)`. AOI당 래스터 1장이다.
- `module_b_flood/scripts/33_sfincs_build_reach.py:31` — 경호강 격자 `X0,Y0=1028000,1703000; DX=50; NMAX=400; MMAX=280`.
- `module_b_flood/scripts/25_sfincs_build.py` — 군 전체 강우 강제 모형. 구축만 하고 실행하지 않았다.
- `ui/src/components/MapExplorer.tsx:1477-1516` — `scheduleIsolationCheck`. 프레임마다 `/isolation-check`를 호출한다.
- `ui/src/components/MapExplorer.tsx:1593-1604` — `floodAtFrame`. 수위강하에 0.3을 하드코딩해 더한다.
- `ui/src/components/MapExplorer.tsx:2011-2124` — 범례("지금 지도에 올라와 있는 것"). JSX에 직접 적혀 있다.
- `ui/src/components/MapExplorer.tsx:2291-2298` — 스크러버 마커(우리 탐지/발송/공식 경보).
- `ui/src/components/panels/EvacuationPanel.tsx:100` — `.then(({ results }) =>`. 서버가 보낸 `warnings`를 버린다.
- `policies/policy.schema.json` — 정책 행 스키마. Module E에는 정책 파일이 없다.

**Current Limitations:**
- 마을 단위 경보와 "길이 언제 끊기는가"가 어디에도 없다.
- 도로 속성을 고립 판정에 하나도 쓰지 않는다.
- 통제 구간을 넣을 방법이 없다.
- 침수 모형이 어디까지 계산했는지가 API·저장본·화면 어디에도 없다. 래스터 nodata=0이라 "안 잠김"과 "계산 안 함"이 같은 값이다.
- 침수 모형을 한 지역에 하나만 쓸 수 있다.

## Desired End State

**Success Looks Like:**
- 시간축을 옮기면, 대피 시한이 지났지만 아직 진입로가 끊기지 않은 마을이 지도에 따로 표시된다.
- 스크러버에 "고립 대비 시한" 마커가 생긴다.
- 고립마을 패널(침수 반영)에 군집마다 "진입로 단절 예상 시각 / 대피 시한"이 나온다.
- 끊긴 도로를 가리키면 "○○로 · 교량 · 지방도 — 통행 불가"처럼 실제 도로 정보가 보인다.
- 현장 보정 파일에 링크를 적으면 그 링크에만 의존하는 건물이 "구조차량 진입 곤란"으로 나온다.
- 통제 구간 파일에 구간을 적으면 고립 판정에서 그 구간이 끊기고, 대피 경로가 그 구간을 지나면 "통제 구간 통과"로 표시된다. 지도에도 통제 구간이 그려진다.
- 지도에 "침수 계산 범위 밖" 영역이 회색으로 덮인다. 대피소 찾기에서 범위 밖 대피소에 "침수 판정 범위 밖" 표시가 붙는다.
- 덕천강 래스터가 `module_b_flood/data/`에 들어오면 저장본을 다시 만드는 것만으로 지도·고립·계산 범위에 반영된다.
- `sancheong_all:flood` 고립 2,445동과 경보 봉투는 바뀌지 않는다.

## What We're NOT Doing

- [ ] 마을안길(`LT_L_SPRD`)을 고립 도로망에 넣기 — 팀 결정. 한계로 명시한다.
- [ ] 덕천강 SFINCS 실제 실행 — 입력이 G: 드라이브에 있다. Module B 담당이 실행한다.
- [ ] 실시간 경보 경로(오케스트레이터)의 마을 단위 경보와 다중 침수 도메인 — 실시간 경로에는 시간별 예보 침수가 없다. 대피 시한은 사후 재현 저장본에서만 계산한다. 노출자산(Module D)도 경호강 래스터 1장 그대로다.
- [ ] 도로 폭 데이터 확보(도로명주소 전자지도 다운로드) — 계정·다운로드가 필요한 외부 자료다.
- [ ] 교량 상판 높이 반영 — 자료가 없다. 영향은 4동이다.
- [ ] 통제 구간·현장 보정의 실제 데이터 입력 — 빈 파일로 출발한다. 위치가 확인된 통제 구간이 없다.
- [ ] 네이버 경로의 우회 탐색 — 기존과 같이 겹침만 검사한다.

## Implementation Approach

**Key Architectural Decisions:**
1. **고립 판정을 "문맥(그래프·건물 매핑) 1회 구축 + 위험 도형마다 평가"로 나눈다.**
   - **Rationale:** 시간별 판정(37시각)에서 그래프·건물 매핑을 매번 다시 만들면 시각당 약 8초가 걸린다. 문맥을 한 번만 만들면 시각당 STRtree 질의와 BFS만 남는다.
   - **Trade-offs:** `check_isolation`의 내부 구조가 바뀐다. 출력 키는 그대로 두고 키만 추가한다. 회귀 테스트로 2,445동을 고정한다.
2. **대피 시한은 경보 봉투에 넣지 않고 저장본·시간축에만 둔다.**
   - **Rationale:** `tests/test_demo_snapshot.py`가 봉투를 실시간 재실행 결과와 대조한다. 오케스트레이터에는 시간별 침수가 없다.
   - **Alternatives considered:** 봉투 `alert_package`에 추가 — 계약 변경과 실시간 경로 변경이 필요해 제외했다.
3. **통제 구간은 `link_ids`(정확) 또는 Polygon(면 통제)으로만 받는다.**
   - **Rationale:** 선 기하만으로 교차 검사하면 교차로에서 다른 도로까지 끊긴다.
4. **침수 모형 영역은 `module_b_flood/domains.json` 레지스트리로 관리한다.**
   - 래스터 파일이 있는 영역만 쓴다. 시간별 수위가 있는 영역은 1개까지 시간축으로 쓰고, 나머지는 최대 범위 고정(`flood_static`)으로 쓴다.

**Patterns to Follow:**
- 정책 행 형식과 jsonschema 검증 — `module_d_exposure_overlay/policy.py:74-96`
- 사전계산 → `ui/public/demo/*.json` 정적 사본 — `scripts/build_demo_snapshot.py:249-294`
- 정적 사본 우선, 실패 시 API — `ui/src/lib/api.ts:277-305` (`getAlertTimeline`)
- 실데이터 없는 단위 테스트(합성 그래프) — `module_e_routing/tests/test_blocked_roads.py`

## Implementation Phases

### 공통 합성 픽스처 (Phase 3·4·5가 함께 쓴다)

`module_e_routing/tests/conftest.py` (신규):
```python
"""고립 판정 단위 테스트용 합성 도로·건물. 네트워크를 쓰지 않는다.

   S(대피소) ── e1 ── A ── e2 ── B ── e3 ── C
                                 │
                             마을 건물(B 옆 20m)

e2가 끊기면 마을은 고립된다. 경도 0.001° ≈ 91m (35.4°N).
"""
import pytest

LAT = 35.4
S, A, B, C = (128.000, LAT), (128.001, LAT), (128.002, LAT), (128.003, LAT)
VILLAGE = (128.0021, LAT + 0.0002)


def road(link_id, a, b, **props):
    return {"type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [list(a), list(b)]},
            "properties": {"link_id": link_id, "road_name": f"길{link_id}", "rd_type_h": "일반도로",
                           "rd_rank_h": "시·군도", "rest_veh_h": "모두통행가능", "rest_h": "0", **props}}


def building(lon, lat, d=0.00003):
    ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {}}


def box(lon0, lat0, lon1, lat1):
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]}


# e2 중간만 덮는 위험 (마을 건물은 덮지 않는다)
HAZARD_E2 = box(128.0013, LAT - 0.0001, 128.0017, LAT + 0.0001)


@pytest.fixture
def toy(monkeypatch):
    from module_e_routing import isolation as iso
    roads = [road("e1", S, A), road("e2", A, B), road("e3", B, C)]
    blds = [building(*VILLAGE)]
    monkeypatch.setattr(iso, "fetch_roads", lambda bbox: roads)
    monkeypatch.setattr(iso, "fetch_buildings", lambda bbox: blds)
    return {"roads": roads, "buildings": blds, "bbox": (127.99, 35.39, 128.01, 35.41), "shelters": [S]}
```

---

### Phase 1: Module E 정책 파일

**Objective:** 대피 시한 여유(1h, 팀 결정), 통행 불가 수심(0.3m), 구조차량 높이(3.8m)를 출처와 함께 정책 파일로 둔다.

**Tasks:**
- [x] **실패하는 테스트** — `module_e_routing/tests/test_policy.py` (신규):
  ```python
  import pytest
  from module_e_routing import policy


  def test_module_e_policy_rows():
      p = policy.load()
      assert p.version == "module_e_v1"
      assert p.value("evacuate_lead_before_cut_hours") == 1.0
      assert p.row("evacuate_lead_before_cut_hours").status == "TEAM_DECISION"
      assert p.value("flood_impassable_depth_m") == 0.3
      assert p.value("rescue_vehicle_height_m") == 3.8


  def test_unknown_row_raises():
      with pytest.raises(policy.PolicyError):
          policy.load().value("no_such_row")
  ```
  실행: `python -m pytest module_e_routing/tests/test_policy.py -q` → `ImportError`로 실패.
- [x] **정책 파일** — `policies/module_e.json` (신규):
  ```json
  {
    "policy_version": "module_e_v1",
    "description": "Module E(대피 경로·고립 판정) 정책값. 현장조사(2026-09-25) 반영 사항을 포함한다.",
    "rows": [
      {"id": "evacuate_lead_before_cut_hours", "value": 1.0, "unit": "h", "status": "TEAM_DECISION",
       "source": {"agency": null, "document": "팀 합의 — 현장조사 반영 사항 ①", "clause": null, "url": null,
                  "retrieved": "2026-10-08", "effective": "2026-10-08"},
       "note": "진입로 단절 예상 시각보다 이만큼 앞을 대피 시한으로 본다. 고령 주민의 준비·이동 시간을 고려한 값."},
      {"id": "flood_impassable_depth_m", "value": 0.3, "unit": "m", "status": "ASSUMPTION",
       "source": {"agency": null, "document": null, "clause": null, "url": null, "retrieved": "2026-10-08"},
       "note": "승용차가 지나갈 수 없는 수심의 가정값. 고립 판정·대피 경로·화면 침수 표시가 모두 이 값을 쓴다."},
      {"id": "rescue_vehicle_height_m", "value": 3.8, "unit": "m", "status": "PLACEHOLDER",
       "source": {"agency": null, "document": null, "clause": null, "url": null, "retrieved": "2026-10-08"},
       "note": "대형 구조·소방차 높이의 보수적 가정값. 공식 근거 확인 전. 표준노드링크 rest_h가 이보다 낮은 링크는 구조차량 통행 불가로 본다. 산청의 높이 제한은 모두 4.0m 이상이라 현재 걸리는 링크가 없다."}
    ]
  }
  ```
- [x] **로더** — `module_e_routing/policy.py` (신규):
  ```python
  """Module E 정책 로더 — policies/module_e.json을 스키마로 검증해 읽는다.

  Module D의 로더(module_d_exposure_overlay/policy.py)와 같은 형식이지만, 모듈 사이는
  계약 파일로만 묶는다는 원칙 때문에 import하지 않고 따로 둔다.
  """
  from __future__ import annotations

  import json
  from dataclasses import dataclass
  from functools import lru_cache
  from pathlib import Path
  from typing import Any

  REPO = Path(__file__).resolve().parents[1]
  POLICY_PATH = REPO / "policies" / "module_e.json"
  SCHEMA_PATH = REPO / "policies" / "policy.schema.json"


  class PolicyError(RuntimeError):
      pass


  @dataclass(frozen=True)
  class Row:
      id: str
      value: Any
      unit: str | None
      status: str
      source: dict
      note: str | None


  @dataclass(frozen=True)
  class Policy:
      version: str
      rows: dict[str, Row]

      def row(self, row_id: str) -> Row:
          if row_id not in self.rows:
              raise PolicyError(f"module_e 정책에 '{row_id}' 행이 없다")
          return self.rows[row_id]

      def value(self, row_id: str) -> Any:
          return self.row(row_id).value


  @lru_cache(maxsize=1)
  def load() -> Policy:
      import jsonschema

      doc = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
      schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
      try:
          jsonschema.validate(doc, schema)
      except jsonschema.ValidationError as exc:
          raise PolicyError(f"module_e 정책 스키마 위반: {exc.message}") from exc
      rows = {r["id"]: Row(r["id"], r["value"], r["unit"], r["status"], r["source"], r["note"]) for r in doc["rows"]}
      if len(rows) != len(doc["rows"]):
          raise PolicyError("module_e 정책에 중복된 행 id가 있다")
      return Policy(doc["policy_version"], rows)
  ```
- [x] 실행: `python -m pytest module_e_routing/tests/test_policy.py -q` → 2 passed.
- [x] 커밋: `Give Module E a policy file for the field-survey values`

**Dependencies:** 없음

---

### Phase 2: 버그 수정 — FeatureCollection 위험영역이 대피소를 걸러내지 못함

**Objective:** `_shelter_blocked_by_risk`가 Module B 침수범위(FeatureCollection)로도 대피소를 제외하게 한다.

**Tasks:**
- [x] **실패하는 테스트** — `module_e_routing/tests/test_risk_polygons.py` (신규):
  ```python
  from module_e_routing import _shelter_blocked_by_risk

  SHELTER = {"shelter_id": "S", "x_5179": 1000.0, "y_5179": 1000.0}
  SQUARE = {"type": "Polygon", "coordinates": [[[900, 900], [1100, 900], [1100, 1100], [900, 1100], [900, 900]]]}


  def test_featurecollection_risk_excludes_shelter():
      fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": SQUARE, "properties": {}}]}
      assert _shelter_blocked_by_risk(SHELTER, [{"geometry_5179": fc}]) is True


  def test_feature_risk_excludes_shelter():
      ft = {"type": "Feature", "geometry": SQUARE, "properties": {}}
      assert _shelter_blocked_by_risk(SHELTER, [{"geometry_5179": ft}]) is True


  def test_plain_polygon_still_excludes():
      assert _shelter_blocked_by_risk(SHELTER, [{"geometry_5179": SQUARE}]) is True


  def test_empty_geometries_do_not_exclude():
      empty_fc = {"type": "FeatureCollection", "features": []}
      assert _shelter_blocked_by_risk(SHELTER, [{"geometry_5179": {}}, {"geometry_5179": empty_fc}]) is False
  ```
  실행 → `test_featurecollection_*`, `test_feature_*` 실패.
- [x] **수정** — `module_e_routing/isolation.py:224`의 `_hazard_shape`를 공개 이름 `hazard_shape`로 바꾸고, 같은 파일의 호출부 `:211`, `:402`를 고친다. 이 함수는 좌표계에 무관하다(GeoJSON → shapely).
- [x] **수정** — `module_e_routing/__init__.py:76-86`의 루프 본문을 바꾼다:
  ```python
      from .isolation import hazard_shape  # GeoJSON(Geometry·Feature·FeatureCollection) → shapely

      point = shapely.geometry.Point(shelter["x_5179"], shelter["y_5179"])
      for risk in risk_polygons:
          shape = hazard_shape(risk.get("geometry_5179"))
          if shape is not None and shape.contains(point):
              return True
      return False
  ```
- [x] 실행: `python -m pytest module_e_routing/tests/ -q` → 전부 통과(기존 `test_blocked_roads.py` 포함).
- [x] **영향 확인** — 데모 대피소 S001은 생비량면에 있고, 생비량면은 침수 모형 밖이다. 따라서 저장본의 `shelter_route`는 바뀌지 않는다. `python -m pytest tests/test_demo_snapshot.py -q`로 확인한다.
- [x] 커밋: `Let Module B's flood collection actually exclude shelters`

**Dependencies:** 없음

---

### Phase 3: 고립 판정 재구성 · 도로 속성 · 구조차량 진입

**Objective:** 문맥 1회 구축 구조로 바꾼다(동작 보존). 끊긴 도로에 속성을 붙이고, 높이 제한과 현장 보정으로 구조차량 진입 곤란 건물을 낸다.

**Tasks:**
- [x] **회귀 테스트 먼저(동작 보존)** — `module_e_routing/tests/test_isolation_regression.py` (신규):
  ```python
  """재구성 전후로 산청군 전체·실제 침수 고립 수치가 같아야 한다.
  VWorld 캐시(data/cache/isolation/)가 없으면 건너뛴다 — 네트워크를 쓰지 않는다."""
  import json, re
  from pathlib import Path
  import pytest

  REPO = Path(__file__).resolve().parents[2]
  SNAP = REPO / "data" / "precomputed" / "demo_snapshot.json"


  def _inputs():
      snap = json.loads(SNAP.read_text(encoding="utf-8"))
      ent = snap["isolation"]["sancheong_all:flood"]
      hz = [f for f in snap["flood_display"]["features"] if f["properties"].get("band") == 0][0]["geometry"]
      ts = (REPO / "ui/src/lib/demoShelters.ts").read_text(encoding="utf-8")
      blk = ts[ts.index("sancheong_all: {"):]
      blk = blk[:blk.index("isolationBbox")]
      sh = [(float(a), float(b)) for a, b in re.findall(r"lon: ([\d.]+), lat: ([\d.]+)", blk)]
      return tuple(ent["bbox"]), sh, hz, ent["result"]


  def test_county_flood_isolation_unchanged():
      from module_e_routing import isolation as iso
      bbox, sh, hz, stored = _inputs()
      key = iso.cache_file(iso.VWORLD_ROAD_LAYER, bbox)
      if not key.exists():
          pytest.skip("VWorld 캐시 없음")
      fresh = iso.check_isolation(bbox, sh, hz)
      assert fresh["isolated_building_count"] == stored["isolated_building_count"] == 2445
      assert len(fresh["blocked_roads"]["features"]) == len(stored["blocked_roads"]["features"])
  ```
  `iso.cache_file`이 없으므로 처음에는 실패한다. `isolation.py:138-139`의 캐시 경로 계산을 `cache_file(layer, bbox) -> Path`로 빼내고 `_fetch_tiled_cached`에서 쓰게 하면 통과한다. 재구성 전에 통과하는 것을 먼저 확인한다.
- [x] **실패하는 단위 테스트** — `module_e_routing/tests/test_isolation_context.py` (신규, conftest 사용):
  ```python
  from module_e_routing import isolation as iso
  from module_e_routing.tests.conftest import HAZARD_E2, road, S, A, B, C


  def test_toy_village_isolated_when_e2_cut(toy):
      r = iso.check_isolation(toy["bbox"], toy["shelters"], HAZARD_E2)
      assert r["isolated_building_count"] == 1
      assert r["rescue_limited_count"] == 0


  def test_blocked_road_carries_link_attributes(toy):
      r = iso.check_isolation(toy["bbox"], toy["shelters"], HAZARD_E2)
      props = r["blocked_roads"]["features"][0]["properties"]
      assert props == {"kind": "blocked_road", "link_id": "e2", "road_name": "길e2",
                       "rd_type_h": "일반도로", "rd_rank_h": "시·군도"}


  def test_low_clearance_link_is_rescue_limited(monkeypatch, toy):
      toy["roads"][1] = road("e2", A, B, rest_h="350")  # 3.5m 높이 제한 < 구조차량 3.8m
      monkeypatch.setattr(iso, "fetch_roads", lambda bbox: toy["roads"])
      r = iso.check_isolation(toy["bbox"], toy["shelters"], None)
      assert r["isolated_building_count"] == 0       # 주민은 갈 수 있다
      assert r["rescue_limited_count"] == 1          # 구조차량은 못 들어간다


  def test_field_override_marks_link_impassable(monkeypatch, toy):
      monkeypatch.setattr(iso, "load_road_overrides",
                          lambda: {"e2": {"vehicle_passable": False, "note": "차 한 대 폭", "source": "현장조사"}})
      r = iso.check_isolation(toy["bbox"], toy["shelters"], None)
      assert r["rescue_limited_count"] == 1
      assert any("현장 보정" in w for w in r["warnings"])


  def test_context_evaluate_matches_check_isolation(toy):
      ctx = iso.build_context(toy["roads"], toy["buildings"])
      ev = iso.evaluate(ctx, toy["shelters"], iso.hazard_shape(HAZARD_E2))
      assert len(ev["isolated_idx"]) == 1
  ```
- [x] **구현** — `module_e_routing/isolation.py`:
  - `build_road_graph`(`:183-196`): 엣지 속성에 `road_name`, `rd_rank_h`, `rest_h`를 추가한다:
    ```python
    graph.add_edge(na, nb, weight=weight, link_id=props.get("link_id"), rd_type_h=props.get("rd_type_h"),
                   rd_rank_h=props.get("rd_rank_h"), road_name=props.get("road_name"), rest_h=props.get("rest_h"))
    ```
  - `blocked_road_features(removed_edges, graph)`: 속성에 `link_id, road_name, rd_type_h, rd_rank_h`를 싣는다. 호출부 `:412`에 `graph`를 넘긴다(제거 전 그래프 사본에서 읽는다).
  - 현장 보정 로더:
    ```python
    ROAD_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "road_overrides.json"

    def load_road_overrides() -> dict[str, dict]:
        """현장 보정 기록 {link_id: {vehicle_passable, two_way, note, source, observed}}. 파일이 없으면 빈 dict."""
        if not ROAD_OVERRIDES_PATH.exists():
            return {}
        doc = json.loads(ROAD_OVERRIDES_PATH.read_text(encoding="utf-8"))
        return {str(r["link_id"]): r for r in doc.get("links", [])}
    ```
  - 문맥과 평가:
    ```python
    @dataclass
    class IsolationContext:
        graph: nx.Graph
        edges: list
        edge_tree: shapely.STRtree
        buildings: list            # shapely 건물 윤곽
        building_tree: shapely.STRtree
        centroids: np.ndarray      # (N,2)
        node_of: list              # 건물별 최근접 노드
        dist_m: np.ndarray         # 건물별 최근접 노드 거리
        vehicle_blocked: list      # 구조차량 통행 불가 엣지 (높이 제한·현장 보정)
        override_hits: int

    def build_context(road_features, building_features) -> IsolationContext:
        from . import policy
        graph = build_road_graph(road_features)
        edges = list(graph.edges())
        edge_tree = shapely.STRtree(shapely.linestrings([[u, v] for u, v in edges])) if edges else None
        shapes = []
        for f in building_features:
            try:
                shapes.append(shapely.geometry.shape(f["geometry"]))
            except Exception:
                continue
        building_tree = shapely.STRtree(shapes) if shapes else None
        centroids = np.array([(s.centroid.x, s.centroid.y) for s in shapes], dtype=float).reshape(-1, 2)
        node_of, dist_m = _NodeIndex(graph).nearest(centroids)
        height = float(policy.load().value("rescue_vehicle_height_m"))
        overrides = load_road_overrides()
        vehicle_blocked, hits = [], 0
        for u, v, d in graph.edges(data=True):
            rest_cm = float(d.get("rest_h") or 0)
            ov = overrides.get(str(d.get("link_id")))
            if ov is not None and ov.get("vehicle_passable") is False:
                vehicle_blocked.append((u, v)); hits += 1
            elif 0 < rest_cm < height * 100:
                vehicle_blocked.append((u, v))
        return IsolationContext(graph, edges, edge_tree, shapes, building_tree, centroids, node_of, dist_m,
                                vehicle_blocked, hits)

    def evaluate(ctx, shelters, hazard, closed_edges=()) -> dict:
        """위험 도형 하나에 대한 판정. 반환: isolated_idx(건물 인덱스), direct_idx, rescue_limited_idx,
        removed_edges, usable_shelters, stats."""
        usable = [s for s in shelters if hazard is None or not hazard.contains(shapely.geometry.Point(*s))]
        g0 = nx.restricted_view(ctx.graph, [], list(closed_edges))
        baseline = reachable_from_shelters(nx.Graph(ctx.graph), usable)   # 통제·위험 적용 전
        removed = []
        if hazard is not None and ctx.edge_tree is not None:
            removed = [ctx.edges[k] for k in ctx.edge_tree.query(hazard, predicate="intersects")]
        g1 = nx.restricted_view(ctx.graph, [], list(closed_edges) + removed)
        reach = reachable_from_shelters(g1, usable)
        g2 = nx.restricted_view(ctx.graph, [], list(closed_edges) + removed + ctx.vehicle_blocked)
        reach_vehicle = reachable_from_shelters(g2, usable)
        direct = set()
        if hazard is not None and ctx.building_tree is not None:
            direct = {int(k) for k in ctx.building_tree.query(hazard, predicate="intersects")}
        isolated, rescue_limited = [], []
        stats = {"unmapped": 0, "preexisting": 0}
        for k, node in enumerate(ctx.node_of):
            if k in direct:
                continue
            if ctx.dist_m[k] > ISOLATION_MAX_SNAP_M:
                stats["unmapped"] += 1; continue
            if node not in baseline:
                stats["preexisting"] += 1; continue
            if node not in reach:
                isolated.append(k)
            elif node not in reach_vehicle:
                rescue_limited.append(k)
        return {"isolated_idx": isolated, "direct_idx": sorted(direct), "rescue_limited_idx": rescue_limited,
                "removed_edges": removed, "usable_shelters": usable, "stats": stats}
    ```
    `reachable_from_shelters`(`:282-291`)는 `nx.restricted_view`의 읽기 전용 그래프도 받도록 그대로 쓴다. `nx.node_connected_component`는 뷰에서도 동작한다. `g0`은 Phase 4 통제 구간에서 쓴다. 이 Phase에서는 `closed_edges=()`라 `g0 == graph`이다.
  - `check_isolation`(`:382-471`)은 `build_context(fetch_roads(bbox), fetch_buildings(bbox))` → `evaluate(...)`로 다시 쓴다. 기존 경고 문구와 출력 키를 그대로 유지하고 다음 키를 추가한다.
    - `"rescue_limited_count"`
    - `"rescue_limited_buildings"`(Point FC)
    - 경고: `rescue_limited_count > 0`이면 `"주민은 대피소까지 갈 수 있지만 구조차량이 들어가기 어려운 건물 N동(높이 제한·현장 보정 기록 기준)"`
    - 경고: `ctx.override_hits > 0`이면 `"현장 보정 기록 N개 링크 반영"`
    - 경고: 항상 `"구조차량 판정은 높이 제한과 현장 보정 기록만 쓴다 — 도로 데이터에 폭 정보가 없고 마을안길은 도로망에 없다"`
- [x] **빈 보정 파일** — `data/road_overrides.json` (신규):
  ```json
  {"version": 1,
   "description": "현장에서 확인한 도로 속성 보정. link_id는 표준노드링크(LT_L_MOCTLINK) 링크 ID.",
   "fields": {"vehicle_passable": "false면 구조차량 통행 불가로 본다", "two_way": "교행 가능 여부(기록용)",
              "note": "관찰 내용", "source": "현장조사 등", "observed": "YYYY-MM-DD"},
   "links": []}
  ```
- [x] 실행: `python -m pytest module_e_routing/tests/ -q` → 전부 통과. 회귀 테스트가 2,445동을 유지하는지 확인한다.
- [x] 커밋: `Build the isolation graph once, and say which road is cut`

**Dependencies:** Phase 1

---

### Phase 4: 복구·통제 구간

**Objective:** 통제 구간 파일을 고립 판정·대피 경로·지도에 반영한다.

**Tasks:**
- [x] **실패하는 테스트** — `module_e_routing/tests/test_closures.py` (신규):
  ```python
  from datetime import date
  import pytest
  from module_e_routing import closures, isolation as iso
  from module_e_routing.tests.conftest import A, B, box, LAT

  LINE_E2 = {"type": "LineString", "coordinates": [list(A), list(B)]}


  def closure(**props):
      base = {"id": "c1", "reason": "송경천 복구 공사", "start": "2026-09-01", "end": None, "source": "현장조사"}
      return {"type": "Feature", "geometry": LINE_E2, "properties": {**base, "link_ids": ["e2"], **props}}


  def test_active_on_date():
      fc = [closure(start="2026-09-01", end="2026-12-31")]
      assert closures.active(fc, date(2026, 10, 8)) == fc
      assert closures.active(fc, date(2025, 7, 19)) == []
      assert closures.active([closure(end=None)], date(2030, 1, 1))  # 종료일 없음 = 계속 유효


  def test_line_closure_without_link_ids_is_rejected():
      bad = closure(); bad["properties"].pop("link_ids")
      with pytest.raises(closures.ClosureError):
          closures.validate([bad])


  def test_closure_isolates_village_and_is_reported(toy):
      r = iso.check_isolation(toy["bbox"], toy["shelters"], None, closures=[closure()])
      assert r["isolated_building_count"] == 1
      assert r["closed_roads"]["features"][0]["properties"]["reason"] == "송경천 복구 공사"
      assert r["blocked_roads"]["features"] == []   # 침수로 끊긴 길과 섞지 않는다


  def test_polygon_closure_cuts_intersecting_edges(toy):
      poly = {"type": "Feature", "geometry": box(128.0013, LAT - 0.0001, 128.0017, LAT + 0.0001),
              "properties": {"id": "c2", "reason": "구역 통제", "start": "2026-09-01", "end": None, "source": "군청"}}
      r = iso.check_isolation(toy["bbox"], toy["shelters"], None, closures=[poly])
      assert r["isolated_building_count"] == 1
  ```
- [x] **구현** — `module_e_routing/closures.py` (신규):
  ```python
  """복구·통제 구간 — data/road_closures.geojson.

  선 통제는 link_ids(표준노드링크 ID)를 반드시 같이 적는다. 선 기하만으로 교차 검사하면
  교차로에서 다른 도로까지 끊기기 때문이다. 면 통제(Polygon)는 그 안의 도로를 모두 끊는다.
  """
  from __future__ import annotations

  import json
  from datetime import date
  from pathlib import Path

  CLOSURES_PATH = Path(__file__).resolve().parent.parent / "data" / "road_closures.geojson"
  REQUIRED = ("id", "reason", "start", "source")


  class ClosureError(ValueError):
      pass


  def validate(features: list[dict]) -> list[dict]:
      for f in features:
          p = f.get("properties") or {}
          missing = [k for k in REQUIRED if not p.get(k)]
          if missing:
              raise ClosureError(f"통제 구간 {p.get('id')}: 필수 속성 없음 {missing}")
          gtype = (f.get("geometry") or {}).get("type")
          if gtype in ("LineString", "MultiLineString") and not p.get("link_ids"):
              raise ClosureError(f"통제 구간 {p['id']}: 선 통제에는 link_ids가 필요하다")
          if gtype not in ("LineString", "MultiLineString", "Polygon", "MultiPolygon"):
              raise ClosureError(f"통제 구간 {p['id']}: 지원하지 않는 기하 {gtype}")
      return features


  def load(path: Path = CLOSURES_PATH) -> list[dict]:
      if not path.exists():
          return []
      return validate(json.loads(path.read_text(encoding="utf-8")).get("features", []))


  def active(features: list[dict], on: date) -> list[dict]:
      out = []
      for f in features:
          p = f["properties"]
          start = date.fromisoformat(p["start"])
          end = date.fromisoformat(p["end"]) if p.get("end") else None
          if start <= on and (end is None or on <= end):
              out.append(f)
      return out
  ```
- [x] **구현** — `isolation.check_isolation(..., closures: list[dict] | None = None)`.
  - `link_ids`에 든 링크의 엣지와, Polygon 통제와 교차하는 엣지를 `closed_edges`로 모아 `evaluate`에 넘긴다.
  - 출력 키 `"closed_roads"`: LineString FC, 속성 `{kind: "closed_road", closure_id, reason, link_id, road_name}`.
  - 기준 도달성(baseline)은 통제 적용 **전** 그래프로 계산한다. 그래야 통제 때문에 고립된 건물이 "원래 끊겨 있던 건물"로 숨지 않는다(Phase 3 `evaluate` 코드가 이미 그렇게 한다).
  - 경고: `"통제 구간 N곳 반영(사유: …)"`.
- [x] **빈 통제 파일** — `data/road_closures.geojson` (신규): `{"type": "FeatureCollection", "features": []}`. 형식은 `module_e_routing/README.md`에 적는다.
- [x] **API** — `api_server.py`:
  - `GET /road-closures?on=YYYY-MM-DD`: 기본값은 오늘(KST). `closures.active(closures.load(), on)` FC를 돌려준다.
  - `/isolation-check`(`:1201-1217`): `closures=closures.active(closures.load(), _today_kst())`를 넘긴다.
  - `/evacuation-route`(`:1108-1140`): `_apply_closures_to_route(r, active_closures, warnings)`를 추가한다.
    ```python
    def _apply_closures_to_route(result: dict, closure_features: list, warnings: list) -> None:
        """경로가 통제 구간을 20m 넘게 따라가면 통과로 본다. 교차로에서 스치는 건 무시한다."""
        import math
        import shapely.geometry as sg
        result["route_closed"] = False
        result["closed_route_m"] = 0
        coords = result.get("route_lonlat") or []
        if len(coords) < 2 or not closure_features:
            return
        line = sg.LineString(coords)
        mid_lat = coords[len(coords) // 2][1]
        m_per_deg = 111320.0 * math.cos(math.radians(mid_lat))
        for f in closure_features:
            zone = sg.shape(f["geometry"]).buffer(8.0 / m_per_deg)   # 도로 중심선 디지타이징 오차 8m
            overlap_m = line.intersection(zone).length * m_per_deg
            if overlap_m > 20.0:
                result["route_closed"] = True
                result["closed_route_m"] = max(result["closed_route_m"], round(overlap_m))
                result["time_feasible"] = False
                result["time_margin_min"] = None
                warnings.append(f"{result['shelter_id']} 경로가 통제 구간을 지남 — {f['properties']['reason']}")
    ```
  - **테스트** — `tests/test_closure_route.py` (신규). 통제 구간 위를 30m 따라가는 경로는 `route_closed=True`, 교차로에서 직각으로 스치는 경로는 `False`인지 확인한다(`tests/test_flood_route.py` 패턴).
- [x] **저장본** — `build_isolation`(`scripts/build_demo_snapshot.py:372`)은 사건일(2025-07-19)에 유효한 통제만 넘긴다: `closures=active(load(), date(2025, 7, 19))`. 현재 파일이 비어 있어 결과는 같다.
- [x] 실행: `python -m pytest module_e_routing/tests tests/test_closure_route.py tests/test_flood_route.py -q` → 통과.
- [x] 커밋: `Let road closures cut the network and flag routes through them`

**Dependencies:** Phase 3

---

### Phase 5: 진입로 단절 시각과 대피 시한

**Objective:** 시간별 위험(침수 + 도달한 산사태 위험영역)으로 고립을 다시 판정해, 첨두를 포함하는 고립 구간이 시작된 시각과 대피 시한을 군집마다 낸다.

**정의**
- 기준 시각 = 프레임 중 수위강하가 가장 작은(침수가 가장 넓은) 시각.
- 건물의 단절 시각 = 기준 시각에 고립된 건물에 대해, 기준 시각부터 거꾸로 거슬러 올라가며 계속 고립 상태였던 구간의 첫 시각.
- 그 구간이 자료가 있는 첫 시각까지 이어지면 `cut_before_window=True`로 둔다(창 시작 전부터 끊긴 상태).
- 군집 단절 시각 = 군집 구성 건물의 단절 시각 중 가장 이른 값(보수적).
- 대피 시한 = 군집 단절 시각 − `evacuate_lead_before_cut_hours`.

**Tasks:**
- [x] **실패하는 테스트** — `module_e_routing/tests/test_isolation_timeline.py` (신규):
  ```python
  from module_e_routing import isolation as iso
  from module_e_routing.tests.conftest import HAZARD_E2


  def run(toy, hazards, ref):
      return iso.isolation_timeline(toy["bbox"], toy["shelters"], hazards, reference_hour=ref)


  def test_cut_hour_is_start_of_episode(toy):
      t = run(toy, {2: None, 3: HAZARD_E2, 4: HAZARD_E2}, ref=4)
      c = t["clusters"][0]
      assert (c["cut_hour"], c["cut_before_window"]) == (3, False)
      assert t["isolated_count_by_hour"] == {2: 0, 3: 1, 4: 1}


  def test_reconnection_resets_episode(toy):
      t = run(toy, {2: HAZARD_E2, 3: None, 4: HAZARD_E2}, ref=4)
      assert t["clusters"][0]["cut_hour"] == 4      # 2시의 단절은 다른 구간이다


  def test_cut_since_window_start(toy):
      t = run(toy, {2: HAZARD_E2, 3: HAZARD_E2}, ref=3)
      c = t["clusters"][0]
      assert (c["cut_hour"], c["cut_before_window"]) == (2, True)


  def test_reference_hour_matches_static_check(toy):
      t = run(toy, {2: None, 3: HAZARD_E2}, ref=3)
      static = iso.check_isolation(toy["bbox"], toy["shelters"], HAZARD_E2)
      assert t["isolated_count_by_hour"][3] == static["isolated_building_count"]
  ```
- [x] **구현** — `module_e_routing/isolation.py`:
  ```python
  def isolation_timeline(bbox, shelters, hazards_by_hour: dict[int, dict | None], reference_hour: int,
                         closures: list[dict] | None = None) -> dict:
      """시각별 위험으로 고립을 다시 판정해 군집별 진입로 단절 시각을 낸다.

      그래프·건물 매핑은 한 번만 만든다(build_context) — 시각마다 다시 만들면 군 전체에서
      시각당 8초가 걸린다. 반환: {hours, reference_hour, isolated_count_by_hour,
      clusters: [{geometry, building_count, centroid, bbox, cut_hour, cut_before_window}]}.
      """
      ctx = build_context(fetch_roads(bbox), fetch_buildings(bbox))
      closed = closed_edges_for(ctx, closures or [])
      hours = sorted(hazards_by_hour)
      flags: dict[int, set[int]] = {}
      for h in hours:
          ev = evaluate(ctx, shelters, hazard_shape(hazards_by_hour[h]), closed)
          flags[h] = set(ev["isolated_idx"]) | set(ev["direct_idx"])
      ref_set = flags[reference_hour]
      ref_pos = hours.index(reference_hour)
      cut_of: dict[int, tuple[int, bool]] = {}
      for k in ref_set:
          p = ref_pos
          while p - 1 >= 0 and k in flags[hours[p - 1]]:
              p -= 1
          cut_of[k] = (hours[p], p == 0)
      idx = sorted(ref_set)
      points = [(float(ctx.centroids[k][0]), float(ctx.centroids[k][1])) for k in idx]
      by_point = {points[i]: idx[i] for i in range(len(idx))}
      clusters = []
      for c in cluster_isolated_buildings(points):
          members = [by_point[p] for p in c["member_points"]]
          first = min(members, key=lambda k: cut_of[k][0])
          clusters.append({"geometry": c["geometry"], "building_count": c["building_count"],
                           "centroid": c["centroid"], "bbox": c["bbox"],
                           "cut_hour": cut_of[first][0], "cut_before_window": cut_of[first][1]})
      return {"hours": hours, "reference_hour": reference_hour,
              "isolated_count_by_hour": {h: len(flags[h]) for h in hours}, "clusters": clusters}
  ```
  `closed_edges_for(ctx, closures)`는 Phase 4에서 `check_isolation` 안에 넣은 통제 엣지 수집 코드를 함수로 빼낸 것이다. 두 곳이 같은 함수를 쓴다.
- [x] **저장본** — `scripts/build_demo_snapshot.py`에 `build_isolation_timing(frames, flood_series, risk_display, verbose)`를 추가하고, `build()`(`:208` 다음)에서 호출한다.
  ```python
  def build_isolation_timing(frames, flood_series, risk_display, verbose=True) -> dict:
      """시각별 위험(그 시각의 침수 + 그때까지 도달한 산사태 위험영역)으로 고립을 다시 판정한다.
      화면의 시각별 고립 판정(MapExplorer scheduleIsolationCheck)과 같은 위험 정의를 쓴다."""
      from datetime import datetime, timedelta
      from module_e_routing import isolation as iso, policy
      if not flood_series.get("available"):
          return {"available": False, "reason": "시간별 침수 없음"}
      pol = policy.load()
      lead = float(pol.value("evacuate_lead_before_cut_hours"))
      dmin = float(pol.value("flood_impassable_depth_m"))
      drops = flood_series["stage_drop_by_hour"]
      contours = flood_series["contours"]["features"]
      levels = sorted({float(f["properties"]["level_m"]) for f in contours})
      info = _read_demo_regions()["sancheong_all"]
      hazards, time_of = {}, {}
      for fr in frames:
          h = fr["hour"]
          if str(h) not in drops:
              continue                       # 수위 자료 없는 시각은 판정하지 않는다
          need = drops[str(h)] + dmin
          lvl = next((x for x in levels if x >= need - 1e-9), None)
          parts = [f["geometry"] for f in contours if lvl is not None and abs(float(f["properties"]["level_m"]) - lvl) < 1e-9]
          parts += [f["geometry"] for f in risk_display["features"]
                    if f["properties"].get("arrival_hour") is not None and f["properties"]["arrival_hour"] <= h]
          hazards[h] = {"type": "FeatureCollection",
                        "features": [{"type": "Feature", "geometry": g, "properties": {}} for g in parts]} if parts else None
          time_of[h] = fr["time"]
      ref = min(hazards, key=lambda h: drops[str(h)])
      t0 = time.perf_counter()
      tl = iso.isolation_timeline(info["bbox"], info["shelters"], hazards, reference_hour=ref)
      feats = []
      for i, c in enumerate(tl["clusters"]):
          cut = datetime.fromisoformat(time_of[c["cut_hour"]])
          feats.append({"type": "Feature", "geometry": c["geometry"], "properties": {
              "cluster_id": i, "building_count": c["building_count"], "centroid": list(c["centroid"]),
              "cut_time": cut.isoformat(), "evacuate_by": (cut - timedelta(hours=lead)).isoformat(),
              "cut_before_window": c["cut_before_window"]}})
      real = [f["properties"]["evacuate_by"] for f in feats if not f["properties"]["cut_before_window"]]
      if verbose:
          print(f"  고립 시각 판정 {len(hazards)}시각 · 군집 {len(feats)} · {time.perf_counter() - t0:.1f}s")
      return {"available": True, "region": "sancheong_all", "reference_time": time_of[ref],
              "lead_hours": lead, "lead_policy": "module_e_v1/evacuate_lead_before_cut_hours",
              "clusters": {"type": "FeatureCollection", "features": feats},
              "isolated_by_time": {time_of[h]: n for h, n in tl["isolated_count_by_hour"].items()},
              "earliest_evacuate_by": min(real) if real else None,
              "한계": [
                  "시각별 침수는 최대침수심에서 경호교 수위강하를 뺀 준정적 근사다 — 단절 시각도 근사다.",
                  "하천 본류는 최저 수위에도 침수로 잡혀, 본류를 건너는 교량은 늘 끊긴 것으로 처리된다(상판 높이 자료 없음).",
                  "사후 재현에서 계산한 시각이다. 실시간 경보에는 아직 쓰지 않는다.",
                  "마을안길은 도로망에 없어, 그 길로만 드나드는 마을은 가장 가까운 시·군도 기준으로 판정된다.",
              ]}
  ```
  `build()`의 반환 dict에 `"isolation_timing": isolation_timing`을 추가한다.
- [x] **UI 사본** — `write_ui_copies`(`:283-286`)의 `timeline.json`에 `"isolation_timing"`을 추가하고, `markers`에 `"isolation_deadline": snapshot["isolation_timing"].get("earliest_evacuate_by")`를 추가한다.
- [x] **API** — `/alerts/{id}/timeline`(`api_server.py:229-344`)이 저장본의 `isolation_timing`과 `markers.isolation_deadline`을 돌려주게 한다(경보가 저장본과 같은 id일 때만).
- [x] **저장본 테스트** — `tests/test_demo_snapshot.py`에 추가:
  ```python
  def test_isolation_deadline_is_lead_before_cut(snapshot: dict) -> None:
      from datetime import datetime, timedelta
      t = snapshot["isolation_timing"]
      assert t["available"] and t["lead_hours"] == 1.0
      for f in t["clusters"]["features"]:
          p = f["properties"]
          gap = datetime.fromisoformat(p["cut_time"]) - datetime.fromisoformat(p["evacuate_by"])
          assert gap == timedelta(hours=t["lead_hours"])
      assert t["reference_time"] in {fr["time"] for fr in snapshot["frames"]}
  ```
- [x] 실행: `python -m pytest module_e_routing/tests/test_isolation_timeline.py -q` → 통과. 저장본 테스트는 Phase 8에서 저장본을 다시 만든 뒤 통과한다.
- [x] 커밋: `Work out when each village's road closes, and warn an hour before`


> **구현 중 변경 (2026-10-08)** — 실데이터로 돌려 보니 원래 정의(`cut_before_window`)로는 하천 본류를 건너는
> 길처럼 "늘 끊긴" 곳이 7/18 새벽에 끊긴 것으로 잡혀, 가장 이른 대피 시한이 탐지보다 31시간 앞섰다.
> 그래서 다음처럼 바꿨다.
> - `isolation_timeline(..., low_water_hour=)` 인자를 추가했다. 단절 구간이 저수위 시각까지 이어지면 `persistent=True`로 두고, 대피 시한을 매기지 않는다.
> - 저수위 시각 = 앞선 수위 정점 이후, 기준 시각 전까지 수위가 가장 낮은 시각(홍수 사이의 골)이다. 창에서 가장 낮은 시각(7/18 02:00)은 구간 모형이 빈 하도에서 시작하는 초기화 구간이라 쓰지 않는다.
> - 결과: 저수위 7/19 01:00, 늘 끊김 9곳(493동), 이번 홍수로 끊김 56곳(1,841동). 단절은 7/19 04:00~13:00이고, 13곳(915동)은 대피 시한이 경보 발송(09:05)보다 이르다.

**Dependencies:** Phase 1, 3, 4

---

### Phase 6: 침수 모형 영역 레지스트리 · 계산 범위 · 덕천강 스크립트

**Objective:** 여러 침수 모형 영역을 받을 수 있게 하고, 계산 범위와 범위 밖을 저장본·API·결과에 싣는다. 덕천강 모형 구축 스크립트를 준비한다.

**Tasks:**
- [x] **실패하는 테스트** — `tests/test_flood_domains.py` (신규):
  ```python
  import pytest
  from shapely.geometry import box
  from module_b_flood import domains


  def test_registry_lists_both_domains():
      ds = {d.id: d for d in domains.load_domains()}
      assert ds["gyeongho_reach"].available
      assert ds["gyeongho_reach"].stage_series["gauge"] == "경호교"
      assert "deokcheon_upper" in ds


  def test_gyeongho_footprint_is_model_grid():
      d = next(d for d in domains.load_domains() if d.id == "gyeongho_reach")
      assert domains.footprint_5179(d) == pytest.approx((1028000, 1703000, 1042000, 1723000))


  def test_coverage_splits_county():
      county = box(1020000, 1700000, 1050000, 1730000)
      cov = domains.coverage(county)
      assert cov["covered"].area + cov["uncovered"].area == pytest.approx(county.area)
      assert cov["covered"].area == pytest.approx(14000 * 20000)


  def test_sancheong_coverage_is_about_a_third():
      cov = domains.coverage(domains.county_5179("38570"))
      assert 0.30 < cov["covered_ratio"] < 0.40
  ```
- [x] **레지스트리** — `module_b_flood/domains.json` (신규):
  ```json
  {"version": 1,
   "domains": [
     {"id": "gyeongho_reach", "name": "경호강 구간 (고읍교~수산교)", "status": "computed",
      "raster": "module_b_flood/data/sfincs_maxdepth_50m.tif",
      "stage_series": {"gauge": "경호교", "csv": "module_b_flood/data/sfincs_reach_wse.csv"},
      "footprint_5179": null, "built_by": "module_b_flood/scripts/33_sfincs_build_reach.py",
      "note": "유입 고읍교 유량 · 하류 수산교 수위 경계."},
     {"id": "deokcheon_upper", "name": "덕천강 상류 (시천·삼장)", "status": "planned",
      "raster": "module_b_flood/data/sfincs_deokcheon_maxdepth_50m.tif",
      "stage_series": null, "footprint_5179": null,
      "built_by": "module_b_flood/scripts/33d_sfincs_build_deokcheon.py",
      "note": "G: 드라이브 입력으로 실행 후 래스터가 생기면 자동 반영. 수위 관측소가 없어 최대 범위만 표시한다."}
   ]}
  ```
  `footprint_5179`이 null이면 래스터 경계를 쓰고, 래스터가 없으면 33d 스크립트가 계산한 격자를 쓴다. 33d 실행 전에는 `domains.json`에 격자를 적어 둔다(아래 dry-run 출력값).
- [x] **로더** — `module_b_flood/domains.py` (신규):
  ```python
  """침수 모형 영역 레지스트리. 래스터가 있는 영역만 '계산됨'으로 본다."""
  from __future__ import annotations
  import json
  from dataclasses import dataclass
  from pathlib import Path

  REPO = Path(__file__).resolve().parents[1]
  REGISTRY = Path(__file__).resolve().parent / "domains.json"


  @dataclass(frozen=True)
  class Domain:
      id: str
      name: str
      status: str
      raster: Path
      stage_series: dict | None
      footprint: tuple | None
      built_by: str
      note: str

      @property
      def available(self) -> bool:
          return self.raster.exists()


  def load_domains() -> list[Domain]:
      doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
      return [Domain(d["id"], d["name"], d["status"], REPO / d["raster"], d.get("stage_series"),
                     tuple(d["footprint_5179"]) if d.get("footprint_5179") else None, d["built_by"], d["note"])
              for d in doc["domains"]]


  def footprint_5179(d: Domain) -> tuple | None:
      if d.available:
          import rasterio
          with rasterio.open(d.raster) as ds:
              b = ds.bounds
              return (b.left, b.bottom, b.right, b.top)
      return d.footprint


  def county_5179(code: str):
      from shapely.geometry import shape
      fc = json.loads((REPO / "data/vector/adm_sigungu_5179.geojson").read_text(encoding="utf-8"))
      return next(shape(f["geometry"]) for f in fc["features"] if f["properties"].get("code") == code)


  def coverage(county) -> dict:
      from shapely.geometry import box
      from shapely.ops import unary_union
      parts = [box(*footprint_5179(d)) for d in load_domains() if d.available]
      covered = unary_union(parts).intersection(county) if parts else county.difference(county)
      return {"covered": covered, "uncovered": county.difference(covered),
              "covered_ratio": covered.area / county.area if county.area else 0.0,
              "domains": [{"id": d.id, "name": d.name, "available": d.available, "status": d.status,
                           "footprint_5179": footprint_5179(d)} for d in load_domains()]}
  ```
  `adm_sigungu_5179.geojson`의 산청군 피처는 `properties.code == "38570"`이다(확인함).
- [x] **저장본 다중 영역** — `scripts/build_demo_snapshot.py:100-176`:
  - `flood_depth_raster(aoi)` 대신 `[d for d in domains.load_domains() if d.available]`를 순회한다.
  - 영역마다 `flood_display_featurecollection` 결과를 이어 붙이고, 각 피처 속성에 `"domain": d.id`를 넣는다.
  - `stage_series`가 있는 영역이 2개 이상이면 `RuntimeError("시간축 침수는 영역 1개만 지원 — domains.json 확인")`를 낸다. 1개면 그 영역으로 기존 `flood_series`를 만든다(`wse_csv = REPO_ROOT / d.stage_series["csv"]`).
  - 시간축이 없는 영역의 band 0 피처는 `flood_static` FC로 따로 모으고, 속성에 `"time_varying": False`를 넣는다.
  - `flood_series`에 `"impassable_depth_m": policy.value("flood_impassable_depth_m")`를 추가한다.
- [x] `_flood_hazard`(`:361-369`): band 0 피처 **전부**의 합집합으로 바꾼다.
  ```python
  feats = [f for f in (flood_display or {}).get("features", []) if (f.get("properties") or {}).get("band") == 0]
  if not feats:
      return None
  if len(feats) == 1:
      return feats[0]["geometry"]                      # 영역 1개면 기존과 같다 — 고립 2,445동 유지
  from shapely.geometry import mapping, shape
  from shapely.ops import unary_union
  return mapping(unary_union([shape(f["geometry"]) for f in feats]))
  ```
- [x] 저장본 `flood_coverage` 키를 추가한다. `domains.coverage(domains.county_5179("38570"))`의 `covered`/`uncovered`/각 영역 footprint를 lon/lat로 변환해 넣는다(`geo.featurecollection_5179_to_lonlat` 사용). `timeline.json`에도 `"flood_coverage"`, `"flood_static"`을 넣는다.
- [x] **API** — `api_server.py`:
  - `_sancheong_flood_shape`(`:1146-1166`): band 0 피처 전부의 합집합.
  - `_flood_covered_shape()`: 저장본 `flood_coverage.covered`를 캐시로 읽는다.
  - `/evacuation-route`: 결과마다 `r["in_flood_coverage"] = bool(covered and covered.contains(Point(*shelter_lonlat)))`를 넣는다. 범위 밖이면 경고 `"{id}: 침수 계산 범위 밖 — 침수 여부를 판정하지 않았다"`를 추가한다.
  - `/alerts/{id}/timeline`: `flood_coverage`, `flood_static`을 돌려준다.
  - **테스트** — `tests/test_flood_route.py`에 추가. 범위 밖 대피소는 `in_flood_coverage=False`와 경고 1개, 범위 안 대피소는 `True`인지 확인한다(합성 box 사용).
- [x] **고립 경고** — `build_isolation`의 `sancheong_all:flood` 결과 `warnings`에 `"침수 반영 고립은 침수 계산 범위(산청군의 약 N%) 안에서만 판정한다"`를 덧붙인다. N은 `covered_ratio`에서 계산한 값이다.
- [x] **덕천강 스크립트** — `module_b_flood/scripts/33d_sfincs_build_deokcheon.py` (신규). 25번(강우 강제)과 33번(격자·한글경로 우회)을 합친 구성이다.
  - 영역: `data/vector/adm_dong_5179.geojson`의 시천면 ∪ 삼장면 경계 박스에 1km 여유를 두고 50m로 맞춘다.
  - 지형: `G:/연구/공모전/아쿠아가드/data/dem/산청_dem_5m_5179.tif`.
  - 조도: `data/hydro/sancheong_manning_5m_5179.tif`.
  - 강제: `data/hydro/sfincs_precip_basinmean.csv`.
  - 경계: `setup_mask_bounds(btype="outflow", zmax=120)`.
  - 기간: 2025-07-18 00:00 ~ 07-21 00:00. subgrid는 10.
  - 빌드 폴더: 환경변수 `AQUAGUARD_SFINCS_ROOT`(ASCII 경로). netCDF 한글경로 버그를 피하기 위해서다.
  - `--dry-run`: hydromt를 import하지 않고 격자(x0, y0, mmax, nmax)와 입력 파일 존재 여부만 출력하고 0으로 끝낸다.
  - `--postprocess <sfincs_map.nc>`: `zsmax - zb`를 `module_b_flood/data/sfincs_deokcheon_maxdepth_50m.tif`(nodata=0, EPSG:5179)로 쓴다. `34b_sfincs_postprocess.py:20-30`과 같은 flipud·transform 규칙을 쓴다.
  - **테스트** — `tests/test_flood_domains.py`에 추가:
    ```python
    def test_deokcheon_build_script_dry_run():
        import subprocess, sys
        r = subprocess.run([sys.executable, "module_b_flood/scripts/33d_sfincs_build_deokcheon.py", "--dry-run"],
                           capture_output=True, text=True, encoding="utf-8", cwd=domains.REPO)
        assert r.returncode == 0, r.stderr
        assert "격자" in r.stdout
    ```
  - dry-run이 출력한 격자 경계를 `domains.json`의 `deokcheon_upper.footprint_5179`에 적는다. 그래야 실행 전에도 "계산 예정 범위"를 지도에 표시할 수 있다.
- [x] 실행: `python -m pytest tests/test_flood_domains.py tests/test_flood_route.py -q` → 통과.
- [x] 커밋: `Know which ground the flood model covered, and make room for 덕천강`

> **구현 중 변경 (2026-10-08)** — 덕천강 격자(시천·삼장 + 1km)가 경호강 격자와 일부 겹친다. 그래서
> `domains.json`의 순서를 우선순위로 쓴다. 겹친 곳에서는 앞 영역(수위계로 검증된 경호강) 결과만 남기고,
> 뒤 영역의 표시 폴리곤은 앞 영역 사각형 밖으로 잘라낸다. 저장본은 7단계 화면 작업에 새 키가 필요해서 이 단계에서 다시 만들었다.

**Dependencies:** Phase 1

---

### Phase 7: 화면

**Objective:** Phase 3~6의 산출을 지도·패널·스크러버에 표시한다.

**Tasks:**
- [x] **타입** — `ui/src/lib/api.ts`:
  - `AlertTimeline`(`:220`)에 추가:
    - `flood_coverage?: { covered: GeoJSON.Geometry; uncovered: GeoJSON.Geometry; covered_ratio: number; domains: { id: string; name: string; available: boolean; status: string; footprint?: GeoJSON.Polygon }[] }`
    - `flood_static?: GeoJSON.FeatureCollection`
    - `isolation_timing?: { available: boolean; reference_time?: string; lead_hours?: number; clusters?: GeoJSON.FeatureCollection; earliest_evacuate_by?: string | null; 한계?: string[] }`
    - `markers.isolation_deadline?: string | null`
  - `flood_series`에 `impassable_depth_m?: number`를 추가한다.
  - `getAlertTimeline`(`:277-305`)의 정적 경로에서 새 키를 그대로 복사한다.
  - `IsolationCheckResult`(`:358`)에 `closed_roads?`, `rescue_limited_buildings?`, `rescue_limited_count?`를 추가한다.
  - `EvacuationRouteResult`(`:329`)에 `route_closed?`, `closed_route_m?`, `in_flood_coverage?`를 추가한다.
  - 신규 `getRoadClosures(): Promise<GeoJSON.FeatureCollection>`(`GET /road-closures`, 실패하면 빈 FC).
- [x] **지도** — `ui/src/components/MapExplorer.tsx`:
  - `floodAtFrame`(`:1593-1604`): `+ 0.3`을 `+ (floodSeries?.impassable_depth_m ?? 0.3)`로 바꾸고, `timeline.flood_static.features`를 항상 이어 붙인다.
  - 신규 소스 `flood-uncovered`: 레이어 `flood-uncovered-fill`(회색 `#64748b`, opacity 0.28)과 `flood-uncovered-line`(점선)을 둔다. `hasHazardAoi`일 때 `timeline.flood_coverage.uncovered`로 채운다. 가리키면 `"침수 계산 범위 밖 — 침수가 없다는 뜻이 아니라 계산하지 않은 곳"` 팝업을 띄운다.
  - 신규 소스 `closed-roads`: `getRoadClosures()`로 한 번 받는다. `closed-roads-line`(주황 `#f97316`, 점선 [2,1], 폭 4)으로 그리고, 팝업에 `reason` · `start~end`를 보인다.
  - 신규 소스 `isolation-deadline`: `timeline.isolation_timing.clusters`. `isolation-deadline-outline`(마젠타 `#e879f9`, 점선, 폭 3)으로 그린다. 프레임이 바뀔 때마다 `setFilter`로 `evacuate_by ≤ 현재 시각 < cut_time`인 군집만 남긴다. 비교는 각 피처 속성에 넣은 epoch ms(`evacuate_by_ms`, `cut_ms`)로 한다. 이 값은 `getAlertTimeline`에서 계산해 넣는다.
  - `blocked-roads-line` 팝업(`:1401-1405`): 고정 문구 대신 `${road_name ?? "도로"} · ${rd_type_h} · ${rd_rank_h} — 통행 불가`를 보인다. 교량이면 `"(상판 높이 자료 없음 — 침수 범위와 겹치면 통행 불가로 처리)"`를 덧붙인다.
  - 고립 군집 팝업(`showIsolationPopup`, `:1361-1379`): 가리킨 군집 중심이 `isolation_timing` 군집 안에 있으면 `"진입로 단절 예상 HH:MM · HH:MM까지 대피"`를 덧붙인다. 창 시작 전부터 끊긴 경우 `"자료 시작 시각에 이미 단절"`로 쓴다.
  - 범례(`:2011-2124`)에 행 3개를 추가한다.
    - `침수 계산 범위 밖` — 회색 견본. 계산 예정 영역 이름을 함께 쓴다(`domains.filter(d => !d.available)`).
    - `통제 구간` — 주황 점선. 통제 구간이 0개면 `"현재 등록된 통제 구간 없음"`.
    - `대피 시한이 지난 마을` — 마젠타 점선. `"진입로가 끊기기 1시간 전부터 표시"`.
  - 스크러버 마커(`:2291-2298`) 옆에 `🟣 고립 대비 시한 {hhmm(timeline.markers.isolation_deadline)}`를 추가한다. 값이 없으면 숨긴다.
- [x] **고립마을 패널** — `ui/src/components/panels/IsolationPanel.tsx`:
  - 침수 반영 시나리오(`:56`, `:110`)에서 군집 목록(`:217-258`) 각 행에 대피 시한을 보인다. 순서: 저장본 결과 군집과 `isolation_timing` 군집을 중심점 포함으로 짝짓는다.
  - 목록 위에 요약 한 줄: `"통상 경보(HH:MM)보다 먼저 대피해야 하는 마을 N곳"`. `evacuate_by < markers.alert_sent`인 군집 수다.
  - `rescue_limited_count > 0`이면 `"구조차량 진입 곤란 N동"` 줄을 보인다.
  - `closed_roads`가 있으면 `"통제 구간 반영"` 줄을 보인다.
- [x] **대피소 찾기 패널** — `ui/src/components/panels/EvacuationPanel.tsx`:
  - `:100`의 `.then(({ results }) =>`를 `.then(({ results, warnings }) =>`로 바꾸고, 결과 목록 아래에 `warnings`를 `IsolationPanel.tsx:224-229`와 같은 형식(`⚠ {w}`)으로 보인다.
  - 행 배지(`:298-302` 근처)에 `route_closed` → `"통제 구간 통과"`, `in_flood_coverage === false` → `"침수 판정 범위 밖"`을 추가한다.
- [x] 실행: `cd ui && npx tsc --noEmit` → 오류 0. `npx eslint src` → 기존 1건(`MapExplorer.tsx:536` set-state-in-effect) 외 새 오류 0.
- [x] 커밋: `Show the uncomputed ground, closures, and each village's deadline`

> **구현 중 변경 (2026-10-08)**
> - 계산 범위 밖 회색 영역에는 팝업을 달지 않았다. 군의 절반 이상을 덮는 면이라, 커서를 움직일 때마다 팝업이 계속 떠서 방해가 된다. 설명은 범례에서 한다.
> - 고립마을 패널은 시간축을 따로 받지 않는다. `MapExplorer`가 받은 시간축을 `page.tsx`가 끌어올려 넘긴다(1.5MB를 두 번 받지 않기 위해서다).
> - 통제 구간 조회는 지도 준비와 묶지 않았다. WebGL이 없어 지도가 안 떠도 범례가 통제 구간 유무를 맞게 말한다.
> - 디자인 점검 도구(`impeccable detect`) 결과 0건.

**Dependencies:** Phase 4, 5, 6

---

### Phase 8: 저장본 재생성 · 문서 · 전체 검증

**Tasks:**
- [x] `python scripts/build_demo_snapshot.py` — 네이버 키와 VWorld 캐시가 필요하다. 출력에서 다음을 확인한다.
  - `고립 sancheong_all:flood 고립건물 2445동`
  - `고립 시각 판정 37시각`
- [x] `python -m pytest -q` → 전부 통과. 기존 563개와 새 테스트를 모두 포함한다.
- [x] 문서:
  - `module_e_routing/README.md`: 정책 파일, 통제 구간 형식, 현장 보정 형식, `isolation_timeline`, 구조차량 판정의 한계(폭 정보 없음, 마을안길 없음, 이륜차 값의 의미). 도보 설명도 갱신한다(`:36-37`가 낡았다 — 도보는 네이버 경로 길이 ÷ 4km/h).
  - `module_b_flood/README.md`: `domains.json`, 33d 실행 순서(G: PC). 순서: `--dry-run` → 빌드 → `sfincs.exe` → `--postprocess` → 래스터 복사 → `domains.json` status를 computed로 → 저장본 재생성.
- [ ] 커밋 후 푸시. EC2는 `git fetch` + `reset --hard origin/main` + 재시작. 새 엔드포인트 `/road-closures`가 `/health` routes에 보이는지 확인한다. Vercel은 자동 배포된다.

**Dependencies:** Phase 1~7

## Success Criteria

### Automated Verification
- [x] `python -m pytest -q` → 실패 0.
- [x] `python -m pytest module_e_routing/tests/test_isolation_regression.py -q` → 통과(캐시가 있을 때). 2,445동 유지.
- [x] `python -m pytest tests/test_demo_snapshot.py -q` → 통과. 봉투가 실시간 재실행과 일치하고, 대피 시한 = 단절 − 1h이다.
- [x] `python module_b_flood/scripts/33d_sfincs_build_deokcheon.py --dry-run` → 종료코드 0.
- [x] `python -c "import json;d=json.load(open('ui/public/demo/timeline.json',encoding='utf-8'));assert d['isolation_timing']['available'] and d['flood_coverage']['covered'] and 'isolation_deadline' in d['markers']"` → 오류 없음.
- [x] `cd ui && npx tsc --noEmit` → 오류 0.
- [x] `cd ui && npx eslint src` → 새 오류 0.
- [x] 로컬 API: `GET /road-closures` 200 + FeatureCollection. `POST /evacuation-route` 응답의 결과마다 `in_flood_coverage`, `route_closed` 키가 있다.

### Manual Verification
- [ ] 지도에서 산청군의 침수 계산 범위 밖이 회색으로 덮이고, 범례에 "덕천강 상류(시천·삼장): 계산 예정"이 보인다.
- [ ] 스크러버를 7/19 오전에서 첨두 쪽으로 옮기면, 대피 시한이 지났지만 아직 안 끊긴 마을이 마젠타 점선으로 나타났다가, 끊기면 고립 표시로 바뀐다.
- [ ] 스크러버에 "고립 대비 시한" 마커가 보인다.
- [ ] 끊긴 도로를 가리키면 도로명·교량 여부가 나온다.
- [ ] 고립마을 패널(침수 반영)에 군집별 대피 시한과 "통상 경보보다 먼저 대피해야 하는 마을 N곳"이 보인다.
- [ ] 대피소 찾기에서 범위 밖 대피소에 "침수 판정 범위 밖" 배지가, 서버 경고가 목록 아래에 보인다.
- [ ] `data/road_closures.geojson`에 시험용 통제 1건을 넣고 API를 재시작하면, 지도에 주황 점선이 그려지고 고립마을 패널에 반영된다. 확인 후 시험 항목은 지운다.

※ 이 개발 PC의 브라우저 창은 WebGL이 꺼져 있어 지도 렌더링은 사용자 PC에서 확인한다. 패널·API는 여기서 확인할 수 있다.

## Testing Strategy

**Unit:** 합성 도로·건물(`module_e_routing/tests/conftest.py`)로 고립 문맥·구조차량·통제·시간별 단절을 검증한다. 합성 FC/Feature/Polygon으로 위험영역 대피소 제외를 검증한다. 합성 county box로 계산 범위 분할을 검증한다.

**Integration:** 실제 VWorld 캐시로 2,445동을 회귀 검증한다(캐시 없으면 건너뜀). 저장본과 실시간 재실행 봉투를 대조하는 기존 테스트를 유지한다. 대피 시한 = 단절 − 1h 일관성도 검증한다.

**Manual:** 위 Manual Verification.

## References
- 현장조사 절: `C:\Users\user\Desktop\하수범_공모전\Aquaguard.AI\아쿠아가드_현장조사.docx`
- `module_e_routing/isolation.py`, `module_e_routing/__init__.py`, `module_e_routing/tests/test_blocked_roads.py`
- `api_server.py:1100-1217`, `:229-344`
- `scripts/build_demo_snapshot.py:62-412`
- `module_o_orchestrator/exposure_layers.py:50-83`, `:479-494`
- `module_b_flood/scripts/25_sfincs_build.py`, `33_sfincs_build_reach.py`, `34b_sfincs_postprocess.py`
- `module_d_exposure_overlay/policy.py:74-96`, `policies/policy.schema.json`
- `ui/src/components/MapExplorer.tsx`, `ui/src/components/panels/{IsolationPanel,EvacuationPanel}.tsx`, `ui/src/lib/api.ts`
