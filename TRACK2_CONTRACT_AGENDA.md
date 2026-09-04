# 트랙② 계약 회의 안건 (Day 1)

나정우(트랙②)가 Module C·D를 구현하면서 발견한, **4인 합의가 필요한 항목**들.
`contracts/`는 §4.3에 따라 합의 없이 수정하지 않았고 README.md·ARCHITECTURE.md도
건드리지 않았다 — 전부 여기에만 기록한다.

---

## 1. Module A의 계약 출력에 위험 폴리곤 필드가 없다 (최우선)

`contracts/module_a.example.json`의 output은 `location: {x_5179, y_5179}`, 즉 **점**이다.
그런데 `contracts/module_d.example.json`의 input은 `risk_polygons[].geometry_5179`로
**폴리곤**을 기대한다. 사이를 잇는 Module O는 실제로 이렇게 넘기고 있다
(`module_o_orchestrator/orchestrator.py`):

```python
{"source_module": "A", "geometry_5179": landslide.get("location", {}), "risk_prob": ...}  # 점 dict
{"source_module": "B", "geometry_5179": {}, "risk_prob": ...}                             # 빈 dict
"building_footprints_5179": {}, "farmland_parcels_5179": {}                               # FC 아님
```

Module O의 버그가 아니라 계약의 빈틈이다 — A가 폴리곤을 안 내놓으니 O가 넘길 게 없다.
Module B는 `inundation_extent_5179`(FeatureCollection)를 갖고 있지만 O가 D로 전달하지 않는다.

**트랙②의 임시 대응**: Module D가 점을 반경 100m로 버퍼링해서 흡수한다. 단 반드시
`status: degraded` + warning + `explain()`에 ASSUMPTION으로 표시한다
(`policies/module_d.json`의 `point_buffer_radius_m`, status=PLACEHOLDER).

**결정이 필요한 것**
- Module A 계약에 `risk_polygon_5179`(또는 `risk_extent_5179`)를 추가할 것인가?
  추가한다면 A가 FoS 격자에서 어떻게 폴리곤을 뽑을지는 트랙①이 정한다.
- 아니면 점→폴리곤 변환을 어느 모듈의 책임으로 둘 것인가 (A / O / D)?
- Module B의 `inundation_extent_5179`를 O가 D로 전달하도록 O를 고칠 것인가? (트랙③)

**결정 전까지**: D의 버퍼 경로가 계속 degraded를 내므로 Module O의 `fallback_tier`가
항상 2 이상으로 올라간다. 데모에서 "정상" 배지가 안 뜨는 원인이 여기다.

---

## 2. `contracts/module_d.example.json`의 input이 output을 만들 수 없다

input은 `coordinates: []`, `features: []`로 전부 비어 있는데 output에는 건물 `B12345`와
`exposed_farmland_ha: 4.2`가 있다. 빈 입력에서 이 출력이 나올 수 없다.

Module C는 example의 input→output이 실제로 재현되지만(`45 × 1.30 × 1.15 = 67.275 ≥ 50 → "위험"`)
D는 구조적으로 불가능하다. 그래서 D의 테스트는 두 갈래로 나눠뒀다:
- `test_contract_example_input_cannot_produce_its_own_output` — 이 불일치 자체를 고정
- `test_documented_output_is_reproducible_from_real_coordinates` — 실좌표 픽스처
  (위험영역 300×300m, 농경지 교차 210×200m = 42,000㎡ = **정확히 4.2ha**)로 문서화된
  output data를 정확히 재현

**제안**: example.json의 input에 실좌표를 채워 자기 output을 재현하게 만든다. 위 픽스처
좌표를 그대로 쓰면 된다(`module_d_exposure_overlay/tests/conftest.py`의 `documented_case`).
계약 파일 수정이므로 4인 합의 필요. 합의되면 위 첫 번째 테스트는 삭제하고 두 번째를
계약 재현 테스트로 승격한다.

---

## 3. §7 폴백 계층 표에 Module C·D 행이 없다

README §7 / ARCHITECTURE §7의 표에는 A·B·V·H만 있다. C와 D는 트랙②가 아래처럼 정의해
구현했다 — 문서 반영은 합의 후에 한다.

| 모듈 | 1순위 | 2순위 | 3순위 |
|---|---|---|---|
| C 도로·지하차도 | 입력 4개 정상 | `drainage_capacity_class`/`known_risk` 결측·부적합 → 보수적 기본값(low/true) | `rainfall_intensity_1h_mm` 결측·부적합 → `known_risk`만으로 최소 등급 |
| D 노출자산 | 위험 폴리곤·건물·농경지 모두 정상 | 점 버퍼 대체, 무효 지오메트리 제외·복구, 컬렉션 형식 오류 | 쓸 수 있는 위험 지오메트리 없음 → 노출 0건 |

C는 `underpass_id` 결측, D는 입력 구조 자체가 깨진 경우를 `status: "error"`로 둔다.
어느 경우에도 스키마를 만족하는 봉투를 내고 예외를 던지지 않는다(§4.2).

---

## 4. 저장소 최상위에 `policies/` 디렉토리를 추가했다 (보고 사항)

ARCHITECTURE §8 디렉토리 구조에 없는 디렉토리다. **계약 변경은 아니다** — 트랙② 내부
정책값(점 버퍼 반경, use_type 어휘 등)이 사는 곳이고 4인 합의 대상이 아니다.

최상위에 둔 이유: `exposed_buildings[].use_type`이 곧 Module G의 원단위 테이블 키인데
(O가 `call_module("g", {**exposure, ...})`로 D 출력을 G 입력에 펼친다), 이 어휘 파일을
D 패키지 안에 두면 G가 D에 의존하게 되어 §4.2의 모듈 독립성이 깨진다. 자세한 건
`policies/README.md`.

Module C의 임계값 룰셋은 `module_c_urban_rule/rulesets/`에 남아 있다(C는 공유할 정책이
없어서). 통일이 필요하다고 판단되면 그때 옮긴다.

---

## 5. Module O가 Module C를 호출하지 않는다 (트랙③ 확인 요청)

`orchestrator.py`는 a/b/d/e/g/h만 부르고 c가 없다. 한편 `ui/src/lib/types.ts`에는
`road_flooding?: UnderpassAlert[]`로 **배열** 타입이 준비돼 있는데 C의 계약은 지하차도
1건 단위다. 여러 지하차도를 누가 순회할지가 미정이다.

트랙②는 계약 밖 편의 함수 `run_many(inputs) -> list[envelope]`를 C에 넣어뒀다(한 건이
실패해도 나머지 보존). 실제 연결 방식은 트랙③이 정하면 맞춘다.

---

## 6. 출처 확보가 남은 임계값 (트랙② 자체 과제, 합의 불필요)

| 파일 | 행 | 현재 status | 필요한 것 |
|---|---|---|---|
| `module_c_urban_rule/rulesets/v1_kma_mois.json` | `cutpoint_주의`/`cutpoint_경계` | DERIVED | 기상청 호우특보 기준 공식 페이지 URL (3시간 60/90mm) |
| 〃 | `cutpoint_위험` | CONFIRMED_COMPONENT | 계약에 `rainfall_cumulative_3h_mm`가 추가되면 CONFIRMED로 승격 가능 → **1번 안건과 함께 논의** |
| 〃 | `known_risk_min_level` | POLICY_CONFIRMED_DIRECTION | 행안부 1차 자료(보도자료·TF 회의자료) URL. 보도 2건은 접속 검증 완료 |
| 〃 | `drainage_factor`, `known_risk_factor` | PLACEHOLDER | 공식 출처 없음 — 없으면 TEAM_DECISION으로 내리는 것도 방법 |
| `policies/module_d.json` | `point_buffer_radius_m` | PLACEHOLDER | 1번 안건이 해결되면 이 행 자체가 폴백 전용으로 전락 |
| `policies/use_type_vocabulary.json` | `source_value_mapping` | PLACEHOLDER | 실제 건축물대장 주용도 값 분포 확인 후 교체 |
