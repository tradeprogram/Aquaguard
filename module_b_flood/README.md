# module_b_flood — 하천범람 예측 (Track ① Module B)

§4.2 표준 진입점 `run(input: dict) -> dict` 하나를 노출한다. `contracts/module_b.{schema,example}.json` 준수.

## 구조 (module_a_landslide와 동일 패턴)
| 파일 | 역할 |
|---|---|
| `__init__.py` | `run()` / `explain()` — §4.2 공통 봉투 진입점 |
| `envelope.py` | **계약 경계** — 계약 필드명을 아는 유일한 곳, 입력 정규화 + 폴백 계층 |
| `flood.py` | 수문 모델(설명가능 로지스틱) — flood_prob·신뢰구간(MC 1000)·hours_to_critical |
| `fim.py` | 침수 범위 → GeoJSON FeatureCollection(EPSG:5179): SFINCS 래스터 폴리곤화 / HAND-FIM |
| `tests/` | pytest — 계약 준수·폴백 4계층·모델 단조성·MC 재현성 (15 통과) |

## 방법론
- **flood_prob**: 순수 ML 아님. 실측 수위·강우를 홍수특보 기준(150mm/24h)·실측 홍수사례로 보정한 로지스틱. `explain()`이 logit·보정근거 노출(설명가능성 §6.1).
- **물리 백본**: 자체 solver 금지. **Deltares SFINCS**(국지관성+subgrid, 1순위) / **ANUGA**(완전 2D 동파, 대체)로 오프라인 보정·검증.
  - 검증(산청 경호강 2025-07-19): **경호교 수위 RMSE 1.42m**, 2엔진 교차 IoU 0.775, SFINCS 2.5일 시뮬 43초.
- **inundation_extent_5179**: SFINCS/ANUGA 최대침수심 래스터 폴리곤화 또는 예측 수위 HAND-FIM. 지형 미주입 시 빈 FC + warning(정직).

## 폴백 계층 (§7)
| tier | 조건 | 처리 |
|---|---|---|
| 1 | 실측강우 + 수위 + SAR | 정밀(status=ok) |
| 2 | SAR 없음 | 강우+수위(degraded) |
| 3 | river_level 결측 | 강우만, 신뢰구간 확대 |
| error | reach_id 결측 | 하천구간 특정 불가, 안전 봉투 |

## 사용
```python
import module_b_flood as mb
out = mb.run({
  "reach_id": "GYEONGHO_01",
  "static": {"drainage_area_km2": 420, "river_order": 4, "slope_pct": 1.2},
  "dynamic": {"rainfall_cumulative_24h_mm": [300], "river_level_m": 8.67},
  "sar_water_extent": None,
  "_terrain": {"depth_raster": "models/anuga_reach/sfincs_maxdepth_50m.tif"}  # 선택: 실제 침수 폴리곤
})
```

원칙: 실데이터만 · 자체 solver 금지 · data-leakage 금지 · 예외로 죽지 않는다(§4.2).

---

## 추가 스크립트·산출물 (2026-09-20)

재현에 필요한데 빠져 있던 엔진 구축·비교 단계를 채웠다.

| 스크립트 | 하는 일 |
|---|---|
| `25_sfincs_build` | HydroMT-SFINCS 초기 모델 구축(광역) |
| `28_anuga_reach` · `32_anuga_reach_v2` | ANUGA 대체엔진 구간 모형 (v2가 최종) |
| `28b_rasterize_from_npz` | ANUGA 결과 npz → 최대침수심 래스터 |
| `30_plot_module_b` | 침수·수위 결과 플롯 |

`data/` 추가분 — `anuga_reach_*`(메타·수위 시계열), `anuga_*_maxdepth_*.tif`(ANUGA 최대
침수심, 2엔진 교차 IoU 0.775의 실제 입력), `sfincs_reach_wse.csv`(경호교 모의수위),
`hand_fim_meta.json`, `sar_flood_meta.json`, `module_b_validation.json`.

`figures/` — `module_b_result.png`, `module_b_sfincs_result.png`.

**저장소에 없는 것**: SFINCS 실행파일(Deltares freeware — 재배포 불가, 각자 다운로드),
5m DEM·HAND 래스터, subgrid 빌드 산출물(`scripts/33`으로 재생성). 대용량이거나
라이선스가 걸린 것들이라 의도적으로 뺐다.


## 서울 강남구 내수침수 모형 (2026-09-20 추가)

산청은 **하천범람**(상류 유량 + 하류 수위 경계)인데, 강남역 침수는 하천이 넘친 게
아니라 하수도 통수능을 넘긴 빗물이 저지대에 고인 **내수침수**다. 강제 방식 자체가
달라 별도 모형으로 만들었다.

| 스크립트 | 하는 일 |
|---|---|
| `47_gangnam_dem_manning` | 도별 5m DEM 모자이크 클립 + WorldCover → Manning n |
| `48_gangnam_sfincs_build` | SFINCS 빌드 — 강우 강제(precip) + 배수 상수(qinf) |
| `49_gangnam_postprocess` | 최대침수심 래스터 + 깊이밴드 폴리곤(산청과 같은 구간) |
| `50_gangnam_drain_sensitivity` | 배수율 30/50/75 mm/h 민감도 + 지점 점검 |

**제원** 도메인 강남구 + 500m 버퍼 10.83 × 9.87 km, 계산격자 20m(542×494),
5m DEM/Manning subgrid(4px), 시가지 56.2%.
**강우** 2022-08-08 KMA AWS 400(강남구) 실측 — 30시간 합계 374.0mm, 최대 92.5mm/h.

### 배수율 민감도 — 가정 하나가 결과의 8.3배를 좌우한다

| qinf | 0.3m↑ 침수면적 | 1.0m↑ | 최대침수심 |
|---|---|---|---|
| 30 mm/h | 1,954.6 ha | 741.7 ha | 10.41 m |
| 50 mm/h | 1,229.3 ha | 310.5 ha | 7.19 m |
| 75 mm/h | 234.9 ha | 20.3 ha | 3.65 m |

기본 산출물(`gangnam_inundation_5179.geojson`, `gangnam_maxdepth_20m.tif`)은 75 mm/h
케이스다. 셋 중 어느 값이 옳은지 고를 근거가 아직 없다 — 이 표는 정답 후보가 아니라
**불확실성 폭**이다.

### 지점 점검에서 드러난 한계

2022-08-08 침수가 보도된 지점의 모의 침수심(±40m 최대, m):

| 지점 | qinf 30 | qinf 50 | qinf 75 |
|---|---|---|---|
| 대치역/은마 | 1.87 | 1.17 | 0.49 |
| 삼성역 | 0.56 | 0.31 | 0.03 |
| 강남역 사거리 | 0.16 | 0.14 | 0.10 |

**대치·삼성 같은 지형 저지대는 재현되는데 강남역은 세 케이스 모두 0.1~0.2m 에
머문다.** 강남역 침수는 지형 저류가 아니라 관망 통수능 초과·역류로 생긴 것이라
상수 배수 모형이 구조적으로 못 잡는 유형이다. 배수율을 더 낮춰 억지로 맞추면 다른
지역이 과대침수된다 — 관망 모형이 있어야 한다.

### 한계 (요약)
- **하수관망 미반영.** 배수를 공간·시간 상수(qinf)로 대리했다.
- **미검증.** 서울시 침수흔적도를 확보해야 값을 고를 수 있다. 산청은 경호교 수위계로
  RMSE 1.42m 를 냈지만 여기엔 대응하는 참값이 아직 없다.
- 건물은 지형(DEM)에만 반영되고 별도 장애물로 넣지 않았다.

### 겪은 사고 하나 — 결측 DEM 이 만든 3,604m 침수심
첫 실행에서 최대 침수심이 **3,604m** 로 나왔다. `data/dem/서울_dem_5m_5179.tif` 가
① 원본 `dem_5m_서울특별시.tif` 와 배열은 같은데 transform 이 서쪽 163m·북쪽 1,646m
어긋난 손상본이었고, ② 서울 타일만 써서 강남 남단(세곡·자곡·율현)이 통째로 비어
도메인의 16% 가 `-9999` 였다. 그 값이 subgrid 지반고를 −3,598m 까지 끌어내렸다.
활성셀 마스크(msk)로는 걸러지지 않는다 — 그 셀들은 `msk==1` 이고 수위도 정상 5~6m
였다. 도별 원본 타일(서울특별시 + 경기도)은 행정경계에서 정확히 상보적이라 겹치면
결측이 0% 가 된다. 47번이 결측을 발견하면 멈추고, 49번도 지반고 범위를 따로
검사한다. 침수심을 조용히 잘라내면 모형이 멀쩡해 보이기 때문이다.

**저장소에 없는 것**: 강남 5m DEM 클립(14.5MB, 47번으로 재생성), SFINCS subgrid 빌드
산출물(48번으로 재생성), SFINCS 실행파일.
