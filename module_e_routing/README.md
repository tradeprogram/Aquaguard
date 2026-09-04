# Module E — 대피경로·고립분석 (트랙④)

HANDOFF.md §6(대피경로)·§7(고립마을 자동탐지)의 실제 구현. 이 폴더는 두 개의 독립된
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
가정속도로 대체 계산된다. 도보 시간은 애초에 공개 API가 도보 길찾기를 안 줘서
항상 직선거리 ÷ 4km/h 근사다(이건 키가 있어도 그대로).

## 알려진 한계 (2026-09-03 기준)

- **고립분석 캐싱 없음**: `/isolation-check`를 부를 때마다 VWorld를 처음부터 다시
  조회하고 그래프도 새로 만든다. HANDOFF §7.3이 요구하는 "AOI 진입 시 한 번만 구성"
  최적화가 아직 없음 — 데모 규모(마을 단위)에선 몇 초 안에 끝나서 체감상 괜찮지만,
  넓은 지역으로 확장하면 느려질 수 있음.
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
- **`contracts/module_e` 계약 미반영**: `modes: {car, walk}` 필드 확장(HANDOFF §6.6
  제안)은 API 응답에만 임시로 붙어있고, 계약 파일 자체는 안 바꿨다(4인 합의 필요,
  §4.3 규약). 합의되면 `contracts/module_e.example.json`/`module_e.schema.json`에
  반영할 것.
- **Module O 경보 파이프라인 미연동**: 이 패키지는 `EvacuationPanel`/`IsolationPanel`
  독립 화면에서만 쓰인다. `api_server.py`의 `/alerts/{id}/geojson`(실제 경보 발생 시
  그리는 지도)은 여전히 직선 placeholder — Module A/B/G/H가 아직 없어서
  `AQUAGUARD_MOCK_MODE`를 전체 실모드로 못 바꾸는 구조적 제약 때문.

## 동작 확인 (스모크 테스트)

```bash
python scripts/smoke_test_module_e.py     # 대피경로 — 실제 네이버 API 호출됨
python scripts/smoke_test_isolation.py    # 고립분석 — 실제 VWorld API 호출됨
```

둘 다 `.env`의 키를 그대로 쓰므로, 키가 없으면 대피경로는 폴백값으로, 고립분석은
에러로 끝난다.
