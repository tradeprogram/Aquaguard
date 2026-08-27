# AquaGuard AI (아쿠아가드)

산불로 훼손된 사면 위에 첫 집중호우가 떨어지는 순간부터, 산사태→하천범람→고립까지 이어지는 **재해연쇄(disaster chain)**를 몇 시간 전에 읽어내고, 관(官)의 의사결정을 기다리지 않고 대피소·경로·피해규모까지 자동으로 계산해 동시에 전파하는 에이전트.

> 이 저장소에서 작업을 시작하는 모든 사람(사람이든 Claude Code 세션이든)은 이 README를 먼저 읽을 것. 더 상세한 전문은 **[ARCHITECTURE.md](ARCHITECTURE.md)**(§0~§14), 원본 PDF(다이어그램 포함)는 [`docs/`](docs/)에 있음. 모듈 계약 원본은 [`contracts/`](contracts/).

---

## 빠른 시작 (트랙③ 프로토타입 — Module O + 대시보드, 전부 목업 모드)

`module_o_orchestrator`가 A~H를 `contracts/`의 example.json으로 목업 호출하고, `ui/`의 Next.js 대시보드가 그 결과를 그린다. 팀원 모듈이 실제로 들어오면 `AQUAGUARD_MOCK_MODE=0`으로 바꾸는 것만으로 실제 모듈 호출로 전환된다(코드 변경 없음, `module_o_orchestrator/modules_client.py` 참조).

```bash
# 1) 백엔드 (FastAPI + Module O)
pip install -r requirements.txt
python -m uvicorn api_server:app --port 8000

# 2) 프론트엔드 (다른 터미널)
cd ui
npm install
npm run dev   # http://localhost:3000

# 3) 테스트
python -m pytest module_o_orchestrator/tests/ -v
```

대시보드(`/`)에서 "산청 시나리오 실행" → 골든타임 카운터·위험 패널이 뜸 → "승인 화면으로"(`/approve`)에서 원클릭 승인/타임아웃 카운트다운 확인 → `/whatif`에서 강수 슬라이더(현재는 목업이라 값 고정, 실모델 연동 시 즉시 반영) → `/map3d`에서 MapLibre+deck.gl 3D 지도(위성영상, 지형, 건물/도로/교량 입체화, 전국 행정동 경계 검색·표시, 골든타임 시간슬라이더).

`/map3d`의 지리 데이터 파이프라인:
- **행정동 경계**(전국, 사용자 제공 `BND_ADM_DONG_PG` 원본 EPSG:5186 → `data/vector/adm_dong_5179.geojson`으로 EPSG:5179 저장·단순화) — `api_server.py`의 `GET /boundaries?bbox=...`가 뷰포트만큼만 EPSG:4326으로 재투영해 내려주고(§4.1: 재투영은 UI 출력 직전에만), `GET /search?q=...`가 `data/vector/adm_dong_index.json`(이름·중심점·bbox 인덱스)에서 시/군/구/읍/면/동 이름으로 검색해 지도 이동에 씀.
- **지형**: `GET /terrain-tiles/{z}/{x}/{y}.png`가 AWS 공개 지형 타일을 프록시(CORS 우회).
- **위성영상**: Esri World Imagery(무료, 키 불필요).
- **건물·도로·교량**: OpenFreeMap 무료 벡터타일(OSM, OpenMapTiles 스키마) — 건물은 `render_height`로 실높이 압출, 교량은 `@turf/buffer`로 폭만큼 버퍼링해 지면에서 띄운 `fill-extrusion`.

새로 추가된 `geopandas`/`pyproj`/`requests` 의존성은 `requirements.txt`에, `@turf/buffer`는 `ui/package.json`에 포함돼 있다.

---

## 1. 왜 만드는가 (배경)

2025년 여름 한반도는 한 시즌 안에 복합재해를 겪었다. 7/16~20 기록적 집중호우(다수 지역 누적 300mm 이상)로 전국 37명 사망, 12,921명 대피, 피해 총 1조 848억원(도로침수 778곳·토사유실 197건·하천시설 붕괴 403건·건축물침수 1,857건·농경지침수 73건).

가장 심각했던 곳은 경남 산청군 — 7/19 하루 동안 산사태 266건, 13명 사망·1명 실종. **진짜 실패 지점은 예측 실패가 아니라 전파 지연**이다: 산림청은 이미 7/17에 대피를 권고했고, 7/19 08:00부터 주민 신고가 빗발쳤는데도 산사태 경보 격상은 12:37 — 이미 있던 신호가 관(官)의 판단·전파 단계에서 **4시간 넘게 샜다.**

또한 우연이 아닌 연결고리가 있다: 같은 산청군은 이 산사태 4개월 전(2025.3) 경남·경북 11개 지역(48,238ha)을 태운 대형 산불의 피해지였다. 산불 피해지는 화재 2년 후까지도 토양유출량이 일반 산림 대비 3~4배 높게 유지된다(나무 뿌리가 토양을 붙잡는 힘, 토양의 빗물 흡수력 모두 상실). 산불이 사면을 훼손해두면 다음 집중호우가 산사태로 이어질 확률이 급증하는 **재해연쇄가 실제로 존재한다.**

### 이 프로젝트가 푸는 문제 두 가지

1. **재해연쇄를 모델링하는 시스템이 없다** — 산불위험·산사태·홍수 예측은 각각 따로 존재(예: KIGAM 물리기반 산사태 모델, 85~90%대 정확도). 하지만 "산불이 할퀸 사면 + 첫 폭우 → 산사태 위험 급증 → 하류 하천범람"이라는 인과 사슬을 하나로 연결해 추적하는 시스템은 없다.
2. **정확한 예측이 있어도 판단·전파 단계에서 시간이 샌다** — 산청이 정확히 그 사례. 그래서 목표는 "더 정확한 예측 모델"이 아니라 **"이미 있는 신호와 실제 대피 사이에서 새는 시간을 자동화로 되찾는 시스템"**이다.

### 아쿠아가드가 하는 일

1. 산불 이력(dNBR)이 산사태 위험을 증폭시키는 계수를 문헌·실측 근거로 정량화 (`f(dNBR, Δt)`, 아래 §4 참조)
2. 강수·토양수분·지형·화재이력·지반변위(InSAR)를 실시간 감시해 산사태·하천범람 위험 예측 (Module A/B)
3. 위험이 임계치를 넘는 순간 사람의 판단을 기다리지 않고 대피소·경로·피해비용까지 자동 계산 (Module D/E/G)
4. 결과를 관(지자체 재난상황실)과 시민에게 동시 전파 (Module O — 골든타임 상태머신)
5. 산청 실제 타임라인(신고 08:00, 경보 12:37)과 이 시스템이 있었다면 나왔을 타임라인을 비교해 "몇 시간 몇 분을 벌 수 있었는가"를 숫자로 증명 (데모 시나리오, §8)

### 공모전 트랙

아이디어/프로토타입 부문 — **완성도보다 창의성·독창성이 최우선 심사 기준.** 데이터 스택·모듈 계약이 자세한 건 신뢰도를 받치는 인프라이기 때문이지, 심사 기준 자체가 완성도는 아님 — **데모의 서사가 최종적으로 제일 중요.**

### 팀 배경

국민대 산림환경 및 원격탐사 전공. 국가유산청 산불위험 예측 AI 연구(CNN 기반 멀티태스크 모델)와 대상 수상작 MOFOM AI(forest-ai-agent)에서의 협업 경험을 화재-산사태 재해연쇄라는 새 문제에 적용. §4의 화재흉터 증폭계수·폴백 계층·모듈화 원칙은 모두 그 선행 프로젝트에서 검증된 패턴 재사용.

---

## 2. 핵심 컨셉 (TL;DR)

- **독창성 축 1 — 재해연쇄**: `f(dNBR, Δt)`로 화재→산사태→하천범람 사슬을 정량 모델링 (산불 자체는 실시간 예측 대상이 아닌 정적 이력값)
- **독창성 축 2 — 골든타임 격차**: "예측 정확도"가 아니라 "관의 판단·전파 지연"을 자동화로 우회
- **독창성 축 3 — 판단 지연 자체를 겨냥한 3종 장치**: ① 시민 신고 역검증 루프(Module H) ② 원클릭 승인(사람의 최종 판단권은 유지하되 몇 시간을 몇 초로) ③ What-if 예측 시뮬레이터(가상 강수 시나리오를 심사위원이 직접 조작)

**스코프 확정**: 실시간 예측 대상은 수해(산사태·하천범람·도로침수)뿐. 산불은 정적 증폭계수로만 쓰이고 별도 화재위험 예측 모델은 스코프 제외. 데이터 처리 범위도 우기 집중기간(6~9월)만.

- **메인 데모**: 2025.7.19 산청 산사태 (공개된 실패 타임라인 보유)
- **보조 데모**: 서울 취약성지수 (전국 확장성 증거, 메인 서사 아님)

---

## 3. 재해 Taxonomy

예측 모델은 3종으로 한정, 나머지는 GIS 파생 계산 (행안부 재해연보 분류체계와 1:1 대응):

| # | 유형 | 산출 방식 | 재해연보 카테고리 |
|---|------|-----------|---------------------|
| 1 | 산사태·토사유실 | 예측 모델 (Module A) | 토사유실 |
| 2 | 하천범람·하천시설 붕괴 | 예측 모델 (Module B) | 하천시설 붕괴 |
| 3 | 도로·지하차도 침수 | 규칙기반 경보 (Module C, 모델 아님) | 도로 침수 |
| 4 | 건축물 침수 | 위험지역 ∩ 건축물대장 (파생, Module D) | 건축물 침수 |
| 5 | 농경지 침수 | 위험지역 ∩ 농경지 (파생, Module D) | 농경지 침수 |

---

## 4. 데이터 스택 (확정)

| 레이어 | 데이터 | 해상도/주기 | 비고 |
|--------|--------|-------------|------|
| 정적 | DEM 유도 지형(경사·곡률·TWI·사면방향) | 10m | Module A 공통입력 |
| 정적 | NDVI, dNBR (Sentinel-2) | 10m | 산불 흉터 매핑, 식생회복 추적 |
| 정적 | 토지피복 (환경부) | 10m | 노출자산 분류 |
| 동적 | 강수량(mm/h, **필수**) | 500m, 1시간, 6~9월만 | Module A/B 직접 트리거, API 지수 산출 |
| 동적 | VPD·기온·풍속 (선택/저우선순위) | 500m | 향후 정밀모드 확장용, MVP 아님 |
| 예보 | LDAPS 강수량 | 1.5km, 3시간 간격 | **리드타임 3~6시간만 신뢰**, 48시간 전체 신뢰 금지 |
| SAR | Sentinel-1 수체 탐지 | — | Module B 보조, 광학 불가 상황에서도 동작 |
| SAR | InSAR 지반변위 시계열 | — | 땅밀림형 산사태 전조, coherence 확보 지점만 |
| 벡터 | 대피소/도로망/하천수위/건축물/농경지/피해비용원단위 | — | §14의 각 공공 API/DB |

**처리 범위 축소**: 우기 집중기간(6~9월)만 처리 — 연중 대비 데이터량 약 1/3로 절감. 6~9월 구간 내에도 무강우일이 충분히 섞여 있어 음성(평시) 클래스 부족 문제는 없음 — 단, 학습 전 강우/무강우 비율 확인 필요(§7 TODO).

### 화재흉터 증폭계수 `f(dNBR, Δt)`

화재위험 자체는 실시간 예측 대상이 아니다 — `f(dNBR, Δt)`는 과거 산불이 남긴 **정적(static) 증폭계수**일 뿐.

| 근거 | 수치 | 출처 |
|------|------|------|
| 국내 실측(산림청, 2000 동해안 산불) | 화재 2년 후에도 토양유출량 일반산림 대비 3~4배 | 경향신문(2025.4) 인용 |
| 침투속도(국제문헌) | 화재 6개월 후 강우침투속도 2배 이상 | KIGAM |
| 확률증분(그리스 사례) | 강우유발 산사태확률 +20~30% 이상 | KIGAM |
| 벤치마크 | KIGAM 물리모델, 극한강우 후 2.5시간 내 위험도 산출, 예천·경주 85~90%+ 정확도 | KIGAM |

```
f(dNBR, Δt) = 1 + (A_max(dNBR_class) - 1) × decay(Δt)
A_max: low→1.2, moderate→2.0, high→3.5~4.0 (Key&Benson 2006 등급)
decay(Δt): Δt<2년 → 1.0(감쇠없음) / Δt≥2년 → NDVI 회복곡선 기반 경험적 산출
```

**포지셔닝**: "KIGAM보다 정확한 모델"이 아니라 "KIGAM급 모델이 있어도 못 막은 전파 지연을 우회하는 시스템". TODO: `A_max` 등급값은 2025.3 산불 11개지역 자체 dNBR 산출 후 사후검증으로 보정.

---

## 5. 통합 규약 (전 모듈 필수 — 가장 중요)

3개의 독립 세션이 서로 대화 없이도 맞아떨어지려면 아래를 토씨 하나 안 틀리고 지켜야 한다.

### 값 표기 규칙

| 항목 | 규칙 |
|------|------|
| 좌표 | 내부 분석·저장은 **`EPSG:5179`**(한국 UTM-K). 지점은 `x_5179`/`y_5179`, 폴리곤·라인은 `geometry_5179`(GeoJSON과 동일 구조지만 5179 미터라 `*_geojson`이라 부르지 않음). Module UI/UI-3D 출력 직전에만 `EPSG:4326`으로 재투영해 `*_geojson`으로 내보냄. 그 앞단(A/B/C/D/E/G/H/O) 교환은 전부 5179 |
| 시간 | ISO 8601 + 타임존 명시. 예: `"2025-07-19T08:00:00+09:00"`(KST). **UTC 금지** |
| 확률 | float, `0.0~1.0` (퍼센트 아님) |
| 거리/면적 | 미터(`_m`), 헥타르(`_ha`)/제곱미터(`_m2`) — 필드명에 단위 명시 필수 |
| 금액 | 원(KRW) 정수 (`_krw`, 만원 단위 금지) |
| 신뢰구간 | 항상 `[low, high]` 2원소 배열, 동일 단위 |
| 결측치 | `null` 사용, 빈 문자열/0 대체 금지 |

### 모듈 호출 규약

- 모든 모듈 = Python 패키지, 표준 진입점 `def run(input: dict) -> dict` 하나로 노출
- 각 모듈 폴더는 pytest로 독립 테스트 가능 (다른 모듈 없이 `tests/`의 fixture만으로 실행)
- 최종 통합은 FastAPI 서버 하나(`api_server.py`)가 각 모듈을 import해서 순서대로 호출 — REST로 쪼개지 않음(MOFOM 패턴 재사용)

모든 모듈 출력은 공통 봉투(envelope):

```json
{
  "status": "ok",        // "ok" | "degraded" | "error"
  "fallback_tier": 1,     // 1=정상, 2=2순위 폴백, 3=3순위 폴백
  "data": { "...": "모듈별 실제 데이터" },
  "warnings": []
}
```

모듈은 예외(exception)를 던져서 죽지 않는다 — 실패해도 `status: "degraded"` + 폴백값 반환 (graceful degradation을 코드 레벨 계약으로 강제, Module O가 나머지를 보존할 수 있게).

### 계약 파일 (`contracts/`)

`contracts/module_*.example.json` / `module_*.schema.json` 8세트가 이미 이 저장소에 커밋되어 있음 — 아래 §6이 그 내용. **Day 1 이후 3인 합의 없이 임의 수정 금지** (한쪽에서 필드 하나 바꾸면 다른 두 트랙이 조용히 깨짐).

---

## 6. 모듈 계약 — 입출력 예시 (= `contracts/`의 내용)

### Module A — 산사태 예측 (`module_a_landslide`)

```jsonc
// input
{
  "x_5179": 1090452.3, "y_5179": 1662188.7, "timestamp": "2025-07-19T08:00:00+09:00",
  "static": { "slope_deg": 32.5, "curvature": -0.02, "twi": 6.8, "aspect_deg": 210,
    "dnbr": 0.62, "dnbr_class": "high", "days_since_fire": 121 },
  "dynamic": { "rainfall_1h_mm": [12.0, 18.5, 24.0], "rainfall_cumulative_24h_mm": 187.3,
    "rainfall_cumulative_72h_mm": 245.0, "api_index": 0.81, "source": "observed" },
  "insar_displacement_mm_per_day": null
}
// output (data)
{ "landslide_prob": 0.78, "confidence_interval": [0.65, 0.88], "source": "observed",
  "amplification_factor": 3.1, "precursor_flag": false,
  "hours_to_critical": 2.5,
  "location": { "x_5179": 1090452.3, "y_5179": 1662188.7 } }
```

`hours_to_critical`은 "골든타임"을 실제 숫자로 만드는 핵심 필드 — LDAPS 예보 시계열(1시간 스텝)로 `landslide_prob`을 계산해 임계치(예: 0.7)를 처음 넘는 시점까지의 시간. 예보 구간 내내 안 넘으면 `null`. 폴백: InSAR+실측강수 → 지형+실측강수 → LDAPS 예보모드(CI 확대, `source:"forecast"`).

### Module B — 하천범람 예측 (`module_b_flood`)

```jsonc
// input
{ "reach_id": "GEUMHO_042", "static": { "drainage_area_km2": 58.2, "river_order": 3, "slope_pct": 1.8 },
  "dynamic": { "rainfall_cumulative_24h_mm": [187.3], "river_level_m": 3.2 }, "sar_water_extent": null }
// output (data)
{ "flood_prob": 0.61, "confidence_interval": [0.45, 0.75], "hours_to_critical": 4.0,
  "inundation_extent_5179": { "type": "FeatureCollection", "features": [] } }
```

폴백: 실측강수+수위+SAR → 실측강수+SAR → 실측강수만(CI 확대).

### Module C — 도로·지하차도 침수 (`module_c_urban_rule`, 규칙기반·모델 아님)

```jsonc
// input
{ "underpass_id": "SC-UP-003", "rainfall_intensity_1h_mm": 45.0, "known_risk": true, "drainage_capacity_class": "low" }
// output (data)
{ "alert_level": "위험", "underpass_id": "SC-UP-003" } // ∈ {"정상","주의","경계","위험"}
```

UI 표기 시 신뢰도 배지를 A/B와 다르게(모델 아님을 명시).

### Module D — 노출자산 오버레이 (`module_d_exposure_overlay`)

```jsonc
// input — A/B/C의 data를 위험폴리곤 배열로 (전부 5179)
{ "risk_polygons": [
    { "source_module": "A", "geometry_5179": { "type": "Polygon", "coordinates": [] }, "risk_prob": 0.78 },
    { "source_module": "B", "geometry_5179": { "type": "Polygon", "coordinates": [] }, "risk_prob": 0.61 }
  ],
  "building_footprints_5179": { "type": "FeatureCollection", "features": [] },
  "farmland_parcels_5179": { "type": "FeatureCollection", "features": [] } }
// output (data)
{ "exposed_buildings": [ { "building_id": "B12345", "risk_prob": 0.78, "use_type": "주거" } ],
  "exposed_farmland_ha": 4.2 }
```

### Module E — 대피소·경로 라우팅 (`module_e_routing`)

```jsonc
// input — time_budget_hours = Module O가 A/B의 hours_to_critical에서 안전여유(기본 0.5h)를 뺀 값
{ "origin": { "x_5179": 1090452.3, "y_5179": 1662188.7 },
  "risk_polygons": [ { "geometry_5179": {}, "risk_prob": 0.78 } ],
  "shelter_candidates": [ { "shelter_id": "S001", "x_5179": 1091200.0, "y_5179": 1663500.0, "capacity": 200 } ],
  "road_graph_source": "standard_node_link_v1", "time_budget_hours": 2.0 }
// output (data)
{ "shelter_id": "S001", "route_5179": { "type": "LineString", "coordinates": [] },
  "eta_min": 14.5, "route_confidence": "high",
  "time_feasible": true, "time_margin_min": 105.5, "fallback_used": false }
```

**알고리즘**: ① 후보별 위험가중 A*(risk_prob ≥ 0.7 셀/링크는 제외 또는 페널티)로 경로·`eta_min` 계산 → ② `eta_min ≤ time_budget_hours×60` 만족하는 후보 중 최단시간 선택(동률이면 capacity 큰 쪽) → ③ 아무 대피소도 시간 내 도달 불가면(`time_feasible: false`) 최근접 안전지점(`risk_prob < 0.3`)으로 목적지 변경하는 긴급 폴백 실행, `fallback_used: true` + UI에 "지정 대피소까지 시간 부족 — 가까운 안전지대로 즉시 이동" 경고 **명시적으로** 노출(생명안전상 가장 중요한 예외처리 — 절대 조용히 넘어가지 않는다).

### Module G — 피해비용 추정 (`module_g_damage_cost`)

```jsonc
// input — Module D 출력을 그대로 받음
{ "exposed_buildings": [ { "building_id": "B12345", "risk_prob": 0.78, "use_type": "주거" } ],
  "exposed_farmland_ha": 4.2, "unit_cost_table_ref": "재해연보_2024_원단위" }
// output (data)
{ "estimated_cost_krw": 1250000000, "cost_range_krw": [900000000, 1600000000],
  "basis_citation": "행안부 재해연보 2024 건축물 침수 원단위" }
```

### Module H — 시민 신고 역검증 (`module_h_citizen_verification`, 신규·창의성 축 3)

산청 사건의 진짜 실패(신고는 08:00부터 있었는데 경보는 12:37)를 정면으로 겨냥. Module A의 `precursor_flag`(InSAR 땅밀림 전조)가 뜬 반경 내 주민에게 자동으로 "이상 징후가 보이십니까?"를 푸시하고, 응답을 모아 확신도를 보정해 Module O에 되돌려주는 역검증 루프.

```jsonc
// input — Module A의 precursor_flag=true 지점 반경 내에서 트리거
{ "alert_id": "AL-20250719-0915", "trigger_location": { "x_5179": 1090452.3, "y_5179": 1662188.7 },
  "trigger_radius_m": 500,
  "citizen_reports": [
    { "report_id": "R001", "x_5179": 1090480.1, "y_5179": 1662201.4,
      "timestamp": "2025-07-19T09:22:00+09:00",
      "report_type": "이상징후_목격", "photo_url": null } // "이상징후_목격"|"이미_대피함"|"오탐_신고"
  ] }
// output (data)
{ "report_count": 6, "verification_status": "현장확인", // "미확인"|"현장확인"|"오탐판정"
  "confidence_adjustment": 0.12, // Module A의 landslide_prob에 가산(-0.3~+0.3), 오탐 다수면 음수
  "response_latency_min": 4.5 }
```

폴백: 응답 0건이면 `verification_status: "미확인"`, `confidence_adjustment: 0` — Module O는 시민 확인 없이도 원래 임계치 로직대로 진행(역검증은 보조 채널, 단일 실패점 아님).

### Module O — 골든타임 오케스트레이션 (`module_o_orchestrator`)

**역할**: A/B/C를 임계치로 감시 → 초과 시 D/E/G 순차 호출 → H로 시민 역검증 트리거 → 경보 패키지 생성 → 전파.

**상태머신 8단계**: 관측 → 예측 → 1차권고 → 시민 역검증(H, 병렬) → 원클릭 승인 대기 → 경보격상 → 주민전파 → 개별대피

**시간예산**: `time_budget_hours = A/B의 hours_to_critical − 안전여유(기본 0.5h)` → Module E에 전달. 경보 패키지에 Module E의 `time_feasible`/`fallback_used` 반드시 포함.

**원클릭 승인** (창의성 축 3-2, 산청의 "4시간 지연"을 정면 타격):
- 지자체 담당자가 대시보드에서 버튼 하나로 승인/보류 — 최종 판단권은 유지, 판단 시간을 몇 시간→몇 초로
- `approval_status`: `"대기" | "승인" | "거부" | "자동승인(timeout)"`
- 엔드포인트: `POST /approve/{alert_id}` `{ "decision": "승인"|"거부", "approver_id": "..." }`
- **타임아웃 자동승인**: `auto_approve_timeout_min`(기본 15분) 내 무응답 시 자동 "승인" 전환. 단, Module H가 `"오탐판정"`이면 자동승인 걸지 않고 대기 유지

```jsonc
// output (data)
{ "timeline_actual": { "advisory": "2025-07-17T00:00:00+09:00", "report_start": "2025-07-19T08:00:00+09:00",
    "warning_escalated": "2025-07-19T12:37:00+09:00" },
  "timeline_agent": { "detected": "2025-07-19T09:15:00+09:00", "alert_sent": "2025-07-19T09:20:00+09:00" },
  "golden_time_saved_min": 197,
  "approval_status": "자동승인(timeout)",
  "citizen_verification": { "verification_status": "현장확인", "confidence_adjustment": 0.12 },
  "alert_package": { "landslide": {}, "flood": {}, "shelter_route": {}, "damage_cost": {} } }
```

> `input` 필드(`alert_id`/`trigger_location`/`timestamp`/`auto_approve_timeout_min`/`safety_margin_hours`)는 원문서 §5에 명시적 예시가 없어 트랙③이 추론해 `contracts/module_o.example.json`에 넣은 값 — 3인이 함께 확정할 것.

### Module UI / UI-3D

- **대시보드**: 지도+타임라인, 골든타임 비교 카운터, 대피소/경로/피해비용 패널, 근거/신뢰도 배지, (보조) 서울 확장성 화면
- **LLM 채팅**: Module O의 `alert_package` 위에 얹는 자연어 해석층
- **원클릭 승인 화면**: 승인/거부 버튼 2개 + 근거 요약(위험확률·신뢰구간·시민 역검증·`time_feasible`) 한 화면에 압축, 타임아웃 카운트다운 시각 노출
- **What-if 시뮬레이터**: 새 모델 불필요 — Module A/B의 `run()`을 가상 강수값으로 즉시 재호출해 위험 폴리곤 실시간 재계산 (순수 UI 레이어, 트랙①과 독립적으로 트랙③에서 구현 가능)
- **3D**: MapLibre GL JS(지형) + deck.gl(TerrainLayer/PolygonLayer/PathLayer/ScatterplotLayer). 지형 1순위 V-World 3D API, 2순위 자체 DEM. 레이어: 지형메시/산사태 위험드레이프/침수 bathtub 볼륨("정밀 수리모형 아님" 배지 필수)/건물 압출/경로 3D 라인/시간슬라이더/What-if 슬라이더. AOI: 상능마을 일대 수 km²

---

## 7. 불확실성 표기 & 폴백 (전 모듈 공통)

- 모든 확률/추정치는 `confidence_interval: [low, high]` 필수
- `source: "observed" | "forecast"`를 A/B 출력에 필수 포함, forecast는 CI를 더 넓게
- InSAR는 coherence 확보 지점만 표시, 나머지는 "관측 불가" 명시
- Module C는 신뢰도 배지를 A/B와 다르게(모델 아님을 명확히)

| 모듈 | 1순위 | 2순위 | 3순위 |
|------|-------|-------|-------|
| A 산사태 | InSAR+실측강수 정밀모드 | 지형+실측강수 | LDAPS 예보모드(CI 확대) |
| B 하천범람 | 실측강수+하천수위+SAR | 실측강수+SAR | 실측강수만 |
| H 시민 역검증 | 시민 응답 다수 확보 | 응답 소수(낮은 가중치) | 응답 0건(confidence_adjustment=0) |

---

## 8. 데모 시나리오 (산청 2025 타임라인 재연)

1. 초기화면: 2025.3 산불 피해지(dNBR 흉터) 지도 로딩
2. 7/19 강우 시작 → 위험도 그래프가 실제 신고 시작(08:00)보다 앞서 임계치 초과
3. 상능마을 구간 InSAR 이상치 → 땅밀림 전조 플래그
4. 대피소·경로·피해비용 패널 동시 생성
5. Module B 동시 트리거(하류 영향권)
6. 골든타임 비교 카운터: `timeline_actual(12:37)` vs `timeline_agent` → **"N시간 O분 확보"** 헤드라인
7. (보조) 서울 취약성지수 오버레이

---

## 9. 저장소 구조

```
README.md                  # 이 파일 — 개요 + §0~§9 핵심 요약
ARCHITECTURE.md             # 아키텍처 확정안 v2.4 전문
docs/                        # 원본 PDF (다이어그램 §3/§11 포함)
contracts/                   # §5 — 8개 모듈 입출력 계약 (Day 1 최우선, 3인 합의 없이 수정 금지)
  module_*.example.json
  module_*.schema.json
module_a_landslide/         # 트랙① — 산사태 예측
module_b_flood/             # 트랙① — 하천범람 예측
module_c_urban_rule/        # 트랙② — 도로·지하차도 침수 (규칙기반)
module_d_exposure_overlay/  # 트랙② — 노출자산 오버레이
module_e_routing/           # 트랙② — 대피소·경로 라우팅
module_g_damage_cost/       # 트랙② — 피해비용 추정
module_h_citizen_verification/ # 트랙② — 시민 신고 역검증
module_o_orchestrator/      # 트랙③ — 골든타임 오케스트레이션
ui/                           # 트랙③ — Next.js 대시보드 + 3D
data/                         # static(10m) / dynamic(500m, 6~9월만) / vector
api_server.py                  # FastAPI, 전 모듈 import
```

---

## 10. 팀 & 역할 (3인, 독립 개발)

| 트랙 | 담당 | 소유 모듈 | 핵심 산출물 |
|------|------|-----------|-------------|
| ① 예측모델·위성 | 김민석 | A, B | 데이터 파이프라인(6~9월), `f(dNBR,Δt)`, LDAPS 편차보정, 신뢰구간 |
| ② 대응로직·데이터통합 | 나정우 | C, D, E, G, H | 벡터데이터, 위험가중 A* 라우팅, 피해비용, 시민 역검증 |
| ③ 오케스트레이션·UI·3D | 하수범 | O, UI, UI-3D | 상태머신·원클릭승인, 대시보드, deck.gl+V-World 3D, What-if 시뮬레이터, 산청 데모 |

담당자가 바뀌어도 이 표와 §5~6 계약만 유지되면 재구성 가능.

## 11. 2주 로드맵

| 구간 | ① 예측모델 | ② 대응로직 | ③ 오케스트레이션/UI |
|------|-----------|-----------|---------------------|
| Day 1 | 3인 §5~6 리뷰, `contracts/` 확정·커밋 → 각자 착수 | 〃 | 〃 |
| Day 2-5 | 500m/1.5km/10m 파이프라인, Module A 베이스라인(목업 InSAR) | Module C 규칙엔진, Module D(A/B example.json 입력), Module H 뼈대 | Next.js 스캐폴딩 + module_o.example.json으로 대시보드 뼈대, V-World API 연동 테스트 |
| Day 6-9 | A/B 실데이터 학습·검증, 신뢰구간 산출·공유 | 실제 A/B output으로 D/E/G 전환, Module H를 precursor_flag와 실연동 | 실제 output 연동, 3D 레이어 구현, 원클릭 승인 화면 프로토타입 |
| Day 10-12 | 산청 백테스트로 `golden_time_saved_min` 산출 | 산청 대피소/경로 실사례 검증 | 시간슬라이더·What-if 완성, `api_server.py` 통합, 버그픽스 |
| Day 13-14 | 전원: 발표자료·기획서, 최종 리허설, 예상 질의응답 준비 | 〃 | 〃 |

## 12. 남은 TODO

1. `A_max` 등급값 — 2025.3 산불 11개지역 자체검증으로 보정
2. LDAPS↔500m 편차보정 함수 설계·검증(6~9월 중첩기간)
3. 산청 타임라인 백테스트로 `golden_time_saved_min` 목표수치 확정
4. Module A/B 베이스라인 학습 (2019-2025 중 6~9월만 + 산사태정보시스템 라벨) — 강우/무강우 비율 확인 후 필요시 연중 확장 재검토
5. V-World 3D/지형 API 커버리지 확인(상능마을 AOI)
6. Module H 푸시 알림 채널 결정(문자/앱푸시/카톡 알림톡 — 데모는 웹 대시보드 시뮬레이션 대체 가능)
7. 원클릭 승인 `auto_approve_timeout_min` 기본값(15분) 데모에 맞춰 조정
8. Module O `input` 스키마(위 §6 참고사항) 3인 합의로 확정

---

## 13. 트랙별 Claude Code 브리핑

각 트랙 담당자는 아래 문구를 그대로 복붙해서 각자 세션에 붙여넣을 것 (전문은 [ARCHITECTURE.md §13](ARCHITECTURE.md)):

> 이 저장소의 README.md(또는 ARCHITECTURE.md)를 읽어라 — 배경(재해연쇄+골든타임 격차, 산청 사건)부터 반드시 이해한 뒤 §5~6(통합 규약·모듈 계약)으로 넘어가라. 다른 트랙의 내부 구현은 몰라도 된다 — 오직 `contracts/`의 example.json/schema.json이 네 모듈의 입출력 계약 전부다. Day 1엔 나머지 두 세션과 함께 `contracts/`를 먼저 확정하라.

- **트랙①**: `module_a_landslide`, `module_b_flood`
- **트랙②**: `module_c_urban_rule`, `module_d_exposure_overlay`, `module_e_routing`, `module_g_damage_cost`, `module_h_citizen_verification` — D/E/G/H는 `contracts/module_a.example.json`, `module_b.example.json`을 목업 삼아 트랙①을 기다리지 않고 개발
- **트랙③**: `module_o_orchestrator`, `ui/`(대시보드+채팅+원클릭승인+3D) — A~H를 전부 `contracts/`의 example.json으로 목업 호출하는 파이프라인부터 굴려보고 실제 모듈로 하나씩 교체

---

## 14. 참고 벤치마크

USGS Postfire debris-flow hazards · 경향신문(2025.4) 대형 산불 이후 산사태 우려 · KIGAM 산불 뒤 산사태 위험 예측 · MOFOM AI/forest-ai-agent · 자치법규 정책지도/policymaps · 나무위키(2025 산청 북부 산사태, 2025 여름 한반도 폭우) · 기상자료개방포털 LDAPS · 기상청 API허브 · WRF-Hydro+LDAPS 금호강 유역 앙상블 유출 예측 연구
