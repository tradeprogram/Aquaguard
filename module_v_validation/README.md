# module_v_validation — 위성 검증 (Track ① Module V)

§4.2 표준 진입점 `run(input: dict) -> dict` 하나를 노출한다. `contracts/module_v.{schema,example}.json` 준수.

## 구조 (module_a/module_b와 동일 패턴)
| 파일 | 역할 |
|---|---|
| `__init__.py` | `run()` / `explain()` — §4.2 공통 봉투 진입점 |
| `envelope.py` | **계약 경계** — 계약 필드명을 아는 유일한 곳, 입력 정규화 + 폴백 계층 |
| `metrics.py` | 예측·관측 폴리곤 공통격자 rasterize → IoU/F1/precision/recall + confusion(TP/FP/FN) |
| `leadtime.py` | lead_time_min(관측시각 − 예측경보시각) = 골든타임 |
| `tests/` | pytest — 계약 준수·폴백 3계층·겹침 IoU(동일1.0/반겹침1/3/분리0)·lead_time (17 통과) |

## 방법론
- **공간 채점**: 예측(A/B의 geometry_5179)과 관측(Sentinel-1 SAR 변화탐지/인벤토리)을 같은 격자에 rasterize → TP/FP/FN → IoU·F1·P·R. confusion_geometry로 UI가 예측(빨강)·실측(파랑) 분리 표시.
- **★ data-leakage 금지**: observed(사건 후 취득)는 A/B '예측'을 만드는 데 **절대 안 씀**. 이 모듈은 이미 만들어진 예측을 관측으로 **사후 채점만** 한다(계약으로 A/B와 분리 → 순환 없음).
- **lead_time_min**: alert_id("AL-YYYYMMDD-HHMM") 또는 predicted.alert_timestamp에서 예측경보시각, observed.acquisition_timestamp에서 관측시각 → 분 단위 골든타임(양수=예측이 앞섬).

## 폴백 계층 (§7, 관측 참값 품질 순)
| tier | observed.type | 처리 |
|---|---|---|
| 1 | sentinel1_sar_change | SAR (정밀, ok) |
| 2 | landslide_inventory | 실측 인벤토리 (degraded) |
| 3 | river_gauge | 수위 점/선, 공간 IoU 제한 |
| error | alert_id/predicted/observed geometry 결측 | 안전 봉투 |

## 사용
```python
import module_v_validation as mv
out = mv.run({
  "alert_id": "AL-20250719-0915",
  "predicted": {"source_module": "B", "geometry_5179": {…FeatureCollection…}},
  "observed": {"type": "sentinel1_sar_change", "geometry_5179": {…FC…},
               "acquisition_timestamp": "2025-07-19T12:37:00+09:00", "source": "Copernicus Sentinel-1"}
})
# → {status, fallback_tier, data:{iou,f1,precision,recall,confusion_geometry_5179,lead_time_min}, warnings}
```

## 오프라인 검증 결과 (data/, DATA_SOURCES.md)
- 산청 하천범람: SFINCS/ANUGA 2엔진 교차 IoU **0.775**, 수위 RMSE 1.42m
- 산사태: 발생부 참값 부재로 SAR IoU 낮음(3중 참값으로 한계 규명 — 정직)

원칙: 실데이터만 · data-leakage 금지 · 공간자기상관 과대평가 방지(event/spatial split, §15.6).

---

## 추가 산출물 (2026-09-20)

- `data/module_v_confusion.tif` — TP/FP/FN 공간 분포 래스터(EPSG:5179). 계약의
  `confusion_geometry_5179`가 폴리곤으로 나가기 전 원본 격자다. UI가 예측(빨강)·
  실측(파랑)을 분리해 그릴 때 쓰는 그 값이 실제로 어디에 있는지 보여준다.
- `data/module_v_ndvi_metrics.json` — NDVI 변화 기반 대안 관측(`20_module_v_ndvi`)
  지표. SAR이 초목계곡에서 실패하는 구간을 광학으로 메울 수 있는지 본 시도다.

### 정직하게 — 산사태 쪽 수치

같은 파이프라인을 산사태에 적용하면 IoU 0.0038 · F1 0.0076 · AUPRC 0.0106
(기저 0.0097)로 **사실상 무기력하다**(`data/module_v_metrics.json`). 강우 후
토양수분·식생위상 변화가 SAR 진폭에 섞여 노이즈가 크고, 무엇보다 산사태 발생부
참값 자체가 없다. Module V는 만능이 아니라 **참값이 있는 홍수에서만 제 역할을 한다.**

홍수 쪽 결론은 유효하다 — SFINCS vs SAR IoU 0.32 · lead_time 217분이며, 주검증은
2엔진 교차 IoU 0.775와 수위 RMSE 1.42m다.

`lead_time_min` 217분의 기준은 **SAR 촬영시각(12:37 = 공식 경보 시각)**이고 실제
범람·붕괴 시각이 아니다. 이 둘을 섞으면 안 된다.

