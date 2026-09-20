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

