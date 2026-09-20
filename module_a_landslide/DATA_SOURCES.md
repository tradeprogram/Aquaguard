# DATA_SOURCES — Module A 지반정수 출처·이중검증·라이선스

원칙(사용자 지침 2026-09-04): **가상·오류 데이터 금지, 실데이터·문헌값만, 출처
2중 검증, 우리 사례에 맞는 해외 선행연구.** 아래 모든 수치는 추적 가능하며,
표에 없는 분류는 "외삽(EXTRAPOLATED)"으로 명시했다.

## 1. 토성별 지반정수 (c', φ', γ, Ksat)

**P1 — 1차 출처 (우리 사례와 직결: 물리기반 얕은산사태 + 뿌리점착력)**
Frontiers in Forests and Global Change (2026), *"Quantifying vegetation effects on
landslide hazard using a physically based model"*, DOI **10.3389/ffgc.2026.1842027**, **Table 1**.
USDA 토성 → 유효점착력 Cs·마찰각 φ·단위중량 γs·Ksat, 뿌리점착력 Cr 0~5 kPa 시나리오,
토심 1/2/3 m 시나리오. → 8개 토성 값을 그대로 채택.

**P2 — 교차검증 (φ·γ 표준 compilation)**
PSU GEOL 615 *"Some Useful Numbers on the Engineering Properties of Materials"*
(Waltham, *Foundations of Engineering Geology* / Holtz & Kovacs 계열 표준값).
φ: Sand 30–40°, Gravel 35°, Silt 26–35°, Clay 20° / γ: Sandy 16, Silty 20, Clay 18,
Gravel 19 kN/m³. → P1 값이 이 범위 안에 있음을 확인.

**P3 — 한국 현장 실측 교차검증 (풍화화강토, PM '산성암' 우세지역과 일치)**
Hwangryeong Mt., Busan — MDPI *Sustainability* (2020) **12(7):2839**.
풍화토 c' 0.1–6.6 kPa(평균 2), φ' 32–39°(평균 36); 풍화암 c'=43.4 kPa, φ'=43.1°.
→ P1의 Sand/Loamy sand/Sandy loam c'(1.2/1.8/4.0)·φ'가 한국 실측 범위와 일치.

**3중 일치 확인** (예):

| 토성 | P1 c'/φ' | P2 φ | P3 현장 | 판정 |
|---|---|---|---|---|
| Sand 사질 | 1.2 / 30 | 30–40 | c'≈2, φ'36 | ✓ 일치 |
| Sandy loam 사양질 | 4.0 / 28 | (사질계) | ✓ | ✓ |
| Clay loam 식양질 | 8.7 / 20 | Clay 20 | — | ✓ |

**외삽 분류(문헌표에 없음 → 경향 보간, 명시)**: 식질(clay, P1 최세립 경향+P2 Clay),
역질(gravel, P2 Gravel), 사력질(sand~gravel 보간). provenance="EXTRAPOLATED".

## 2. 토심 z (파괴면)
정밀토양도 AD 유효토심 등급 중앙값: <20→0.2, 20–50→0.35, 50–100→0.75, >100→1.2 m.
근거: 얕은산사태 파괴면 = 토양–기반암 경계 = 유효토심 (TRIGRS/Infinite Slope 표준 가정).

## 3. 산불 증폭 f(dNBR, Δt)
ARCHITECTURE §2.5. A_max: low 1.2 / moderate 2.0 / high 3.5–4.0(중앙값 3.75), Δt<2년 감쇠없음.
근거: 산림청(화재 2년 후 토양유출 3–4배), KIGAM, USGS post-fire debris flow, Key&Benson(2006) dNBR 등급.

## 4. 미보정 파라미터 (provenance 명시, 백테스트로 대체 예정 — HANDOFF §9.3)
- FoS→확률 시그모이드 기울기 k(기본 6.0): 산청 백테스트로 보정.
- 강우→포화도 m 계수: 구조는 물리, 계수는 미보정.
- 배수등급→선행습윤 m₀: 모델링 가정(ASSUMPTION).
- InSAR 땅밀림 전조 임계 2 mm/day: §2.4 기반, 보정 대상.

## 5. 입력 데이터 라이선스 (2026-09 확인, 전부 무료·공개)
| 데이터 | 무료·공개 | 비고 |
|---|---|---|
| 정밀토양도(흙토람, 1:25,000) | ✅ 비영리·공익 무료분양(Shape/Grid) | API 30종 중 3종만 상업허용. 본 과제는 공문 확보분 사용 |
| DEM 5m(국토정보플랫폼) | ✅ 무료(회원가입) | 전국, 매년 갱신 |
| Sentinel-1/2(Copernicus/ASF) | ✅ 완전개방(상업이용까지) | GEE는 상업배포 시 유료 → 원본은 Copernicus/ASF 직접 |
| 강우·수위(WAMIS/HRFCO/기상청 API허브) | ✅ 무료(인증키) | 공공데이터 KOGL |

문헌 출처(P1–P3)는 오픈액세스/공개 자료.
