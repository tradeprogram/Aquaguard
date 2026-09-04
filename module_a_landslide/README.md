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

**구현 완료** (`pytest module_a_landslide/tests/ -q` → 15 passed):
- `fos.py` — FoS 물리, 산불 f(dNBR,Δt), FoS→확률 시그모이드, 몬테카를로 CI
- `parameters.py` — 토양도 지반정수 룩업 + 강우→포화도 m
- `envelope.py` — 계약 정규화 + §7 폴백(tier 1 InSAR / 2 지형 / 3 예보) + graceful degradation
- `__init__.py` — `run(input)->dict`(§4.2 공통 봉투) + `explain()`(§6.1 Provenance)

**물리 검증** (산청 2025-07-19 조건: 경사 32.5°, dNBR high, 187mm/24h):
- 사질 풍화토 주입 → **FoS 0.637 (<1) → landslide_prob 0.898, CI[0.81,0.94]** (고위험, 물리 정상)
- 단조성 테스트 통과: 경사↑·포화↑·산불등급↑ → 위험↑

**정직성**: 계약 input에는 토성·토심이 없다 → Module A가 좌표에서 토양도를 샘플링해야 함.
전국 토양도 shapefile은 대용량이라 미커밋 → 부지 미샘플 시 전국 대표 폴백값 사용 +
`warnings`·`fallback_tier`로 명시(module_c의 PLACEHOLDER 정직성과 동일).

---

## 4. 다음 단계 (staged plan)

| 단계 | 작업 | 의존(필요 데이터) |
|---|---|---|
| A-1 | 정밀토양도 샘플러 연결(좌표→토성·토심·배수) | 디스크 토양도(확보) — 산청/안동 클립 |
| A-2 | 5m DEM으로 slope·TWI·curvature 정밀화 | 국토정보플랫폼 DEM(키 필요) |
| A-3 | 강우→포화도 m 계수 실측 보정 | 기상청 AWS·토양수분(일부 확보) |
| A-4 | LDAPS 예보 연동 → `hours_to_critical` 실제 시간 | 기상청 API허브(키 필요) |
| A-5 | FoS→확률 시그모이드 k 보정 + Ablation(±dNBR) | 산청 leakage-free 백테스트(HANDOFF §9.3) |
| A-6 | (선택) LightGBM/XGBoost 보정을 physics 위에 | A-1~A-5 완료 후 |

미보정 구간(시그모이드 k, 강우 계수, InSAR 임계, 배수 m₀)은 코드·문서에 provenance로
명시했고 백테스트 완료 시 실측으로 대체한다. **가상값을 성능처럼 제시하지 않는다.**

---

## 5. 파일

```
module_a_landslide/
  __init__.py       run()/explain() — 계약 진입점
  envelope.py       계약 정규화 + 공통 봉투 + 폴백 계층
  fos.py            무한사면 FoS + 산불계수 + 확률 + 몬테카를로 CI
  parameters.py     정밀토양도 → 지반정수 룩업 로더
  data/             문헌 출처 지반정수(가상값 없음) + 토양 코드사전
  tests/            계약 6 + 물리 9 = 15 passed
  README.md         이 문서
  DATA_SOURCES.md   출처·이중검증·라이선스
```
