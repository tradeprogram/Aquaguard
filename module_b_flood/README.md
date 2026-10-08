# module_b_flood — 하천범람 예측 (Track ① Module B)

§4.2 표준 진입점 `run(input: dict) -> dict` 하나를 노출한다. `contracts/module_b.{schema,example}.json` 준수.

## 구조 (module_a_landslide와 동일 패턴)
| 파일 | 역할 |
|---|---|
| `__init__.py` | `run` / `explain` — §4.2 공통 봉투 진입점 |
| `envelope.py` | **계약 경계** — 계약 필드명을 아는 유일한 곳, 입력 정규화 + 폴백 계층 |
| `flood.py` | 수문 모델(설명가능 로지스틱) — flood_prob·신뢰구간(MC 1000)·hours_to_critical |
| `fim.py` | 침수 범위 → GeoJSON FeatureCollection(EPSG:5179): SFINCS 래스터 폴리곤화 / HAND-FIM |
| `tests/` | pytest — 계약 준수·폴백 4계층·모델 단조성·MC 재현성 (15 통과) |

## 방법론
- **flood_prob**: 순수 ML 아님. 실측 수위·강우를 홍수특보 기준(150mm/24h)·실측 홍수사례로 보정한 로지스틱. `explain`이 logit·보정근거 노출(설명가능성 §6.1).
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

## 침수 모형 영역 (2026-10-08)

`domains.json`이 침수 모형 영역 목록이다. 침수 래스터는 nodata=0이라 "안 잠김"과 "계산 안 함"이
같은 값이어서, 어디까지 계산했는지를 래스터 밖에서 따로 둔다(`domains.py`).

| id | 영역 | 상태 | 시간축 |
|---|---|---|---|
| `gyeongho_reach` | 경호강 구간(고읍교~수산교) | 계산됨 | 경호교 수위 → 시각별 침수 |
| `deokcheon_upper` | 덕천강 상류(시천·삼장) | 계획 | 수위 관측소 없음 → 최대 범위만 |

- 래스터 파일이 있는 영역만 '계산됨'이다. 저장본(`scripts/build_demo_snapshot.py`)은 계산된
  영역을 모두 읽어 지도·고립 판정·계산 범위에 반영한다.
- 두 영역이 겹치면 **목록 앞쪽이 우선**이다. 경호강 구간은 수위계로 검증됐고(RMSE 1.42m),
  덕천강 상류는 검증할 참값이 없다. 뒤 영역의 표시 폴리곤은 앞 영역 사각형 밖으로 잘린다.
- 시간축(수위 곡선)이 있는 영역은 1개만 지원한다.
- 실시간 경보 경로(오케스트레이터 → Module B·D)는 여전히 경호강 래스터 1장만 쓴다.

### 덕천강 상류 모형 실행 (G: 드라이브 PC)
입력(DEM 5m, Manning, 유역평균 강우)이 G: 드라이브에 있어 그 PC에서 돌린다.

1. `python module_b_flood/scripts/33d_sfincs_build_deokcheon.py --dry-run` — 격자와 입력 확인
2. `set AQUAGUARD_SFINCS_ROOT=C:\sfincs_deokcheon` (ASCII 경로 — netCDF 한글경로 버그)
3. `conda run -n sfincs python module_b_flood/scripts/33d_sfincs_build_deokcheon.py` — 모형 빌드
4. 빌드 폴더에서 `sfincs.exe` 실행 → `sfincs_map.nc`
5. `python module_b_flood/scripts/33d_sfincs_build_deokcheon.py --postprocess %AQUAGUARD_SFINCS_ROOT%\sfincs_map.nc`
   → `module_b_flood/data/sfincs_deokcheon_maxdepth_50m.tif`
6. `domains.json`의 `deokcheon_upper.status`를 `"computed"`로 고친다.
7. `python scripts/build_demo_snapshot.py` — 저장본을 다시 만든다.

격자: 시천면 ∪ 삼장면 경계 + 1km, 50m, 383×425. 강우 강제·outflow 경계라 수위 관측소 검증은 없다.

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

