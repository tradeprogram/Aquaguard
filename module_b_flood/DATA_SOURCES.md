# module_b_flood — 데이터 출처·보정 근거 (실데이터·개방, 가상값 0)

## 입력·검증 데이터 (전부 무료·공개)
| 데이터 | 출처 | 라이선스 | 용도 |
|---|---|---|---|
| DEM 5m | 국토정보플랫폼 | 무료·공개 | 지형(dep), subgrid, HAND |
| Manning 조도 | ESA WorldCover 2021 v200 (10m) | 개방(CC-BY) | 마찰항 n |
| 하천 수위·유량 | 한강홍수통제소(HRFCO) OpenAPI | 무료·공개(누구나) | 유입·경계·검증 (경호교 등 57소) |
| 강우 | 기상청 ASOS + HRFCO 강우 42소 | 무료·공개 | 강제/강우 |
| Sentinel-1 SAR | Microsoft Planetary Computer RTC | 완전개방 | 침수범위 관측 검증 |
| SFINCS 솔버 | Deltares (download.deltares.nl) | **Freeware(무료)** | 침수 물리모형(1순위) |
| ANUGA | ANU/Geoscience Australia (conda-forge) | 오픈소스 | 대체 물리모형 |

## flood.py 보정 파라미터 근거
| 상수 | 값 | 근거 |
|---|---|---|
| `L_REF` | 3.0 m | 일반 하천 주의수위 수준(HRFCO 홍수특보 attwl 관례) |
| `R_REF` | 150 mm/24h | 기상청 호우경보 수준 |
| `SLOPE_WL`, `SLOPE_R` | 0.70/m, 0.008/mm | 실측 재현 보정: 산청 경호강 피크 수위 8.67m·강우≈300mm → prob≈0.99, 계약 예시 3.2m·187mm → 0.61 |
| `MC_N`, seed | 1000, 42 | SPEC §4 (몬테카를로 필수·재현성) |

## 물리 검증 산출물 (오프라인)
- `outputs/module_b_engine_comparison.json` : SFINCS vs ANUGA (공통 50m격자)
- `outputs/module_b_allrefs.json` : SAR·HAND-FIM 3중 참값 삼각검증
- `models/anuga_reach/sfincs_maxdepth_50m.tif` : SFINCS 최대침수심(EPSG:5179)
- 스크립트 22~38 (data/hydro 입력 → 빌드 33 → 실행 34 → 검증 35·38)

**검증 요약**: 경호교 수위 RMSE **1.42m**(피크 −0.8m), 2엔진 교차 IoU **0.775**. 침수 IoU(vs SAR) 0.36은 초목 급경사 계곡 SAR 과소탐지 한계(모델 문제 아님, 3중 참값으로 규명).

원칙: 실데이터만 · 문헌·기관 출처 2중검증 · 자체 solver 금지.
