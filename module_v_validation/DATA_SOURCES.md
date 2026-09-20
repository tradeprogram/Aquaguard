# module_v_validation — 데이터 출처·검증 근거 (실데이터·개방)

## 관측(observed) 참값 데이터
| 참값 | 출처 | 라이선스 | tier |
|---|---|---|---|
| Sentinel-1 SAR 변화탐지 | Copernicus / Microsoft Planetary Computer RTC | 완전개방 | 1 |
| 산사태 인벤토리 | 안동 실태조사 DB(2021-2025) / 산청 피해기록 | 연구용 | 2 |
| 하천 수위 | 한강홍수통제소(HRFCO) | 무료·공개 | 3 |

## SAR 전처리(관측 폴리곤 생성, SPEC §1)
RTC(정밀궤도·열잡음·방사·지형보정, PC 완료) → 스펙클 median 7×7 → VV/VH log-ratio
dB=10log10(post/pre) → 임계(홍수: 표준 −2dB change / 산사태: 진폭변화·coherence 손실).
scripts: `19_module_v.py`(SAR IoU), `26_sar_flood_extent.py`(홍수범위).

## 오프라인 검증 산출물 (data/)
| 파일 | 내용 |
|---|---|
| `module_v_example.json` | 계약 예시 입출력(예측 vs SAR 관측) |
| `module_b_allrefs.json` | 홍수: SAR·HAND-FIM 3중 삼각검증 |
| `module_b_engine_comparison.json` | SFINCS vs ANUGA 교차 IoU 0.775 |

## 검증 결론 (정직)
- **하천범람(Module B)**: 2엔진 교차 IoU **0.775**·수위 RMSE 1.42m. 침수 IoU(vs SAR) 0.36은 초목 급경사 계곡 SAR 과소탐지 한계 — SAR(5.75km²) < 모델(8.5) < HAND-FIM(20)로 모델이 두 관측 사이(3중 참값으로 규명).
- **산사태(Module A)**: 피해기록은 발생부(source) 아니라 수용부 편향 → 공간 IoU 낮음. 발생부 좌표 확보가 유일 해결(산림청 요청서 발송 대기). 시점 검증(골든타임)은 견고.
- **data-leakage 차단**: predicted는 사건 이전 데이터로만 재실행, observed(사건 후)는 예측 입력 미사용. scripts 19·20에 명시.

## anti-pattern 방지 (ARCHITECTURE §15.6)
- IoU와 CSI 동일 개념 → 중복 금지. extent(IoU/F1)와 depth(RMSE) 분리.
- pixel split 아니라 event/spatial split(공간자기상관 과대평가 방지).

원칙: 실데이터만 · 출처 2중검증 · data-leakage 금지.
