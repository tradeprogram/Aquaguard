# Implementation Summary: 현장조사 반영 — 고립 대피 시한 · 도로 보정 · 통제 구간 · 침수 계산 범위

---
**Date:** 2026-10-08
**Author:** AI Assistant
**Status:** Complete (병합·배포 전)
**Plan Reference:** [plan-field-survey-reflections.md](plan-field-survey-reflections.md)

---

## Overview

산청읍 송경천 현장조사(2026-09-25)의 "시스템에 반영할 점" 다섯 가지를 구현했다. 기존 수치는 바뀌지 않았다. 고립 2,445동·4,243동과 경보 봉투가 그대로이며, 실시간 재실행 대조 테스트로 확인했다.

**Implementation Duration:** 2026-10-08 (하루)
**Branch:** `field-survey-reflections` (`main`에 아직 병합하지 않음)
**Final Status:** ✅ Complete — 단, ④ 덕천강 모형의 **실제 실행**은 G: 드라이브 PC에서 해야 한다(계획 범위 밖).

## Plan Adherence

**Deviations from Plan:**

- **Deviation 1: 대피 시한의 정의를 바꿨다 (Phase 5).**
  - **Reason:** 계획의 `cut_before_window`(자료 첫 시각부터 끊김) 기준으로 돌려 보니, 하천 본류를 건너는 길처럼 늘 끊긴 곳이 7/18 새벽에 끊긴 것으로 잡혔다. 그 결과 가장 이른 대피 시한이 탐지보다 31시간 앞섰다. 또 창의 최저 수위 시각(7/18 02:00)은 구간 모형의 초기화 구간이었다.
  - **Change:** `low_water_hour` 인자를 추가했다. 저수위 시각은 앞선 수위 정점 이후, 기준 시각 전까지 가장 낮은 시각(홍수 사이의 골)이다. 그때도 끊긴 마을은 `persistent=True`로 두고 시한을 매기지 않는다.
  - **Impact:** 저수위 7/19 01:00. 늘 끊김 9곳(493동), 이번 홍수로 끊김 56곳(1,841동). 가장 이른 시한은 7/19 03:00.
- **Deviation 2: 계획의 구조차량 판정 근거 하나가 틀렸다 (Phase 3, 계획 수립 단계에서 정정).**
  - **Reason:** `rest_veh_h = "이륜차"`를 이륜차 전용으로 오해했다. 실제로는 이륜차 통행 금지이고, 150개 중 140개가 고속국도다.
  - **Change:** 구조차량 판정은 높이 제한과 현장 보정 파일로만 한다. 산청에서는 판정되는 건물이 0이며, 응답마다 한계 문구가 붙는다.
- **Deviation 3: 덕천강 격자가 경호강 격자와 겹친다 (Phase 6).**
  - **Change:** `domains.json`의 순서를 우선순위로 쓴다. 뒤 영역의 표시 폴리곤은 앞 영역 사각형 밖으로 잘라낸다.
- **Deviation 4: 저장본 재생성을 Phase 8에서 Phase 6으로 앞당겼다.**
  - **Reason:** Phase 7 화면 작업에 새 저장본 키가 필요했다. Phase 7은 화면만 바꿨으므로 다시 만들 필요가 없었다.
- **Deviation 5: 화면 세부 (Phase 7).**
  - 계산 범위 밖 영역에는 팝업을 달지 않았다(넓은 면이라 커서마다 팝업이 떠서 방해가 된다).
  - 고립마을 패널은 지도가 받은 시간축을 `page.tsx`를 통해 받는다(중복 다운로드 방지).
  - 통제 구간 조회를 지도 준비와 분리했다. WebGL이 없을 때 "불러오지 못함"으로 잘못 나오던 것을 이렇게 고쳤다.

## Phases Completed

| Phase | 내용 | 커밋 |
|---|---|---|
| 1 | Module E 정책 파일(`policies/module_e.json`) + 로더 | `94b2d151` |
| 2 | 버그 수정 — FeatureCollection 침수범위가 대피소를 걸러내지 못함 | `d9a8bc3a` |
| 3 | 고립 판정 재구성(문맥 1회 구축) · 끊긴 도로 속성 · 구조차량 진입 · 현장 보정 파일 | `975dabaa` |
| 4 | 복구·통제 구간(파일·고립·경로·`/road-closures`) | `afb4925f` |
| 5 | 시각별 고립 재판정 → 마을별 진입로 단절 시각·대피 시한 | `eaafb764` |
| 6 | 침수 모형 영역 목록 · 계산 범위 · 덕천강 구축 스크립트 · 저장본 재생성 | `3305275d`, `9e17d164` |
| 7 | 화면 — 계산 범위 밖, 통제 구간, 대피 시한 마을, 스크러버 마커, 패널 | `4aaf5af2` |
| 8 | 문서(Module E·B README), 구현 요약 | (이 커밋) |

## Files Modified

**Created:**
- `policies/module_e.json`, `module_e_routing/policy.py` — 정책값과 로더
- `module_e_routing/closures.py`, `data/road_closures.geojson` — 통제 구간(빈 파일로 출발)
- `data/road_overrides.json` — 현장 보정 기록(빈 목록으로 출발)
- `module_b_flood/domains.json`, `module_b_flood/domains.py` — 침수 모형 영역 목록·계산 범위
- `module_b_flood/scripts/33d_sfincs_build_deokcheon.py` — 덕천강 상류 모형 구축(`--dry-run`, `--postprocess`)
- 테스트: `module_e_routing/tests/{conftest,test_policy,test_risk_polygons,test_isolation_regression,test_isolation_context,test_closures,test_isolation_timeline}.py`, `tests/{test_closure_route,test_flood_domains}.py`

**Modified:**
- `module_e_routing/isolation.py` — `build_context`·`evaluate`·`closed_edges_for`·`isolation_timeline`, 도로 속성, 구조차량, 사용하지 않게 된 헬퍼 2개 삭제
- `module_e_routing/__init__.py` — 위험영역 대피소 필터가 FeatureCollection을 처리
- `api_server.py` — `/road-closures`, 경로 통제 구간·계산 범위 표시, 시간축에 `isolation_timing`·`flood_coverage`·`flood_static`, 침수 band 0 합집합
- `scripts/build_demo_snapshot.py` — 다중 영역, 계산 범위, 시각별 고립 판정, 사건일 통제 구간
- `tests/test_demo_snapshot.py`, `tests/test_flood_route.py` — 대피 시한·계산 범위 테스트 추가
- `ui/src/lib/api.ts`, `ui/src/components/MapExplorer.tsx`, `ui/src/components/panels/{IsolationPanel,EvacuationPanel}.tsx`, `ui/src/app/page.tsx`
- `data/precomputed/demo_snapshot.json`, `ui/public/demo/*.json` — 저장본 재생성
- `module_e_routing/README.md`, `module_b_flood/README.md`, `policies/README.md`
- `.claude/launch.json` — 로컬 API 미리보기를 8010(`ui/.env.local`과 같은 포트)으로

## Verification

### Automated
- ✅ `python -m pytest -q` — **602 passed** (기존 563 + 신규 39)
- ✅ `module_e_routing/tests/test_isolation_regression.py` — 산청군 침수 고립 **2,445동 유지**
- ✅ `tests/test_demo_snapshot.py` — 저장본 봉투 = 실시간 재실행, 대피 시한 = 단절 − 1h
- ✅ `python module_b_flood/scripts/33d_sfincs_build_deokcheon.py --dry-run` — 종료코드 0
- ✅ `cd ui && npx tsc --noEmit` — 오류 0
- ✅ `cd ui && npx eslint src` — 기존 3건(오류 1·경고 2) 외 새 문제 0
- ✅ `impeccable detect` — 디자인 점검 0건

### Browser (이 PC, localhost:3000 + API 8010)
- ✅ 범례: "통제 구간 · 현재 등록된 통제 구간 없음", "대피 시한이 지난 마을", "침수 계산 범위 밖 · 산청군의 35%", "계산 예정: 덕천강 상류 (시천·삼장)"
- ✅ 탐지 시점(09:00) "지금 대피해야 할 마을 3곳 · 약 34채"
- ✅ 스크러버 "고립 대비 시한 03:00"
- ✅ 고립마을 패널(침수 반영): "우리 경보(7/19 09:05)보다 먼저 대피해야 했던 마을 13곳 · 약 915채", 군집 카드별 단절·시한, 늘 끊긴 군집은 "평상시 수위에도 끊김"
- ✅ 대피소 찾기: 실도로 경로와 "침수 판정 범위 밖" 배지

### Manual (사용자 확인 필요)
- [ ] 지도에서 회색 계산 범위 밖 영역이 결과 레이어를 가리지 않는지
- [ ] 스크러버를 7/19 오전 → 첨두로 옮길 때 마젠타 점선 마을이 나타났다가 고립 표시로 바뀌는지
- [ ] 끊긴 도로를 가리키면 도로명·교량 여부가 나오는지
- [ ] `data/road_closures.geojson`에 시험 통제 1건을 넣고 API를 재시작하면 주황 점선이 그려지는지(확인 후 시험 항목 삭제)

## Remaining Work
- **덕천강 상류 모형 실행** — G: 드라이브 PC에서 `module_b_flood/README.md`의 7단계 순서를 따른다.
- **통제 구간·현장 보정 데이터 입력** — 위치가 확인되는 대로 파일에 적는다.
- **`main` 병합과 배포** — EC2는 `git fetch` + `reset --hard origin/main` + 재시작, Vercel은 자동 배포. 새 엔드포인트 `/road-closures`가 `/health` routes에 보여야 한다.
- 기존부터 있던 문제(이번 범위 밖): `tests/test_demo_snapshot.py`의 경로 비교는 네이버 최단경로가 바뀌면 깨진다(오늘 302→310점). 그때마다 저장본을 다시 만들어야 한다.
