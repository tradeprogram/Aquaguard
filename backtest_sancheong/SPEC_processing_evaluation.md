# AquaGuard 트랙① 처리·평가 사양서 (SPEC)

작성 2026-09-10 · 김민석(Kimminseok-01) · 원칙: 실데이터·문헌인용·출처2중검증·가상값 0
관련: [aquaguard-track1-guardrails], README 방법론(§ARCHITECTURE §5).

이 문서는 (1) Sentinel-1 SAR 전처리 하이퍼파라미터, (2) 평가지표 6종, (3) DEM 정밀도,
(4) 몬테카를로 설정, (5) 모델 분리를 **재현 가능하게 기록**한다.

---

## 1. Sentinel-1 SAR 전처리 파이프라인 (Module V — 예측 vs 실측 검증용)

도구: ESA SNAP (Sentinel-1 Toolbox) / snappy 또는 pyroSAR. 입력: GRD(진폭) — 홍수·산사태 진폭변화용.
(땅밀림 coherence는 SLC 별도 체인 §1.6.)

처리 순서(사용자 확정): **정밀궤도 → 열잡음 제거 → 방사보정 → 스펙클 처리 → 지형보정**

| # | 단계 | SNAP 오퍼레이터 | 하이퍼파라미터 | 값(권장/기본) | 출처·비고 |
|---|---|---|---|---|---|
| 1 | 정밀궤도 보정 | `Apply-Orbit-File` | orbitType | **Sentinel Precise (POEORB, Auto Download)** | ESA POEORB, 사건 후 ~20일 확정. 급하면 RESORB(restituted) |
| | | | polyDegree | **3** | SNAP 기본 |
| 2 | 열잡음 제거 | `ThermalNoiseRemoval` | removeThermalNoise | **true** | GRD 필수 |
| | | | selectedPolarisations | **VV, VH** | 홍수=VV 주, 산사태=VV+VH |
| 3 | 방사보정 | `Calibration` | outputBandName | **σ⁰ (sigma0)** | 홍수 수체탐지 표준 |
| | | | (지형효과 큰 산지) | β⁰ → §5 지형평탄화 → **γ⁰** | 급경사 산사태는 γ⁰ 권장 |
| | | | outputImageInComplex | false | GRD |
| 4 | 스펙클 처리 | `Speckle-Filter` | filter | **Refined Lee** | 단일영상 표준 |
| | | | windowSize | **7×7** | 5×5(디테일)~7×7(평활) 튜닝 |
| | | | (Lee Sigma 대안) | sigmaStr=0.9, targetWindow=3×3, numLooks=1 | 대안 필터 |
| | | | (시계열 다수 시) | **Multi-temporal Speckle Filter** | 스택이면 우선 |
| 5 | 지형보정 | `Terrain-Correction` (Range-Doppler) | demName | **외부 5m DEM** (국토정보플랫폼) | 미확보 시 Copernicus GLO-30(30m) |
| | | | demResamplingMethod | **BILINEAR_INTERPOLATION** | SNAP 기본 |
| | | | imgResamplingMethod | **BILINEAR_INTERPOLATION** | |
| | | | pixelSpacingInMeter | **10** (SAR 원해상도 매칭) | 5m DEM 시 10m 유지 |
| | | | mapProjection | **EPSG:5179** (UTM-K) | §4.1 내부좌표 규칙 |

**부가 처리(선택, 산지 홍수·산사태 정밀)**
- 5.5 방사지형평탄화 `Radiometric-Terrain-Flattening`(β⁰→γ⁰): 급경사 후방산란 왜곡 보정, DEM 필요.
- 스택 정합 시 `Subset`으로 AOI(산청/안동) 클립 후 처리(속도).

**변화탐지(전처리 후)**
- 홍수: 사건전/후 **log-ratio** 또는 σ⁰ 임계(Otsu 자동임계) — 물=낮은 후방산란(어두움).
- 산사태: 진폭변화(log-ratio) + (SLC 있으면) coherence 손실.

### 1.6 InSAR coherence 서브체인 (땅밀림 전조·산사태 실측, SLC 입력)
`Read(SLC)` → `Apply-Orbit-File` → `TOPSAR-Split`(sub-swath/burst) → `Back-Geocoding`(정합) →
`Enhanced-Spectral-Diversity` → `Interferogram`(coherence window **rg×az = 10×2** 또는 5×5) →
`TOPSAR-Deburst` → `GoldsteinPhaseFiltering`(alpha=1.0) → `Terrain-Correction`.
coherence 낮은(산림 decorrelation) 구역은 UI에 "관측불가" 명시(§2.4).

> ⚠️ 값들은 SNAP 표준/문헌 기본값이며 AOI별로 튜닝 가능. 최종 채택값은 산청·안동 처리 시
> 이 표에 실측 결과(입력 씬 ID·날짜 포함)와 함께 갱신한다. 임의 변경 금지, 변경 시 기록.

---

## 2. 평가지표 6종 (홍수·산사태 공통 평가 프레임) — 확정

**확정(2026-09-10): AUPRC · F1 · IoU · RMSE · FAR · POD** (6번째=POD, 사용자 확정).

| 지표 | 정의 | 무엇을 봄 | 주 적용 |
|---|---|---|---|
| **AUPRC** (PR-AUC) | Precision-Recall 곡선 아래 면적 | 희귀 양성 판별력(ROC보다 적합) | 산사태·홍수 확률 |
| **F1** | 2·P·R / (P+R) | 정밀도·재현율 균형(이진) | 산사태·홍수 extent |
| **IoU** | (예측 ∩ 실측) / (예측 ∪ 실측) | 공간 겹침 정확도 | 홍수·산사태 폴리곤 |
| **RMSE** | √(Σ(예측−실측)² / n) | 연속값 오차 | 홍수 수심 vs 관측수위, 확률 보정 |
| **FAR** | FP / (TP+FP) = 오경보 비율 | 헛경보 정도 | 경보 신뢰성 |
| **POD** | TP / (TP+FN) = 탐지율(Recall) | 실제 재해를 놓치지 않는 정도 | 경보 누락 방지 |

> POD·FAR는 짝(탐지율 vs 오경보) — 함께 보고. AUPRC로 확률판별, IoU/F1로 공간일치,
> RMSE로 크기(수심/수위) 검증. class imbalance 큰 산사태는 AUPRC·POD 우선.

**지표 선택 원칙(ARCHITECTURE §15.6 준수)**
- IoU와 CSI는 개념상 동일 → 중복 제시 금지.
- extent(공간일치, IoU/F1)와 depth(수위정확도, RMSE)는 **분리** 검증.
- 산사태는 극심한 class imbalance → accuracy 대신 AUPRC/POD/Brier 우선.
- 공간검증은 random pixel split 아니라 **event/spatial split**(공간자기상관 과대평가 방지).
- FAR 정의: 여기선 **False Alarm Ratio = FP/(TP+FP)**. (기상학 fall-out FP/(FP+TN)과 구분해 명시.)

---

## 3. 지형(DEM) 정밀도 — 3D 홍수·산사태 예측 요구사항

3D 예측·지형보정·경사 정밀도의 근간이므로 **정밀 topography 필수**.

| 항목 | 현재 | 목표(최종) |
|---|---|---|
| DEM 해상도 | Copernicus GLO-30 (30m, 무료·무로그인) | **국토정보플랫폼 5m** (로그인 다운로드) |
| 경사(β) | 30m DEM 또는 토양도 경사등급 | 5m DEM 연속경사 |
| 파생지표 | (예정) | **slope·TWI·curvature** 5m 산출 |
| 지형보정 DEM(§1-5) | GLO-30 | 5m |

- 30m는 급사면 발생부를 뭉갬(안동 검증 AUC 천장 원인) → **5m가 R 상승 핵심 레버**.
- SFINCS(홍수)·무한사면(산사태) 모두 정밀 DEM에 직접 의존.
- 3D 시각화(MapLibre/deck.gl)도 5m 지형 메시 사용.

---

## 4. 몬테카를로 (불확실성 정량화, 필수)

**무작위 반복 반드시 수행하고 반복횟수를 기록한다.**

| 항목 | 값(사양) | 비고 |
|---|---|---|
| 반복 횟수 | **1,000 회 (천 단위)** | 현재 코드 기본 n_mc=500 → 사양 표준 1,000으로 상향 |
| 빠른 모드 | 500 회 | 개발·디버그용 |
| 난수 seed | **고정(42)** | 재현성 |
| 섭동 변수 | c′(±30%), φ′(±2.5°), z(±20%) | 문헌 불확실성 범위(정규분포 샘플) |
| 출력 | landslide_prob 분포 → 신뢰구간 [5%, 95%] | 계약 confidence_interval |
| 산출물 기록 | 실행 시 n·seed를 결과 JSON에 명시 | provenance |

> 모든 확률/취약성 산출물은 "몬테카를로 N=1,000, seed=42"를 메타에 반드시 기록.

---

## 5. 모델 분리 (사용자 확정)

두 재해는 **서로 다른 물리**로 완전히 분리한다.

| | 산사태 (Module A) | 하천범람 (Module B) |
|---|---|---|
| 물리 | **무한사면 안전율(FoS)** 한계평형 | **SFINCS**(국지관성 축소천수) 1순위 / ANUGA 대체 |
| 물의 처리 | 포화도 m (간극수압) — 흐름 안 풂 | 수심·유속 — 흐름 풂 |
| 매닝 조도계수 | **없음** | **있음**(마찰항 S_f=n²u|u|/h^(4/3)) |
| 핵심 입력 | 경사·토성·토심·강우·dNBR | DEM·강우·하천수위·조도(토지피복) |
| 좌표 | EPSG:5179 내부 | EPSG:5179 내부 |

- Module A = 자체 구현(이론은 TRIGRS 원리 표준), Module B = SFINCS 재사용(자체 solver 금지).
- 두 모듈 output은 공통 봉투(§4.2)로 통일하되 물리는 절대 섞지 않음.

---

## 6. Module B (하천범람 SFINCS) 상세 사양 — 확정 (2026-09-17)

**모델:** SFINCS (Super-Fast INundation of CoastS, Deltares) — 국지관성 축소천수방정식
(Bates et al. 2010 local inertia; Leijnse et al. 2021 subgrid). **자체 solver 금지, 바이너리 재사용.**
**환경:** conda env `sfincs` + HydroMT-SFINCS(모델 빌드) + sfincs.exe(Deltares 공식 Windows 빌드).

### 6.1 입력 데이터 (전부 실데이터·개방)
| 입력 | 파일 | 출처·검증 |
|---|---|---|
| 지형 dep | `data/dem/산청_dem_5m_5179.tif` | 국토정보플랫폼 5m (res 4.997m) |
| 조도 Manning n | `data/hydro/sancheong_manning_5m_5179.tif` | ESA WorldCover 2021 v200(10m,STAC) → n 룩업 |
| 강우 강제 | `data/hydro/sfincs_precip_basinmean.csv` | HRFCO 강우 42소 유역평균 **누적 546.9mm**, 시간최대 30.2mm@07-19 12시 |
| 하류 수위경계 | `data/hydro/sfincs_downstream_bnd.csv` | HRFCO 진주덕천교(2018688) 실측수위 |
| 검증 참값(내부수위) | `data/hydro/sfincs_validation_wl.csv` | HRFCO 경호교·수산교·고읍교·소이교·원리교·묵곡교 실측수위/유량 |

### 6.2 Manning 조도계수 룩업 (문헌 중앙값, 임의변경 금지)
출처: Chow(1959) *Open-Channel Hydraulics* Table 5-6; Arcement & Schneider(1989) USGS WSP 2339.
WorldCover클래스→n: Tree(10)=0.120, Shrub(20)=0.060, Grass(30)=0.035, Crop(40)=0.040,
Built(50)=0.050, Bare(60)=0.025, Water(80)=0.030, Wetland(90)=0.050. 기본 0.040.
산청 분포: 산림 77%(n=0.12), 격자평균 n≈0.102 / 중앙값 0.12.

### 6.3 격자·수치 설정
| 항목 | 값 | 비고 |
|---|---|---|
| 계산격자 | **50 m** | 속도·안정 |
| subgrid | **10 서브픽셀(≈5m)** | 하도 표현(5m DEM+Manning) |
| 좌표 | EPSG:5179 | §4.1 내부좌표 |
| 이벤트 | 2025-07-18 00 ~ 07-21 00 (KST) | 피크 07-19 13~14시 |
| tref/dtout | tref=tstart, dtout=3600s, dthisout=600s | 출력간격 |
| 강제 | 강우(공간균일 유역평균) + 하류 수위경계 | 상류 유량(fw)은 옵션 src |

### 6.3.1 엔진 선정 경과 (2026-09-17)
- **SFINCS(1순위) 바이너리 미확보**: Deltares 공식 배포(download.deltares.nl)가 **로그인/가입 필수** →
  AI가 계정생성·로그인 불가(안전규칙). GitHub 릴리스 asset 없음, Docker·gfortran 부재.
  HydroMT-SFINCS 모델은 빌드 완료(`models/sancheong_sfincs`, 격자 618×762@50m+subgrid) — 사용자가
  Deltares 무료가입 후 바이너리 받으면 즉시 실행 가능. (참고: `sfincs-jax`는 동명 플라즈마 솔버로 무관)
- **대체엔진 ANUGA 채택**: SPEC §5 "SFINCS 1순위 / ANUGA 대체" 및 사용자 원칙("비슷한 해외 모델 쓰고")
  에 근거. ANUGA(호주 ANU/Geoscience Australia, 완전 2D 천수 유한체적) — conda-forge 개방, 로그인 불필요.
  자체 solver 아님(기성 오픈모델 재사용).

### 6.3.2 ANUGA 구간모델 결과 (경호강 고읍교→수산교, scripts 27·28·31)
상류 고읍교 유량유입(peak 3019㎥/s) + 하류 수산교 WSE경계. 검증: 경호교 WSE + Sentinel-1 침수 IoU.
공정 평가역: HAND(하천고도기준높이, Nobre 2011)<5m 범람가능 저지대만(사면·레이더그림자 제외, scripts 31).

| 버전 | 격자·시간 | 경호교 WSE RMSE | 피크차 | 침수 IoU(HAND) | F1 | FAR |
|---|---|---|---|---|---|---|
| 1차(dry-start) | 150m·16h | 4.76m | +4.47m/+3h지연 | 0.43 | 0.60 | 0.35 |
| **개선(spin-up)** | **100m·40h(31h spin-up)** | **2.48m** | **+2.91m** | **0.42** | **0.60** | **0.31** |

- **개선 핵심**: full spin-up(07-18 06시 시작→채널 미리 채움)로 dry-start 제거 → **피크시각 07-19 13시 정확 일치(모의 94.01 vs 관측 94.12m, -0.11m)**, RMSE 절반↓.
- **남은 한계(정직)**: 감쇠부 배수가 느림(관측보다 높게 유지)→피크 후 +2.9m, POD 0.52(SAR 지류는 단일 상류유입으로 미충족). 
- 산출: `outputs/module_b_validation.json`, `module_b_result.png`, `models/anuga_reach/anuga_maxdepth_100m.tif`.

### 6.3.3 고도화 실험 결과 (정직 보고, 2026-09-17, scripts 31·32)
사용자 요청(50m 세분 + 지류 다중유입) 시도 → **ANUGA에선 오히려 악화. v1이 최선.**
| 시도 | IoU | POD | FAR | WSE RMSE | 판정 |
|---|---|---|---|---|---|
| **v1 100m 단일유입+spin-up** | **0.42** | 0.52 | **0.31** | **2.48m** | **최선(공식)** |
| v2 100m 다중유입(회랑) | 0.34 | 0.67 | 0.60 | 3.33m | POD↑나 과충전→FAR·WSE 악화 |
| 50m 세분 | — | — | — | — | 명시적 동파+급경사 CFL로 40h≈5.5h(비실용) |

- **다중유입**(질량보존 +1971㎥/s): 탐지율(POD)은 올렸으나 **ANUGA 배수가 느려 과충전** → 침수 과대(FAR 0.60)·WSE +4.2m. 순효과 음(-).
- **50m 격자**: ANUGA(완전 2D 동파, 명시적)는 급경사서 CFL 시간스텝 초저속 → 회랑 80k삼각형 40h에 ~5.5h. 비실용.
- **근본 교훈**: 두 문제(세밀격자 비용·과충전 배수) 모두 **SFINCS가 축소물리(국지관성)+subgrid+빠른 conveyance로 설계상 해결**. → IoU>0.5는 SFINCS(사용자 Deltares 로그인) 또는 ANUGA 정밀보정(Manning·배수경계, 반복비용 큼)이 정도.
- HAND 회랑/다중유입 지오메트리: scripts 31·32a, `data/hydro/reach_corridor.geojson`, `reach_inflow_points.json`.

### 6.3.4 ★SFINCS 1순위 실행 완료 (2026-09-17, scripts 33·34·34b·35·36)
사용자가 Deltares 무료가입→SFINCS v2.4.0 Galibier freeware exe 확보→실행. 동일 참값·구성으로 ANUGA와 공정비교(공통 50m격자).
| 엔진 | IoU | F1 | POD | FAR | **WSE RMSE** | 피크오차 | 실행시간 |
|---|---|---|---|---|---|---|---|
| ANUGA v1 | 0.359 | 0.529 | 0.676 | 0.566 | 2.48m | +2.91m | 수 시간 |
| **SFINCS(50m+subgrid)** | 0.363 | 0.533 | 0.664 | 0.555 | **1.42m** | **-0.80m** | **43초** |

- **SFINCS 압승: WSE RMSE 1.42m(관측게이지 대비, 깨끗)·피크 -0.8m·2.5일 시뮬 43초**(ANUGA 수시간). subgrid로 세밀지형+빠른배수 → ANUGA의 두 한계(느린배수·격자비용) 해소.
- **침수 IoU는 두 엔진 동일(~0.36)** → **병목=SAR 참값**(초목 우거진 급경사 산청계곡서 SAR 침수탐지 원천적 불안정; 임계 -1~-2dB 무관하게 0.36~0.37). **독립적 두 물리엔진이 ~8.5km²로 일치**하는 것 자체가 강한 교차검증.
- 최종 판정: **경호교 수위 RMSE 1.42m가 Module B의 핵심 검증(양호)**. 침수 IoU는 SAR 한계로 캡. 산출 `outputs/sfincs_reach_validation.json`, `module_b_engine_comparison.json`, `module_b_sfincs_result.png`, `models/anuga_reach/sfincs_maxdepth_50m.tif`.
- 모델 위치(ASCII): `scratchpad/sfincs_reach`. env sfincs(pandas 2.3.3). exe: `data/SFINCS/.../SFINCS_v2.4.0_Galibier_release_exe/sfincs.exe`.

### 6.4 검증 (SPEC §2 지표 적용)
- **수심/수위 RMSE**: 모의 수심 → 관측소 수위(경호교 등)와 비교(depth 검증).
- **침수범위 IoU/F1/POD/FAR**: Sentinel-1 홍수탐지(σ⁰ log-ratio, Otsu) vs 모의 침수. (Module V 연계)
- 실측 홍수피크: 경호교 8.67m(유량 4606㎥/s), 수산교 10.39m(4990㎥/s) @ 07-19 13~14시.
- ⚠ 하정리(2018665)는 표고기준 이상치(수위 136m) → 검증 제외.

---

## 변경 이력
- 2026-09-10 최초 작성 (사용자 사양 확정): SAR 5단계 하이퍼파라미터, 지표 6종(6번째 미확정),
  DEM 5m 목표, 몬테카를로 1,000회, A/B 분리.
- 2026-09-17 §6 Module B(SFINCS) 상세 사양 추가: 입력 5종 실데이터 확보(HRFCO 수위57/강우42소,
  WorldCover Manning, DEM 5m), Manning 룩업(Chow1959/USGS), 격자 50m+subgrid, 이벤트·검증 정의.
