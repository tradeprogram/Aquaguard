# AquaGuard AI (아쿠아가드)

산불로 훼손된 사면 위에 첫 집중호우가 떨어지는 순간부터, 산사태→하천범람→고립까지 이어지는 **재해연쇄(disaster chain)**를 몇 시간 전에 읽어내고, 관(官)의 의사결정을 기다리지 않고 대피소·경로·피해규모까지 자동으로 계산해 동시에 전파하는 에이전트.

> 전체 아키텍처는 **[ARCHITECTURE.md](ARCHITECTURE.md)**에 있음 — 이 저장소에서 작업을 시작하는 모든 사람(사람이든 Claude Code 세션이든)은 그 문서의 **§0(프로젝트 배경)**부터 반드시 먼저 읽을 것. 원본 PDF(다이어그램 포함)는 [`docs/`](docs/)에 있음.

## 왜 만드는가

2025.7.19 산청 산사태(13명 사망) — 문제는 예측 실패가 아니라 **전파 지연**이었다. 산림청 대피 권고(7/17) → 주민 신고 폭주(7/19 08:00) → 경보 격상(7/19 12:37), 신호는 있었는데 관의 판단·전파 단계에서 4시간 넘게 샜다. 또한 같은 지역이 4개월 전 대형 산불 피해지였다는 점에서, 산불이 사면을 훼손하면 이후 폭우가 산사태로 이어질 확률이 급증하는 재해연쇄가 실존한다.

**이 프로젝트가 자동화하는 것은 "더 정확한 예측"이 아니라 "이미 있는 신호와 실제 대피 사이에서 새는 시간"이다.**

- **독창성 축 1** — 재해연쇄: 화재흉터 증폭계수 f(dNBR, Δt)로 화재→산사태→범람 사슬 정량화
- **독창성 축 2** — 골든타임 격차: 판단·전파 지연을 자동화로 우회
- **독창성 축 3** — 시민 신고 역검증 루프 / 원클릭 승인(15분 타임아웃 자동승인) / What-if 예측 시뮬레이터

## 저장소 구조

```
ARCHITECTURE.md          # 아키텍처 확정안 v2.4 전문 (§0~§14)
docs/                     # 원본 PDF (다이어그램 포함)
contracts/                # §4.3 — 8개 모듈 입출력 계약 (Day 1 최우선 산출물)
  module_*.example.json    #   예시 입출력 JSON
  module_*.schema.json     #   타입 검증용 JSON Schema
module_a_landslide/       # 산사태 예측
module_b_flood/           # 하천범람 예측
module_c_urban_rule/      # 도로·지하차도 침수 (규칙기반)
module_d_exposure_overlay/# 노출자산 오버레이
module_e_routing/         # 대피소·경로 라우팅
module_g_damage_cost/     # 피해비용 추정
module_h_citizen_verification/ # 시민 신고 역검증
module_o_orchestrator/    # 골든타임 오케스트레이션 (상태머신·원클릭승인)
ui/                        # Next.js 대시보드 + 3D (MapLibre + deck.gl)
data/                      # static(10m 지형) / dynamic(500m 관측, 6~9월만) / vector
api_server.py               # FastAPI, 전 모듈 import
```

## 팀 & 트랙 (3인, 독립 개발)

| 트랙 | 담당 | 소유 모듈 | 핵심 산출물 |
|------|------|-----------|-------------|
| ① 예측모델·위성 | 김민석 | A, B | 데이터 파이프라인(6~9월), f(dNBR,Δt), LDAPS 편차보정, 신뢰구간 |
| ② 대응로직·데이터통합 | 나정우 | C, D, E, G, H | 벡터데이터, 위험가중 A* 라우팅, 피해비용, 시민 역검증 |
| ③ 오케스트레이션·UI·3D | 하수범 | O, UI, UI-3D | 상태머신·원클릭승인, 대시보드, deck.gl+V-World 3D, What-if 시뮬레이터, 산청 데모 |

세 세션은 서로의 실제 구현을 보지 않고 **[`contracts/`](contracts/)의 example.json/schema.json**만으로 병행 개발한다. [ARCHITECTURE.md §13](ARCHITECTURE.md#13-트랙별-claude-code-브리핑-그대로-복붙해서-각자-세션에-붙여넣을-것)에 트랙별로 그대로 복붙할 브리핑 문구가 있음.

## 지금 해야 할 일 (Day 1)

1. ✅ `contracts/` 8개 모듈 계약 확정·커밋 완료
2. 각자 담당 모듈 폴더(`module_*`) 생성, `contracts/`의 example.json을 목업으로 병행 개발 시작
3. `contracts/` 필드 변경은 **3인 합의 없이 금지** — 한쪽에서 조용히 바꾸면 다른 트랙이 깨짐

## 규칙 한 줄 요약 (§4)

- 좌표: 내부는 전부 `EPSG:5179`(미터), 최종 UI 출력 직전에만 `4326`으로 재투영
- 시간: ISO 8601 + KST 타임존 (`+09:00`), UTC 금지
- 확률: `0.0~1.0` float, 신뢰구간은 항상 `[low, high]`
- 모든 모듈: `def run(input: dict) -> dict`, 예외 던지지 말고 `{status, fallback_tier, data, warnings}` 봉투로 반환

## 데모 시나리오

2025.7.19 산청 산사태 타임라인 재연 — `timeline_actual`(신고 08:00 → 경보 12:37) vs `timeline_agent`(에이전트가 있었다면의 타임라인)를 나란히 비교해 "N시간 O분 확보"를 헤드라인으로 증명. 상세는 [ARCHITECTURE.md §9](ARCHITECTURE.md#9-데모-시나리오-산청-2025-타임라인-재연).
