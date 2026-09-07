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
| `module_c_urban_rule/rulesets/v1_kma_mois.json` | `cutpoint_주의`/`cutpoint_경계` | DERIVED | ~~공식 페이지 URL~~ **확보 완료**(기상청 기상특보 발표기준, 2026-09-04 접속 검증). 남은 가정은 3시간→1시간 균등환산뿐 |
| 〃 | `cutpoint_위험` | CONFIRMED_COMPONENT | 계약에 `rainfall_cumulative_3h_mm`가 추가되면 CONFIRMED로 승격 가능 → **1번 안건과 함께 논의** |
| 〃 | `known_risk_min_level` | POLICY_CONFIRMED_DIRECTION | 행안부 1차 자료(보도자료·TF 회의자료) URL. 보도 2건은 접속 검증 완료 |
| `module_h_citizen_verification/policies/v1_default.json` | `shrinkage_k` | PLACEHOLDER | **계약 예시 역산값(9.0)** — 검증된 신뢰도 모델이 아니다. 파일럿 응답 데이터로 재보정 필요 |
| 〃 | `confirm_threshold`, `false_positive_threshold` | PLACEHOLDER | 파일럿에서 오경보율·미탐율 확인 후 조정 |
| 〃 | `full_weight_min_reports` | PLACEHOLDER | §7이 '응답 다수/소수'만 말하고 숫자를 안 줘서 트랙②가 정한 값(3) |
| 〃 | `valid_window_min` | PLACEHOLDER | 경보 후 유효 시간창(60분). 근거 없는 초기값 |
| 〃 | `drainage_factor`, `known_risk_factor` | PLACEHOLDER | 공식 출처 없음 — 없으면 TEAM_DECISION으로 내리는 것도 방법 |
| `policies/module_d.json` | `point_buffer_radius_m` | PLACEHOLDER | 1번 안건이 해결되면 이 행 자체가 폴백 전용으로 전락 |
| `policies/use_type_vocabulary.json` | `source_value_mapping` | PLACEHOLDER | 실제 건축물대장 주용도 값 분포 확인 후 교체 |

---

## 7. Module H 계약에 경보 발송 시각 필드가 없다

`contracts/module_h.schema.json`의 input은 `alert_id` / `trigger_location` /
`trigger_radius_m` / `citizen_reports` 넷뿐이다. 그런데 output의
`response_latency_min`은 정의상 **경보 발송 → 시민 응답**까지의 시간이라, 입력에
경보 시각이 없으면 계산할 수가 없다.

`alert_id`가 `AL-20250719-0915`로 09:15을 암시하지만 그건 **네이밍 관습이지 계약
필드가 아니다.** 단서는 스키마에 있다 — `response_latency_min`만
`["number", "null"]`로 null을 명시적으로 허용한다(다른 세 필드는 아니다). 계약
설계자도 "모를 수 있는 값"으로 본 것이다.

**트랙②의 임시 대응** (3단 폴백):
1. 입력에 `alert_issued_at`(ISO8601 KST)이 있으면 그것 기준 — 스키마가 추가 속성을
   막지 않으므로 계약 위반은 아니다
2. 없으면 `alert_id`가 `^AL-([0-9]{8})-([0-9]{4})$`에 **엄격히** 맞을 때만 파싱하고
   반드시 `status: degraded`로 내린다(관습은 계약이 아니다)
3. 둘 다 안 되면 `null` + warning

**결정이 필요한 것**
- `alert_issued_at`을 Module H 계약의 정식 입력 필드로 올릴 것인가?
- 올린다면 Module O가 이미 갖고 있는 `timestamp`(경보 트리거 시각)를 그대로 넘기면
  된다 — `orchestrator.py`가 Module H를 부르는 지점에 한 줄 추가하는 수준이다(트랙③).

**결정 전까지**: 2순위 폴백이 항상 `degraded`를 내므로 H가 관여하는 경보에서
Module O의 `fallback_tier`가 2 이상으로 올라간다(1번 안건과 같은 증상).

---

## 8. `contracts/module_h.example.json`의 input이 output을 만들 수 없다

`citizen_reports`는 1건인데 `report_count`는 6이다. `response_latency_min: 4.5`도
유도되지 않는다 — `alert_id`의 09:15 기준이면 유일한 신고(09:22)는 7.0분이다.
Module D(2번 안건)와 같은 유형의 불일치다.

트랙②는 D와 같은 방식으로 처리했다:
- `test_contract_example_input_cannot_produce_its_own_output` — 불일치 자체를 고정
- `test_documented_output_is_reproducible` — 이상징후_목격 6건 + 첫 응답 4.5분
  입력으로 문서화된 output data(`6 / 현장확인 / 0.12 / 4.5`)를 정확히 재현

**제안**: example.json의 input에 신고 6건과 `alert_issued_at`을 채워 자기 output을
재현하게 만든다. `module_h_citizen_verification/tests/conftest.py`의
`documented_case` 픽스처를 그대로 쓰면 된다. 7번 안건(경보 시각 필드)과 함께
결정하는 게 자연스럽다.

> **주의**: 이 예시의 `confidence_adjustment: 0.12`를 재현하려고 shrinkage 상수를
> `k=9`로 **역산**했다. 근거 있는 값이 아니라 계약 예시에 맞춘 값이며 정책 파일에
> 그 사실을 명시해뒀다. 예시 숫자를 고칠 거라면 k도 같이 재검토해야 한다 — 어느
> 쪽이든 파일럿 응답 데이터를 받으면 재보정 대상이다.

---

## 9. `contracts/module_g.example.json`의 input이 output을 만들 수 없다 (약 64배)

단가 고시 2건을 적용하면 예시 입력의 산정액은 다음과 같다:

```
주거 1세대 x 3,500,000원(국토부고시 제2026-90호)        =      3,500,000원
농경지 4.2ha = 42,000m2 x 381원(농식품부고시 제2026-78호) =     16,002,000원
                                                          ─────────────────
                                                    합계        19,502,000원
문서화된 값                                            1,250,000,000원  (약 64배)
```

`cost_range_krw`도 마찬가지다. 예시 입력에 '미상' 건물이 0건이라 최소 불확실성
폭(30%)을 적용해도 `[19,502,000, 25,352,600]`이 나오고, 문서값 `[900,000,000,
1,600,000,000]`과 자릿수가 다르다.

Module D(2번)·Module H(8번)와 같은 유형의 불일치다. 트랙②는 같은 방식으로
처리했다 — 불일치 자체를 고정하는 테스트
(`test_contract_example_input_cannot_produce_its_own_output`)를 두고, 산식이
재현 가능한 실입력으로 계산을 검증한다.

**제안**: example.json의 값을 실제 단가로 계산되는 수치로 교체한다. 다만 이건
D·H보다 판단이 필요하다 — 문서값 12.5억이 "주택 1채 + 농경지 4.2ha"에 대한
값으로 나온 근거가 무엇인지(다른 단가표인지, 예시용 임의값인지) 확인한 뒤에
고쳐야 한다. 계약 파일 수정이므로 4인 합의 필요.

> 참고: 우리가 쓰는 단가는 **복구비 지원** 단가 고시다. 실제 경제적 손실(재산피해
> 총액)이 아니라 그 하한이라, 재해연보식 피해액과는 원래 자릿수가 다를 수 있다.
> `basis_citation`에 이 사실을 명시했다.

---

## 10. Module O의 `unit_cost_table_ref` 하드코딩 문자열 교체 요청 (트랙③)

`module_o_orchestrator/orchestrator.py`가 Module G를 부를 때
`"unit_cost_table_ref": "재해연보_2024_원단위"`를 하드코딩해 넘긴다. 그런데 트랙②가
실제로 쓰는 단가표는 2026년 고시 2건(`module_g_v1`)이라 **상시 불일치** 상태다.

Module G는 요청한 표를 쓴 척하지 않는다 — `status`는 `ok`로 두되(2026-09-05 결정)
warning을 남기고 `basis_citation` 끝에 `[요청 '재해연보_2024_원단위' 대신
module_g_v1 적용]`을 붙인다. 즉 지금도 결과는 정상이고 근거도 정확하지만,
호출부의 문자열이 사실과 다르다.

**요청**: `orchestrator.py`의 해당 문자열을 `"module_g_v1"`으로 바꾸거나, 아예
Module O가 표를 지정하지 않고 G의 활성 표를 쓰도록 필드를 생략할 수 있게 해달라
(후자는 계약상 `unit_cost_table_ref`가 required라 4인 합의가 필요하다).

**함께 볼 것 — 단독주택 1동 = 1세대 ASSUMPTION**: Module G의 점추정은 주거 건물
1동을 1세대로 센다(`policies/module_g.json`의 `one_building_one_household`).
공동주택은 실제로 수십 세대라 **과소추정**이다. 산청 실행에서 주거로 분류된
27,824건 전체에 이 가정이 걸려 있다.

> **TODO**: 건축물대장 표제부 응답에 세대수(`hhldCnt`)가 이미 들어 있다
> (2026-09-04 probe로 확인). `scripts/fetch_building_use_types.py`가 지금은
> 주용도(`mainPurpsCdNm`)만 뽑는데, `hhldCnt`를 함께 실어오면 이 가정을 없앨 수
> 있다. 다만 조인이 필지 단위(1번·2번 안건과 같은 한계)라 한 필지에 여러 동이
> 있으면 세대수 배분 규칙이 또 필요하다 — 그래서 이번 범위에서는 미뤘다.
