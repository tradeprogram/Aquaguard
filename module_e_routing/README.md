# Module E — 대피경로·고립분석 (트랙④)

설계 문서(대피경로)·§7(고립마을 자동탐지)의 실제 구현. 이 폴더는 두 개의 독립된
기능을 담고 있다 — 둘 다 `api_server.py`가 REST 엔드포인트로 감싸서 프론트가 호출한다.

## 구성

- `__init__.py` — 대피경로 계산. `run(input)`은 `contracts/module_e.schema.json`
 계약을 그대로 따르는 Module O 오케스트레이터용 진입점(최적 대피소 1곳만 반환).
 `evaluate_candidates(input)`은 후보 전체의 결과를 반환 — `api_server.py`의
 `POST /evacuation-route`가 이걸 감싸서 씀(대피소 목록 화면처럼 여러 곳을 동시에
 비교해야 하는 화면용).
- `isolation.py` — 고립마을 탐지(§7). VWorld 도로망으로 networkx 그래프를 만들고
 위험폴리곤과 겹치는 도로를 제거한 뒤, 대피소 역방향 도달가능성으로 고립 건물을
 찾는다. `api_server.py`의 `POST /isolation-check`가 감싸서 씀.
 그래프·건물 매핑은 `build_context()`로 한 번만 만들고 위험 도형마다 `evaluate()`로 판정한다.
 `isolation_timeline()`은 시각별 위험으로 다시 판정해 마을별 진입로 단절 시각을 낸다.
- `closures.py` — 복구·통제 구간(`data/road_closures.geojson`) 읽기·검증·날짜 필터.
- `policy.py` — 정책값(`policies/module_e.json`): 대피 시한 여유, 통행 불가 수심, 구조차량 높이.

## 필요한 환경변수 (`.env`, git-ignore됨)

| 변수 | 용도 | 발급처 |
|---|---|---|
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 대피경로 — 네이버 Directions 5(자동차 실도로 경로) | 네이버클라우드플랫폼 콘솔 |
| `VWORLD_API_KEY` | 고립분석 — 도로망(`LT_L_MOCTLINK`)·건물(`LT_C_SPBD`) 조회 | vworld.kr (⚠ 아래 참조) |
| `SHELTER_API_KEY` | `GET /shelters` — 전국 대피소 실데이터 조회 | safetydata.go.kr, 하루 1,000건 한도 |

키가 하나라도 없으면 그 기능만 자동으로 폴백된다(직선거리 근사 / 503 에러) — 서버
전체가 죽지는 않는다.

**⚠ VWORLD_API_KEY 관련**: 지금 `.env`에 쓰는 값은 `scripts/fetch_aoi_data.py`에
평문으로 커밋돼 있던 걸 그대로 재사용한 것이다. 원래 발급받은 사람이 재발급(로테이션)
하는 게 안전하다 — 재발급 전까지는 이 값이 여전히 유효하다는 뜻.

## 대피경로가 실제 도로 경로가 아니라 직선으로 나올 때

`fallback_used: true`, `route_confidence: "low"`면 네이버 API 호출이 실패했거나
`NAVER_CLIENT_ID`/`SECRET`이 없는 것이다 — 하버사인 직선거리 ÷ 30km/h(자동차)
가정속도로 대체 계산된다. 도보 시간은 공개 API가 도보 길찾기를 주지 않아 **네이버
차량 경로의 길이 ÷ 4km/h**로 낸다(`modes.walk.source = "road_path@walk_speed"`).
네이버 호출이 실패했을 때만 직선거리 ÷ 4km/h로 떨어진다.

## 산청군 전체 시나리오 (2026-09-21)

UI의 "산청군 전체" 버튼(`ui/src/lib/demoShelters.ts`의 `sancheong_all`)은 산림청 API로 받은 산청군 대피소
104곳 전부와 군을 감싸는 bbox(127.72~128.12, 35.19~35.56)로 고립분석을 돌린다.
실측: 도로 약 1.4만·건물 약 11만, 첫 실행(VWorld 다운로드) 약 50초, 이후 캐시(`data/cache/isolation/`)로 약 5초.
- 위험 구역은 데모용 세로 띠라 결과 숫자는 성능·구조 검증용이며 실제 위험도가 아니다(트랙③ 연동 전).
- bbox가 사각형이라 인접 시군 건물이 일부 섞인다(군 경계 폴리곤 미적용).
- 도로에서 300m 넘게 떨어진 건물(약 2.4만)과, 위험과 무관하게 원래 대피소와 끊겨 있던 건물은 판정에서 빼고 `warnings`에 개수를 남긴다.
- 대피경로(EvacuationPanel)는 후보가 12곳을 넘으면 출발지에서 직선거리 가까운 12곳만 네이버로 조회한다.

### 실제 침수 반영 (2026-09-21)
- 고립분석: 산청군 전체에 "실제 침수 반영" 시나리오가 있다 — Module B 침수범위(표시용 폴리곤 중 수심 0.3m 이상 구간)와
 겹치는 도로를 끊고(빨간 통행불가 도로), 대피소까지 도달 못 하는 건물을 고립으로 센다.
 수심 0.3m를 통행 불가 기준으로 본 것은 가정이다(승용차 기준). 침수범위가 산청 AOI(경호강 일대)뿐이라 상능마을 구역엔 침수가 없다.
 이 시나리오는 사전계산본(`isolation.json`)으로만 제공한다(브라우저에 침수 폴리곤이 없고 `/isolation-check`도 아직 그걸 받지 않음).
 위험영역 안에 든 대피소는 후보에서 뺀다(warnings에 표시).
- 대피경로: `/evacuation-route`가 네이버 경로가 침수 구간과 겹치는지 검사해 `route_flooded`·`flooded_route_m`을 붙이고
 `time_feasible`을 false로 돌린다(UI는 통행 불가 표시 + 목록 뒤로). **우회는 못 한다** — 네이버 Directions는 "이 구역 피해서"를
 받지 않으므로 겹치면 그 대피소를 후보에서 내릴 뿐이고, 침수를 피하는 다른 길을 찾아주지는 않는다. 침수범위는 스냅샷에서 읽는다.

## 현장조사 반영 (2026-10-08)

산청읍 송경천 현장조사(2026-09-25)의 "시스템에 반영할 점"을 넣었다.
계획·변경 기록은 `docs/rse/specs/plan-field-survey-reflections.md`에 있다.

### ① 마을별 진입로 단절 시각과 대피 시한
`scripts/build_demo_snapshot.py`가 사후 재현의 시각마다(37시각) 그 시각의 침수와 그때까지
도달한 산사태 위험영역으로 고립을 다시 판정한다. 침수가 가장 넓은 시각(기준 시각)에 고립된
마을마다, 그 고립이 시작된 시각을 진입로 단절 시각으로 두고, 그보다
`evacuate_lead_before_cut_hours`(1시간, 팀 결정) 앞을 대피 시한으로 둔다.

- **늘 끊긴 마을(persistent)에는 시한을 매기지 않는다.** 저수위 시각(앞선 수위 정점 이후,
  기준 시각 전까지 가장 낮은 시각 — 홍수 사이의 골)에도 끊겨 있던 마을이다. 시각별 침수는
  최대침수심에서 수위강하를 빼는 근사라 본류가 최저 수위에도 물로 남고, 본류를 건너는 길은
  하루 종일 끊긴 것으로 계산된다.
- 창에서 가장 낮은 시각을 저수위로 쓰지 않는 이유: 구간 모형이 7/18 00:00 빈 하도에서 시작해
  첫 몇 시각의 수위가 낮게 나온다(초기화 구간).
- 결과는 경보 봉투가 아니라 저장본의 `isolation_timing`과 `timeline.json`에 있다. 실시간
  경로에는 시각별 침수가 없다.
- 2025년 7월 재현: 이번 홍수로 끊긴 마을 56곳(7/19 04:00~13:00), 그중 13곳(915동)은 대피
  시한이 경보 발송(09:05)보다 이르다.

### ② 끊긴 도로 속성과 구조차량 진입
- 끊긴 도로(`blocked_roads`)에 `link_id`, `road_name`, `rd_type_h`(교량·터널), `rd_rank_h`가 붙는다.
- **구조차량 판정은 높이 제한과 현장 보정 기록만 쓴다.** 표준노드링크에는 도로 폭·차로 수가
  없고, `rest_veh_h = "이륜차"`는 이륜차 통행 **금지**(150개 중 140개가 고속국도)라 구조차량과
  무관하다. 높이 제한(`rest_h`)이 `rescue_vehicle_height_m`(3.8m, 가정값)보다 낮은 링크나,
  `data/road_overrides.json`에 `vehicle_passable: false`로 적은 링크만 구조차량 통행 불가로 본다.
  산청의 높이 제한은 모두 4.0m 이상이라 지금은 걸리는 링크가 없다.
- 주민은 대피소까지 갈 수 있지만 구조차량이 못 들어가는 건물은 `rescue_limited_buildings`로 나온다.
- **마을안길은 도로망에 없다.** 도로명주소 도로 레이어(`LT_L_SPRD`)에는 있지만 도로명만 있고
  폭이 없다. 그 길로만 드나드는 마을은 가장 가까운 시·군도 링크 기준으로 판정된다(팀 결정으로
  이번에는 넣지 않음).

`data/road_overrides.json` 형식:
```json
{"links": [{"link_id": "3940041103", "vehicle_passable": false, "two_way": false,
            "note": "차 한 대 폭, 교행 불가", "source": "현장조사", "observed": "2026-09-25"}]}
```

### ③ 복구·통제 구간
`data/road_closures.geojson`에 적은 통제 구간을 고립 판정에서 끊고(`closed_roads`로 침수와
따로 보고), 대피 경로가 그 구간을 20m 넘게 따라가면 `route_closed`로 표시한다. 지도에는
`GET /road-closures`로 그날 유효한 것만 그린다. 사후 재현은 사건일(2025-07-19)에 유효했던
통제만 쓴다.

```json
{"type": "Feature",
 "geometry": {"type": "LineString", "coordinates": [[127.87, 35.41], [127.871, 35.411]]},
 "properties": {"id": "c1", "reason": "송경천 재해복구사업", "start": "2026-09-01", "end": null,
                "source": "산청군 공지", "link_ids": ["3940041103"]}}
```
- 선 통제에는 `link_ids`가 반드시 있어야 한다. 선 기하만으로 판정하면 교차로에서 다른 도로까지
  끊긴다. 면 통제(Polygon)는 그 안을 지나는 도로를 모두 끊는다.
- 날짜는 `YYYY-MM-DD`이고, `end`가 없으면 계속 유효하다.

### ⑤ 침수 계산 범위
`/evacuation-route` 결과에 `in_flood_coverage`가 붙는다. `false`는 "안 잠김"이 아니라
"이 대피소 주변은 침수를 계산하지 않음"이다. 범위는 `module_b_flood/domains.json`에서 온다.

## 알려진 한계 (2026-09-09 기준)

- **고립분석 캐싱 없음**: `/isolation-check`를 부를 때마다 VWorld를 처음부터 다시
 조회하고 그래프도 새로 만든다. 설계 문서이 요구하는 "AOI 진입 시 한 번만 구성"
 최적화가 아직 없음 — 산청(마을 단위)은 몇 초 안에 끝나지만, 강남(14km²)은 그보다
 느리고 서초(21km²)는 약 15초 걸림(2026-09-09 실측) — 도시 지역으로 넓힐수록
 체감된다.
- **도시 지역 고립 건물 수는 지역 간 비교 불가**: 산청은 진입로가 사실상 하나뿐인
 산골 마을이라 그 길이 끊기면 실제로 고립되는 게 현실적이지만, 강남·서초는 도로가
 촘촘한 격자망이라 같은 폭의 데모 위험폴리곤이 훨씬 많은 도로 구간을 건드린다
 (산청 42개 vs 서초 170개 제거). 그 결과 서초의 고립 건물 수(692채)가 산청(269채)
 보다 크게 나오는데, 이건 서초가 "더 위험해서"가 아니라 도시 도로망 밀도 때문에
 생기는 착시다 — 실제로는 우회로가 많은 도시가 덜 고립돼야 정상. 데모 위험폴리곤을
 실제 침수 범위 기반으로 바꾸기 전까지는 지역 간 숫자를 위험도 비교에 쓰지 말 것
 (IsolationPanel.tsx에 안내 배지로 표시해둠).
- **슬라이더 심각도가 고립 범위에 영향 안 줌**: `ui/src/components/MapExplorer.tsx`의
 침수/토사 3D 볼륨(`buildFlowBands`, 트랙③ 소관)은 슬라이더 값이 커져도 폭(가로
 범위)은 고정이고 높이(3D로 보이는 정도)만 커진다 — 그래서 이 폴리곤을 그대로
 가져다 쓰는 고립분석 결과도 슬라이더 값과 무관하게 항상 같게 나온다. 버그 아님,
 설계상 한계 — 고치려면 트랙③과 먼저 상의할 것(폭 로직 자체가 Module E 담당이 아님).
- **`GET /shelters` 화면 미연결**: 전국 2,604곳 실데이터(`scripts/fetch_shelters.py`로
 받음)가 백엔드엔 있지만 아직 어느 화면도 안 부른다. 게다가 이 데이터셋 자체가
 경상남도(산청 포함)·전라남도·전라북도·충청남도·세종을 아직 커버 안 함(지자체별
 등록 진행 중으로 추정) — 그래서 지금 메인 데모(산청)엔 이 실데이터를 못 쓴다.
 `EvacuationPanel.tsx`/`IsolationPanel.tsx`는 여전히 손으로 넣은 대피소 3곳
 (`ui/src/lib/demoShelters.ts`)을 쓴다.
- **`contracts/module_e` 계약 미반영**: `modes: {car, walk}` 필드 확장설계 문서
 제안)은 API 응답에만 임시로 붙어있고, 계약 파일 자체는 안 바꿨다(4인 합의 필요,
 §4.3 규약). 합의되면 `contracts/module_e.example.json`/`module_e.schema.json`에
 반영할 것.
- **Module O 경보 파이프라인 미연동**: 이 패키지는 `EvacuationPanel`/`IsolationPanel`
 독립 화면에서만 쓰인다. `api_server.py`의 `/alerts/{id}/geojson`(실제 경보 발생 시
 그리는 지도)은 여전히 직선 placeholder — Module A/B/G/H가 아직 없어서
 `AQUAGUARD_MOCK_MODE`를 전체 실모드로 못 바꾸는 구조적 제약 때문.

## 동작 확인 (스모크 테스트)

```bash
python scripts/smoke_test_module_e.py # 대피경로 — 실제 네이버 API 호출됨
python scripts/smoke_test_isolation.py # 고립분석 — 실제 VWorld API 호출됨
```

둘 다 `.env`의 키를 그대로 쓰므로, 키가 없으면 대피경로는 폴백값으로, 고립분석은
에러로 끝난다.
