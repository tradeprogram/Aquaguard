# module_a_landslide — 산사태 예측 (트랙① / 김민석)

ARCHITECTURE.md §5 Module A 구현. **Infinite Slope 안전율(FoS)을 먼저 계산하고
`landslide_prob`은 그 FoS를 변환한 값** — 순수 ML 확률모델이 아니다(§5 방법론 확정
준수). 지반정수는 전부 **출판 문헌값**이며 가상값이 없다([DATA_SOURCES.md](DATA_SOURCES.md)).

> 이 브랜치는 트랙①의 진행상황·확보 데이터·단계 계획을 담는다(트랙②
> `track2/module-c` 방식). Module B/V는 후속 브랜치.

---

## 1. 방법론

```
강우/선행함수 → 포화도 m → Infinite Slope FoS → FoS→확률 변환 → landslide_prob(+CI)
                                  ↑ 산불 f(dNBR,Δt)로 뿌리점착력 약화
```

무한사면 안전율:

```
        c' + Cr + (γ − m·γ_w)·z·cos²β·tanφ'
FoS = ────────────────────────────────────────   (FoS<1 → 붕괴)
                γ·z·sinβ·cosβ
```

| 기호 | 의미 | 출처 |
|---|---|---|
| c' | 유효점착력(토성별) | Frontiers 2026 Table 1 (§DATA_SOURCES) |
| φ' | 유효내부마찰각(토성별) | 〃 (PSU·부산실측 교차검증) |
| γ | 흙 단위중량(토성별) | 〃 |
| z | 토심(=파괴면) | 정밀토양도 AD 유효토심 등급 |
| m | 포화도(0~1) | 배수등급 기저값 + 강우 동적 (§9.3 보정 예정) |
| Cr | 뿌리점착력 | Frontiers 2026 (0~5 kPa) |
| f(dNBR,Δt) | 산불 증폭 | ARCHITECTURE §2.5 (A_max high 3.75) |

**산불 결합**: 피해지는 뿌리가 죽어 `Cr_eff = Cr / f`로 약화 → FoS↓. `amplification_factor = f`를 계약 output에 보고.

---

## 2. 지금까지 한 일 (데이터 확보 과정)

정밀토양도(농진청 1:25,000, 전국, EPSG:5174, `.prj` 없음)에서 FoS 지반정수를 추출:

1. **토양 코드사전 추출** (`scripts/01_extract_soil_codes.py`) — 11개 속성 88개 분류.
   유효토심·배수·경사·표토/심토토성·자갈·구조·모재·지형. → `data/soil_code_dictionary.csv`
2. **토성 → 지반정수 매핑** (`scripts/02_build_fos_parameter_table.py`) — 문헌값으로
   c'·φ'·γ·Ksat, 토심 z, 배수 m₀, 뿌리점착력. **3중 출처 교차검증**. → `data/fos_*.csv`, `data/fos_parameter_bundle.json`
   (스크립트 원본은 작업 저장소 `G:\연구\공모전\아쿠아가드\scripts`. 데이터 산출물만 커밋.)

확보한 토성별 전단강도(심토토성=파괴면):

| 토성(심토) | c'(kPa) | φ'(°) | γ(kN/m³) | provenance |
|---|---|---|---|---|
| 사질 | 1.2 | 30 | 19.33 | MODEL |
| 사양질 | 4.0 | 28 | 18.57 | MODEL |
| 미사사양질 | 3.9 | 28 | 18.64 | MODEL |
| 식양질 | 8.7 | 20 | 17.65 | MODEL |
| 미사식양질 | 10.6 | 22 | 17.00 | MODEL |
| 식질 | 12.0 | 20 | 16.50 | EXTRAPOLATED |
| 역질 | 0.5 | 35 | 19.50 | EXTRAPOLATED |
| 사력질 | 1.0 | 33 | 19.30 | EXTRAPOLATED |

---

## 3. 구현·검증 상태

**구현 완료** (`pytest module_a_landslide/tests/ -q` → **37 passed**):
- `fos.py` — FoS 물리, 산불 f(dNBR,Δt), FoS→확률 시그모이드, 몬테카를로 CI
- `parameters.py` — 토양도 지반정수 룩업 + 강우→포화도 m
- `envelope.py` — 계약 정규화 + §7 폴백(tier 1 InSAR / 2 지형 / 3 예보) + graceful degradation
- `forecast.py` — **LDAPS 예보 시간강우 → `hours_to_critical` 전진적분** (아래 3-1)
- `__init__.py` — `run(input)->dict`(§4.2 공통 봉투) + `explain()`(§6.1 Provenance)

**물리 검증** (산청 2025-07-19 조건: 경사 32.5°, dNBR high, 187mm/24h):
- 사질 풍화토 주입 → **FoS 0.637 (<1) → landslide_prob 0.898, CI[0.81,0.94]** (고위험, 물리 정상)
- 단조성 테스트 통과: 경사↑·포화↑·산불등급↑ → 위험↑

### 3-1. hours_to_critical (a-htc)

관측만으로는 미래 시각을 알 수 없어 종전에는 '이미 초과(0)' 또는 '판단불가(null)'뿐이었다.
이제 **시간별 예보강우 시계열**을 받아 1시간씩 전진시키며 첫 임계초과(P≥0.7) 시각을 찾는다.

```
예보 시간강우 → 24h 이동누적 → m(t) → FoS(t) → P(t) → 첫 P≥0.7 시각
```

주입 방법(기존 `_soil`·`_terrain` 관례와 동일):

```python
input["_forecast"] = {"source": "LDAPS", "rain_1h_mm": [5, 8, 12, 20, 30, ...]}
# 또는 dynamic.source=="forecast" 이면 dynamic.rainfall_1h_mm 자체를 예보로 해석
```

동작 확인(사질 풍화토 35° 사면):

| 예보 | hours_to_critical |
|---|---|
| 30mm/h 지속 | **3.0 h** |
| 점증(2→40mm/h) | **8.0 h** |
| 3mm/h 약한 비 | null (지평 내 미도달) |
| 28° 완사면 + 폭우 | null |

**한계(중요)**: 전국 대표 폴백 토양(식양질, c'=8.7kPa)은 **완전포화(m=1.0)에서도
FoS≈1.9**라 어떤 예보를 넣어도 임계에 도달하지 않는다. 즉 이 기능은 부지 토양이
조립질(사질·역질·사력질)로 주입될 때만 값을 낸다 — 폴백 상태에서 null이 나오는 것은
버그가 아니라 물리다. 예보 자체의 불확실성은 전파하지 않으며(tier 3 CI 확대는
`run()`이 별도 처리), 지평은 LDAPS 운영범위에 맞춰 +48h로 제한한다.

### 3-2. 토양격자 샘플러 (a-1) — 위험도가 안 나오던 원인

계약 input에는 토성·토심이 없어서 `_soil` 이 주입되지 않으면 **전국 대표 폴백
(식양질, c'=8.7kPa, z=0.75m)** 을 썼다. 그런데 이 조합은 **완전포화(m=1.0)에서도
FoS≈1.9~2.2** 라 어떤 강우를 넣어도 `landslide_prob` 이 0.7을 못 넘는다.

Module O는 `landslide_prob >= 0.7` 일 때만 하류 모듈(D/E/G)을 돌린다
(`orchestrator.py` `LANDSLIDE_THRESHOLD`). 즉 **트리거가 영영 안 걸려서 노출·대피경로·
피해액이 전부 비고, 3D 시뮬레이터에 넘길 위험 지오메트리도 없었다.** 발생부 좌표가
없어서가 아니라 이것이 원인이었다.

`soil_sampler.py` 가 좌표에서 산청 지반정수 격자를 샘플링해 `_soil` 을 자동으로 채운다.

| 같은 좌표(x=1030226, y=1729619 · 경사 37.6° · dNBR 0.49) | `landslide_prob` | 트리거 |
|---|---|---|
| 전국 폴백(종전) | 0.015 | ❌ |
| **격자 샘플링** | **0.798** | ✅ |

격자(`data/sancheong_soil_grid_5m.npz`, 2.1MB)는 **5m 원해상도 그대로**다. 조합이
33개뿐이라 uint8 인덱스 + 룩업으로 압축했고, rasterio 없이 numpy만으로 읽는다.
25m로 줄였더니 최근접 리샘플이 고위험 포켓을 뭉개서(한 셀이 0.744→0.391) 되돌렸다.

- **AOI 밖 좌표는 격자를 쓰지 않는다** — `None` 을 반환하고 종전 전국 폴백으로 되돌아간다.
  다른 지역에서 조용히 산청 토양을 쓰지 않기 위해서다.
- **dNBR은 격자에 넣지 않았다.** 산불 등급은 계약(`static.dnbr_class`)이 주는 값이고,
  격자가 그걸 덮어쓰면 계약 밖 데이터로 결과가 바뀐다.

### 3-3. 원시 지반정수 직접 주입

`_soil` 에 토성 카테고리 대신 `c_kpa`·`phi_deg`·`gamma_kn_m3`·`z_m`·`m0` 을 직접 넣을 수
있다. 격자는 픽셀별 실수값을 갖고 있어 8개 토성 카테고리로 되돌릴 이유가 없고,
풍화화강토(c'2·φ36)처럼 토성표에 없는 재료도 그대로 쓸 수 있다.

```python
input["_soil"] = {"c_kpa": 2.0, "phi_deg": 36.0, "gamma_kn_m3": 19.0, "z_m": 1.0, "m0": 0.2}
```

우선순위: **원시 지반정수 → 토성 카테고리 → 격자 자동샘플링 → 전국 폴백**.

### 3-4. 위험 폴리곤 시계열 (`data/risk_polygons/`)

`risk_polygons[].geometry_5179` 가 비어 있어서 3D 시뮬레이터가 손으로 배치한 흐름
경로를 쓰고 있었다(`MapExplorer.tsx` 주석). `scripts/45_risk_polygons_timeseries.py`
가 산청 전역 5m 격자를 실측 강우로 구동해 그 지오메트리를 만든다.

| 레이어 | 면적 | feature |
|---|---|---|
| `A_soilmap` critical (P≥0.7) | 0.010 km² | 2 |
| `A_soilmap` warning (P≥0.5) | 0.238 km² | 4 |
| `B_weathered` critical | 0.940 km² | 7 |
| `B_weathered` warning | 5.006 km² | 8 |

각 feature에 **`arrival_hour`(임계 첫 도달 시각)** 이 붙어 있어서, UI는 이 값으로
필터링하면 시간에 따라 위험이 번지는 애니메이션이 된다. B_weathered critical 기준
07-19 08:00 5.2ha → **09:00 43.9ha** 로 급증하며, 백테스트 `T_agent` 09:00과 일치한다.

> **A_soilmap 이 Module A(`soil_sampler`)와 정합하는 기본값**이고, `B_weathered` 는
> 급사면 파괴재료 가정 시나리오다. 면적이 100배 차이 나므로 **섞어 쓰면 안 된다.**
> 계산은 프레임마다 벡터화하지 않고, 픽셀별 '첫 도달 시각' 래스터를 한 번만 만들어
> 벡터화한다(FoS가 습윤도에 선형이라 가능 — 스크립트 docstring 참조).

**한계**: Rsat·Wmax·시그모이드 k는 미보정이고, 발생부 참값이 없어 이 폴리곤의
**공간정확도는 검증되지 않았다.** `arrival_hour` 는 "그 시각에 임계를 처음 넘었다"이지
"그 시각에 붕괴했다"가 아니다.

**정직성**: 계약 input에는 토성·토심이 없다 → Module A가 좌표에서 토양도를 샘플링해야 함.
전국 토양도 shapefile은 대용량이라 미커밋 → 부지 미샘플 시 전국 대표 폴백값 사용 +
`warnings`·`fallback_tier`로 명시(module_c의 PLACEHOLDER 정직성과 동일).

---

## 4. 다음 단계 (staged plan)

| 단계 | 작업 | 의존(필요 데이터) |
|---|---|---|
| ✅ A-1 | 정밀토양도 샘플러 연결(좌표→지반정수) | **완료** — `soil_sampler.py` + 5m 격자 (§3-2) |
| A-2 | 5m DEM으로 slope·TWI·curvature 정밀화 | 국토정보플랫폼 DEM(키 필요) |
| A-3 | 강우→포화도 m 계수 실측 보정 | 기상청 AWS·토양수분(일부 확보) |
| ✅ A-4 | LDAPS 예보 연동 → `hours_to_critical` | **완료** — `forecast.py` (§3-1) |
| ✅ A-5 | Ablation(±dNBR) | **완료** — `backtest_sancheong/` 39번. 산불이 peak 위험도 **1.88배**, 절대문턱 0.05%에서 **8h 앞당김** |
| ✅ A-6 | (선택) ML 보정을 physics 위에 | **평가 후 기각** — 공간CV에서 유의한 개선 없음(p=0.074). 43번 참조 |
| A-3′ | FoS→확률 시그모이드 k 실측 보정 | **발생부 좌표 필요** (산림청 요청 중) |

미보정 구간(시그모이드 k, 강우 계수, InSAR 임계, 배수 m₀)은 코드·문서에 provenance로
명시했고 백테스트 완료 시 실측으로 대체한다. **가상값을 성능처럼 제시하지 않는다.**

---

## 5. 파일

```
module_a_landslide/
  __init__.py       run()/explain() — 계약 진입점
  envelope.py       계약 정규화 + 공통 봉투 + 폴백 계층
  fos.py            무한사면 FoS + 산불계수 + 확률 + 몬테카를로 CI
  forecast.py       예보 시간강우 → hours_to_critical 전진적분 (a-htc)
  soil_sampler.py   좌표 → 부지 지반정수 (a-1, numpy만 사용)
  parameters.py     정밀토양도 → 지반정수 룩업 로더
  data/             문헌 출처 지반정수(가상값 없음) + 토양 코드사전
    sancheong_soil_grid_5m.npz  산청 지반정수 격자 5m (2.1MB, 33조합 인덱스+룩업)
    risk_polygons/    위험 폴리곤 시계열 GeoJSON(EPSG:5179) + index
    validation_andong/  안동 사전검증 산출물(방법론 검증 — 산청 참값 확보 전 단계)
  scripts/          데이터 준비·검증 파이프라인 01~15 (아래 §5-1)
  tests/            계약 6 + 물리 9 + 예보 11 + 토양/격자 11 = 37 passed
  README.md         이 문서
  DATA_SOURCES.md   출처·이중검증·라이선스
```

### 5-1. scripts/ — 재현 파이프라인

지반정수·지형·강우·산불 입력을 만드는 단계다. 대용량 원시자료(정밀토양도, 5m DEM,
Sentinel 원본)는 저장소에 없으므로 각 스크립트 상단의 경로를 자기 환경에 맞춰야 한다.

| 스크립트 | 하는 일 |
|---|---|
| `01_extract_soil_codes` | 정밀토양도 속성 → 코드사전 88개 분류 |
| `02_build_fos_parameter_table` | 코드 → 지반정수 번들(`data/fos_parameter_bundle.json`) |
| `03_sample_soil_at_points` | 좌표에서 토성·토심·배수 샘플링 |
| `04_fos_validation_auc` | 안동 인벤토리 대비 FoS AUC |
| `05_fos_upslope_buffer` | 발생부 편향 보정용 상류사면 버퍼 집계 |
| `06_plot_validation` | 검증 그림 |
| `07_dem_slope_validation` · `08_plot_dem_comparison` | DEM/경사 정밀도 대조 |
| `09_kma_rainfall_client` | 기상청 API허브 ASOS 시간강우 (키는 `.env`) |
| `10_plot_sancheong_goldentime` | 산청 골든타임 강우 그림 |
| `11_sentinel2_dnbr` | Sentinel-2 → dNBR (Copernicus/PC 직접 취득, GEE 미사용) |
| `12_sentinel1_acquire` | Sentinel-1 GRD 취득 |
| `13_clip_dem_5m` · `14_sancheong_slope` | 산청 DEM 클립 → 경사 |
| `15_sancheong_soil_grid` | 산청 지반정수 격자(`c_kpa`·`phi_deg`·`gamma`·`z_m`·`m0`) |
| `45_risk_polygons_timeseries` | 위험 폴리곤 시계열 GeoJSON 생성 (§3-4) |

**API 키는 전부 `.env`에서 읽는다 — 소스에 박지 말 것.**

`data/validation_andong/`은 **안동** 사전검증 산출물이다. 산청 발생부 참값을 못 구한
상태에서 방법론 자체(토양 샘플링 → FoS → AUC)가 도는지 먼저 확인한 단계이며,
산청 결과와 섞어 읽으면 안 된다.
