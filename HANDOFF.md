# 인수인계 — Codex용 (트랙③ 오케스트레이션·UI·3D)

이 문서는 Claude Code 세션이 지금까지 한 작업을 Codex가 컨텍스트 없이 이어받을 수 있도록 정리한 것이다. **먼저 [README.md](README.md)와 [ARCHITECTURE.md](ARCHITECTURE.md)를 읽어라** — 프로젝트 배경(산청 산사태, 골든타임 격차)과 §4~5 통합 규약은 거기 있고 여기서 반복하지 않는다. 이 문서는 "지금까지 뭘 만들었고, 왜 그렇게 만들었고, 다음에 뭘 해야 하는지"에 집중한다.

담당자: 하수범 — 트랙③(오케스트레이션·UI·3D), 소유 모듈: Module O, UI, UI-3D. 트랙①(예측모델, 김민석)·트랙②(대응로직, 나정우)는 **아직 아무 코드도 없다** — 이 저장소는 지금 100% 트랙③ 산출물이다.

---

## 0. 저장소 정보

- GitHub: https://github.com/tradeprogram/Aquaguard (owner: `tradeprogram`)
- 로컬 경로(이 세션 기준): `C:\aquaguard`
- 브랜치: `main` 하나. 지금까지 58개 커밋(2026-08-28 기준), 전부 push 완료 (최신 커밋 `21d188a`). `git log --oneline`으로 항상 최신 상태 다시 확인할 것 — 이 문서보다 git이 항상 더 정확하다. **주의**: 이 숫자는 매번 갱신 안 될 수 있음 — 실제 공모전 리서치(§9)에서도 이 문서가 27커밋이라고 적어놓은 시점에 실제 GitHub는 56커밋이었다고 지적받은 적 있음.
- 커밋 작성자: `tradeprogram <chanvab1@gmail.com>` (git config, 로컬 repo 한정)
- `git log --oneline`으로 전체 히스토리 확인 가능 — 각 커밋 메시지에 "왜"가 상세히 적혀 있어서 되짚어보기 좋다.

---

## 1. 지금까지 한 일 (요약)

### 1.1 계약(contracts/) — Day 1 산출물
`contracts/module_{a,b,c,d,e,g,h,o}.{example.json,schema.json}` — 문서 §5의 모듈별 입출력 예시를 그대로 옮긴 것. **다른 두 트랙이 아직 안 왔으므로 이 계약은 실제로 검증된 적이 없다** — 트랙①②가 실제 모듈을 만들면 이 계약과 어긋나는 부분이 나올 수 있음을 감안할 것. `Module O`의 `input` 스키마(`alert_id`/`trigger_location`/`timestamp`/`auto_approve_timeout_min`/`safety_margin_hours`)는 문서에 명시적 예시가 없어 트랙③이 추론해 넣은 값이라고 `contracts/README.md`에 명시해뒀다.

`ui/src/lib/types.ts`에 Module C/D(`UnderpassAlert`/`ExposureData`, `AlertPackage.road_flooding`/`.exposure`)와 Module E 확장(`RouteModeEta`, `ShelterRouteData.modes`) TypeScript 타입을 미리 만들어뒀다(2026-08-27, 전부 optional) — 아직 실제 orchestrator 출력엔 없는 준비용이니, 실제 모듈 연동할 때 이 타입 그대로 쓰거나 필요하면 고쳐써도 됨.

### 1.2 Module O 오케스트레이터 (`module_o_orchestrator/`)
- `orchestrator.py`: `run(input) -> envelope`. A/B 호출 → 임계치(`landslide_prob≥0.7` 또는 `flood_prob≥0.7`) 초과 시 D/E/G 순차 호출 → `precursor_flag`면 H 호출 → `golden_time_saved_min` 계산 → `AlertStore`에 등록.
- `modules_client.py`: `AQUAGUARD_MOCK_MODE`(기본 `1`)로 목업/실제 모듈 호출을 스위칭. `MODULE_PACKAGES` 딕셔너리에 트랙①②의 실제 패키지명이 매핑돼 있음 — **트랙①②가 코드를 넣으면 이 파일 수정 없이 `AQUAGUARD_MOCK_MODE=0`만으로 실제 연동됨.**
- `store.py`: 인메모리 `AlertStore`. 원클릭 승인 상태머신(`대기`/`승인`/`거부`/`자동승인(timeout)`), 오탐(`오탐판정`)이면 자동승인 안 함. **2026-08-29부로 핵심 아키텍처에서 제외됨**(시민 직접배포 취지·법적 리스크, §9.5 참조) — 코드는 남아있으나 더 이상 신규 개발 대상 아님.
- `geo.py`: EPSG:5179→4326 재투영 헬퍼(점/원). **§4.1 규약상 재투영은 UI 출력 직전에만** — 이 파일과 `api_server.py`의 지도 관련 엔드포인트가 그 유일한 지점.
- `tests/test_orchestrator.py`: pytest 6개, 전부 통과 중. 문서에 나온 예시값(`golden_time_saved_min=197`)을 정확히 재현하는지까지 검증함.
- 실행: `python -m pytest module_o_orchestrator/tests/ -v` (repo 루트에서)

### 1.3 FastAPI 서버 (`api_server.py`)
엔드포인트 목록:
| 엔드포인트 | 설명 |
|---|---|
| `POST /alerts/trigger` | Module O 파이프라인 실행 (§5 Module O `run()` 호출) |
| `GET /alerts/{id}` | 현재 상태 조회 (타임아웃 자동승인 지연평가 포함, `meta.created_at`/`auto_approve_timeout_min` 포함) |
| `POST /approve/{id}` | 원클릭 승인/거부 |
| `GET /alerts/{id}/geojson` | 3D 지도용 — 산사태 지점·위험버퍼·대피소·경로를 4326으로 반환 (§4.1 재투영 경계) |
| `GET /aoi/{name}` | **삭제됨** — 아래 `/boundaries`로 대체 |
| `GET /boundaries?bbox=...` | 시도/시군구/읍면동 3계층 행정경계를 뷰포트만큼 잘라 4326으로 반환 |
| `GET /search?q=...` | 행정구역 이름 검색(3계층 통합) |
| `GET /terrain-tiles/{z}/{x}/{y}.png` | AWS 지형 타일 CORS 프록시 |
| `GET /health` | 헬스체크 |

실행: `pip install -r requirements.txt && python -m uvicorn api_server:app --port 8000`

### 1.4 Next.js 대시보드 (`ui/`) — 2026-08-27 지도-메인-화면 개편으로 구조 변경됨
Next.js 16(App Router) + TypeScript + Tailwind v4.

- `/` — **이제 3D 지도가 메인 화면**(`MapExplorer.tsx`, 아래 1.5). 좌상단 로고(네이비 박스) + 메뉴바(대시보드/대피소 찾기/고립마을 위험/What-if 시뮬레이터) — 누르면 페이지 이동 없이 지도 위에 **글라스 톤 패널**(`GlassPanel.tsx`, 화면 면적의 ~50%)이 뜨고 닫힘. 패널 내용물은 `ui/src/components/panels/`의 `DashboardPanel`/`EvacuationPanel`/`IsolationPanel`/`WhatifPanel`. 원클릭 승인은 시민 화면이라 메뉴에서 뺐음(아래 `/approve` 참조).
- `/approve` — 원클릭 승인 화면, 실시간 타임아웃 카운트다운. **메뉴에서는 빠졌지만 라우트는 남아있음** — 관 대응용 UI가 따로 필요해지면 여기부터 다시 연결하면 됨(`ApprovePanel.tsx` 재사용).
- `/whatif` — What-if 강수 슬라이더 단독 페이지(직접 링크·테스트용, 평소엔 `/`의 메뉴 패널로 씀). 지금은 목업이라 값 고정 — 트랙①이 실제 Module A/B 붙이면 바로 반영됨.
- `/map3d` — 3D 지도 단독 페이지(로고·메뉴 없이 지도만, 직접 링크·테스트용). 실제 지도 로직은 전부 `ui/src/components/MapExplorer.tsx`에 있고 이 라우트는 그걸 감싸는 얇은 래퍼일 뿐.

챗봇 위젯(`ChatWidget.tsx`, 우측 하단 "AI" 버튼)은 모든 페이지에 공통으로 뜬다 — `/chat` 백엔드는 지금 규칙기반 키워드 응답(진짜 LLM 아님).

실행: `cd ui && npm install && npm run dev` → http://localhost:3000
빌드 검증: `npm run build && npm run lint` (매 변경마다 이걸로 검증해왔음, 계속 그렇게 할 것)

### 1.5 3D 지도 (`ui/src/components/MapExplorer.tsx`, `/`와 `/map3d` 둘 다 이걸 씀) — 가장 공들인 부분
스택: MapLibre GL JS `5.24.0`(⚠️ 버전 중요, 아래 §3 참조) + `@turf/buffer`. **deck.gl은 세션 중 완전히 제거됐다** — 3D 지형·건물·교량·시뮬레이션 볼륨 전부 MapLibre 네이티브 `fill-extrusion`으로 통일(이유는 §3 트러블슈팅 로그).

구성 요소:
- **지형**: `api_server.py`의 `/terrain-tiles` 프록시를 통해 AWS 공개 지형 데이터(terrarium 인코딩) → `map.setTerrain()`
- **위성영상**: Esri World Imagery (무료, 키 불필요) + Esri 지명 레이블 레이어
- **건물**: VWorld 건물통합정보(§2.3 1순위, `LT_C_SPBD` 레이어, `/vworld/buildings` 프록시) — 층수×3m 근사 높이로 압출. VWorld 요청 실패 시에만 OpenFreeMap(OSM) 폴백으로 자동 전환(`buildings-3d-osm`, 산간지역은 매핑이 드문드문 — 산청 AOI bbox 기준 VWorld는 478개, OSM은 훨씬 적었음)
- **도로망**: VWorld 표준노드링크(§2.6, `LT_L_MOCTLINK` 레이어, `/vworld/roads` 프록시) — OSM(OpenFreeMap) `transportation` 벡터타일은 z14가 최대라 그보다 확대하면(서울 z16 테스트 지점 등) 지오메트리가 늘어나 보이며 뒤틀림("서울 도로가 구불구불하고 짜그러짐" 버그, 커밋 `020e86e`). VWorld는 그 배율에서도 실제 형상 그대로 나옴. 실패 시에만 OSM 폴백(`roads-osm`/`roads-casing-osm`/`roads-tunnel-osm`).
- **교량**: VWorld 응답의 `rd_type_h` 필드가 `교량`/`고가차도`/`터널`/`일반도로`를 직접 구분해줘서(OSM `brunnel` 태그보다 신뢰도 높음), 교량·고가차도 구간만 `@turf/buffer`로 폭만큼 버퍼링 → `fill-extrusion`으로 지면에서 3~11m 띄운 "진짜 뜬" 데크 (단순 라인 색칠이 아님). VWorld 실패 시에만 OSM `brunnel` 태그 기반으로 폴백(`updateBridgesFromOSM`).
- **행정경계 3계층**: 사용자가 준 `BND_ADM_DONG_PG`(읍면동 레벨) 원본을 코드 접두어로 dissolve해서 시군구/시도 경계까지 만듦(아래 §2 데이터 파이프라인 참조). 뷰포트 bbox로 실시간 갱신, 데모 AOI(생비량면)만 노란색.
- **검색창**: 시/도/군/구/읍/면/동 이름 검색 → 결과 클릭 시 `fitBounds`로 이동
- **골든타임 시간슬라이더**: `timeline_actual` vs `timeline_agent` 이벤트를 스크럽하면서, 에이전트 탐지/발송 시점을 지나야 위험/대피 레이어가 나타나도록 단계적 노출(관의 실제 대응보다 에이전트가 먼저 안다는 서사를 시각적으로 증명)
- **카메라 조작**: 좌클릭 드래그=이동, 스크롤=줌(화면 중앙 기준 고정), 우클릭/Ctrl+드래그=회전·기울기. `maxPitch:70`.
- 테스트용 빠른 이동 버튼: 산청(AOI)/서울 강남/부산 해운대

**토사/침수 시뮬레이션 — 1차 버전 완료 (커밋 `4759d2a`)**:
> 사용자가 실제 CFD 시뮬레이션 소프트웨어(FLOW-3D류) 캡처를 참조로 주며 "토양은 빨간색, 물은 파란색, 실제 예측 양까지 정밀하게 넣어서 건물이 잠기는지 도로가 잠기는지 정확히 보고 싶다"고 요청.

**지금 있는 것** (전부 `ui/src/app/map3d/page.tsx` 안에 자체 완결, 백엔드 변경 없음 — Codex가 `api_server.py`/`geo.py`를 동시에 만지고 있어서 충돌 피하려고 프론트에만 구현):
- 데모 AOI 지형에 맞춰 손으로 배치한 흐름 중심선(`DEBRIS_CENTERLINE_M`/`FLOOD_CENTERLINE_M`, 산사태 트리거 지점 기준 로컬 미터 오프셋) → `@turf/buffer`로 3겹 밴드 생성(바깥 옅은색~안쪽 진한색, 토사=빨강/주황/노랑, 침수=하늘/파랑/진파랑)
- 각 밴드를 **MapLibre 네이티브 `fill-extrusion`**(deck.gl 아님 — bridges와 같은 이유: 지형·건물과 진짜 깊이버퍼로 겹쳐야 함)으로 지면에서 세움, `depth` 필드로 높이 조절
- 사이드패널에 **토사 깊이(0~4m) / 침수 수위(0~5m) 슬라이더** — 조작하면 밴드가 실시간 재계산
- 침수 범위(가장 바깥 밴드) 안에 들어오는 렌더링된 건물 수를 `queryRenderedFeatures` + `@turf/boolean-point-in-polygon`로 세서 텍스트로 표시
- UI에 "실제 예측값 아님, what-if 슬라이더" 배지 명시(§6 불확실성 표기 원칙)

**한계 / 다음 단계**:
1. 흐름 경로가 손으로 배치한 값이라 실제 지형(계곡 방향)과 완벽히 안 맞을 수 있음 — 상능마을 실제 지형을 3D로 돌려보면서 중심선 좌표(`DEBRIS_CENTERLINE_M`/`FLOOD_CENTERLINE_M`)를 조정할 것.
2. Module A(`landslide_prob`/`amplification_factor`)나 Module B(`inundation_extent_5179`)가 실제로 연동되면, 지금의 하드코딩된 중심선/밴드 생성 로직을 실제 모듈 출력 기반으로 교체해야 함 — `contracts/module_a·b.example.json`은 아직 목업이라 지오메트리가 비어있음.
3. Codex가 `api_server.py`/`geo.py`에서 서버사이드로 비슷한 걸(`debris_flow_demo`/`flood_volume_demo`, `ring_5179_to_lonlat`) 만들다가 중간에 날아간 적 있음(§3.7 "사이트 터진거" 사고, `git stash@{0}`에 보존돼 있음) — **두 접근을 합칠지, 프론트 전용으로 갈지 먼저 정리하고 시작할 것.** 서버사이드로 가면 5179 좌표계로 정확한 미터 버퍼링이 가능해서 더 정밀해지지만, 프론트 전용은 슬라이더 반응성이 빠르고 백엔드 충돌 위험이 없음.
4. 진짜 CFD처럼 매끄러운 그라디언트(레퍼런스 이미지 수준)를 원하면 밴드 개수를 늘리거나(지금 3겹→5~8겹), MapLibre의 `fill-extrusion-vertical-gradient` 같은 페인트 속성을 써서 각 폴리곤 내부도 그라디언트로 보이게 다듬을 수 있음.
5. **(해결됨)** "산청은 건물이 거의 안 뜬다"는 문제 — VWorld 건물통합정보 연동(§1.5, §2.2, 커밋 `abcb95a`)으로 해결. 이제 침수 볼륨이 실제 건물 478개와 정확히 겹쳐 보임. 3번 항목의 "백엔드 충돌 피하려고 프론트 전용으로 감" 전략은 이 커밋에서 `api_server.py`를 다시 건드리면서 깨졌으니, 이어서 작업할 때 Codex 상태를 다시 확인할 것(`git status`/`git log`).

---

## 2. 데이터 파이프라인 (지리 데이터) — 반드시 이해할 것

사용자가 원본 shapefile을 직접 줬다: **`C:\sb2\mask\BND_ADM_DONG_PG (2)\BND_ADM_DONG_PG.{shp,dbf,prj,shx,cpg}`** (전국 읍면동 경계, 3559개, 원본 좌표계 **EPSG:5186**, `ADM_CD`/`ADM_NM`/`BASE_DATE` 필드만 있음 — 상위 시군구/시도 이름은 이 파일에 없음).

이걸 다음과 같이 가공해서 `data/vector/`에 커밋해뒀다 (전부 **EPSG:5179**로 저장, 프로젝트 좌표계 규약 §4.1 준수):

| 파일 | 내용 | 크기 |
|---|---|---|
| `adm_dong_5179.geojson` | 읍면동 3559개 (원본 그대로, 필드: `level,code,name,sido,sidonm,sgg,sggnm,full_nm`) | ~11.7MB |
| `adm_sigungu_5179.geojson` | 시군구 252개 — 위 파일을 `sgg`(코드 앞 5자리)로 **dissolve**해서 생성 | ~6.2MB |
| `adm_sido_5179.geojson` | 시도 17개 — `sido`(코드 앞 2자리)로 dissolve | ~6.0MB |
| `adm_index.json` | 3계층 통합 검색 인덱스 (지오메트리 없음, `level/code/name/full_name/center/bbox`) | ~750KB |

**중요한 함정 — 코드 체계 혼동 주의**: `ADM_CD`(8자리, 예: 생비량면=`38570390`)는 이 shapefile 고유의 **레거시 SGIS 코드**다. 앞 2자리("38")는 흔히 아는 행안부 법정동코드(경남=48)와 **다르다**. `ADM_CD`의 앞 2/5자리를 dissolve의 그룹 키로 쓰는 건 전혀 문제없다(자체적으로 일관되고 유일하므로). 하지만 시도/시군구 **이름**은 이 shapefile에 없어서, 코드가 정확히 일치하는(`adm_cd` 필드, 검증됨 — 3559개 중 3551개 정확히 일치) 외부 공개 데이터셋 **[`vuski/admdongkor`](https://github.com/vuski/admdongkor)**(MIT 라이선스, 동일 SGIS `adm_cd` 스킴)에서 `sidonm`/`sggnm`을 조인해왔다. 이 조인 로직은 코드에 남아있지 않고 **일회성 전처리 스크립트로 실행 후 결과만 커밋**했다 — 재현하려면 이 문서 하단 §2.1의 스크립트를 다시 돌리면 된다. 나머지 8개(0.2%) 불일치 코드는 이름이 비어있을 수 있음(허용 가능한 손실).

### 2.1 전처리 재현 스크립트 (필요시)
```python
# 1) vuski/admdongkor에서 이름 참조 데이터 받기 (34MB, 한 번만)
# curl -sL -o ref.geojson "https://raw.githubusercontent.com/vuski/admdongkor/master/ver20250101/HangJeongDong_ver20250101.geojson"

import json, geopandas as gpd, pandas as pd

with open('ref.geojson', encoding='utf-8') as f:
    ref = json.load(f)
ref_df = pd.DataFrame([{'ADM_CD': p['properties']['adm_cd'], 'sido': p['properties']['sido'],
    'sidonm': p['properties']['sidonm'], 'sgg': p['properties']['sgg'], 'sggnm': p['properties']['sggnm']}
    for p in ref['features']]).drop_duplicates('ADM_CD')  # NB: p['properties'] not p, fix indexing in real run

gdf = gpd.read_file(r'C:/sb2/mask/BND_ADM_DONG_PG (2)/BND_ADM_DONG_PG.shp', encoding='cp949').to_crs('EPSG:5179')
gdf['ADM_CD'] = gdf['ADM_CD'].astype(str)
gdf = gdf.merge(ref_df, on='ADM_CD', how='left')
gdf['full_nm'] = (gdf['sidonm'].fillna('') + ' ' + gdf['sggnm'].fillna('') + ' ' + gdf['ADM_NM']).str.strip()
gdf['level'] = 'dong'
dong = gdf.rename(columns={'ADM_CD':'code','ADM_NM':'name'})[['level','code','name','sido','sidonm','sgg','sggnm','full_nm','geometry']]
dong.to_file('data/vector/adm_dong_5179.geojson', driver='GeoJSON', encoding='utf-8')

sigungu = dong.dissolve(by='sgg', aggfunc={'sidonm':'first','sggnm':'first','sido':'first'}).reset_index()
sigungu['geometry'] = sigungu.geometry.simplify(300, preserve_topology=True)
# level/code/name/full_nm 채우고 저장 — 본문 §1.3의 실제 실행 로그 참조

sido = dong.dissolve(by='sido', aggfunc={'sidonm':'first'}).reset_index()
sido['geometry'] = sido.geometry.simplify(600, preserve_topology=True)
# 마찬가지
```
(실제로 돌렸던 정확한 스크립트는 이 세션의 대화 로그에 있고, 결과 파일은 이미 커밋돼 있으니 **재실행 불필요** — 위는 재현용 참고일 뿐.)

---

## 3. 트러블슈팅 로그 — 이미 겪고 고친 버그들 (다시 겪지 말 것)

이 목록은 시간을 아끼기 위한 것이다. 3D 지도 작업 중 실제로 발생했고 원인을 찾아 고친 것들:

1. **컨테이너가 300px로 찌그러짐**: `maplibre-gl.css`가 지도 컨테이너에 `position:relative`를 강제로 걸어서 Tailwind의 `absolute inset-0`이 무력화됨. → `h-full w-full` 클래스로 교체(포지셔닝에 의존하지 않음).
2. **지형이 안 뜸**: AWS 지형 타일 서버(`s3.amazonaws.com/elevation-tiles-prod`)가 `Access-Control-Allow-Origin` 헤더를 안 보냄 → 브라우저가 고도 픽셀을 못 읽음(캔버스 오염) → **`api_server.py`의 `/terrain-tiles` 프록시**로 우회(서버 간 호출은 CORS 제약 없음).
3. **deck.gl이 "Cannot read properties of undefined (reading 'elevation')"로 크래시**: `maplibre-gl@6.6.0`이 너무 최신 버전이라 API가 바뀌어서(`node_modules/next/dist/docs`의 AGENTS.md가 이 문제를 경고함) `map.transform`이 deck.gl 9.3이 기대하는 형태와 안 맞음 → **`maplibre-gl@5.24.0`으로 다운그레이드**해서 해결. (interleaved 모드를 끄는 걸로는 안 고쳐졌음 — 버전이 근본 원인이었음.)
4. **줌하면 튕기고 방향이 바뀜**: (a) 커서 위치 기준 줌이 지형 로딩 중 고도값 변화로 카메라를 계속 재계산함 → `scrollZoom:{around:'center'}`로 고정. (b) `maxPitch:85`가 지형과 함께 쓰면 투영이 불안정해짐 → `70`으로 낮춤.
5. **`map.fitBounds()`가 bearing을 조용히 0으로 되돌림**: 공식 문서에 나온 동작(`options.bearing || 0`) — `bearing`을 항상 명시적으로 다시 넘겨야 함.
6. **행정동 경계가 동 단위로만 뜨고 시/군/구/도 단위는 안 뜸**: 원본 shapefile 자체가 읍면동 레벨까지만 있어서(§2 참조) — 시군구/시도는 존재하지 않는 데이터를 찾던 게 아니라 애초에 없어서 만들어야 했던 것.
7. **React StrictMode + MapLibre 초기화 관련**: rAF 지연 트릭을 시도했다가 이 세션의 "Browser pane" 자체가 프레임을 컴포짓하지 않는 환경이라 `requestAnimationFrame`이 영영 안 불려서 오히려 악화시킨 적 있음 — **원래의 동기 초기화(가드: `if (mapRef.current) return`)가 맞았다.** 이건 실제 브라우저에서는 문제 없었음 (StrictMode 이론은 틀렸던 진단이었음, 되돌림).

8. **"사이트 터진거 같은데" — 동시 편집 사고**: Claude Code(이 세션)와 Codex가 **같은 로컬 체크아웃(`C:\aquaguard`)을 동시에** 건드리고 있었고, 어느 시점에 `api_server.py`/`geo.py`/`map3d/page.tsx`/`api.ts` 4개 파일에서 마지막 커밋 대비 277줄이 삭제되고 2줄만 추가된 채로 남아 있었다(원인 특정 못함 — Codex가 리팩터링 중 실수했거나 저장이 꼬였을 가능성). `/alerts/{id}/geojson` 엔드포인트와 "산청 시나리오 실행" 데모 버튼 전체가 사라져서 사이트가 사실상 안 됐다. **`git stash`로 안전하게 보관한 뒤(`stash@{0}`, 아직 살아있음) 마지막 정상 커밋으로 되돌려서 복구**했다 — 강제로 버리지 않고 stash한 이유는 Codex가 만들던 내용이 진짜 필요한 작업일 수도 있어서다. **교훈: 같은 파일을 두 에이전트가 동시에 손대면 이런 사고가 난다 — 가능하면 파일/영역을 나누거나(이번엔 "백엔드는 Codex, 프론트는 Claude"로 암묵적으로 나눠서 이후엔 안전했음), 작업 전에 `git status`/`git diff HEAD`로 상대방이 뭘 하고 있었는지 먼저 확인할 것.**

**환경 관련 주의사항**: 이 세션이 쓰던 내부 "Browser pane" 미리보기 도구는 WebGL을 컴포짓하지 못하는 상태였다(스크린샷 자체가 실패함). 그래서 3D 지도 관련 버그의 상당수는 **사용자의 실제 브라우저 스크린샷**을 보고서야 진단할 수 있었다. Codex도 자체 미리보기 환경이 WebGL을 제대로 못 띄울 수 있다는 걸 염두에 두고, 필요하면 사용자에게 스크린샷을 요청할 것.

---

## 4. 실행 방법 (처음부터)

**VWorld API 키 필요**: `.env`(git-ignore됨, 절대 커밋 안 됨)에 `VWORLD_API_KEY=...` 한 줄이 있어야 `/vworld/buildings` 엔드포인트(§1.5, §2.2 참고)가 동작한다. 이 저장소를 새로 체크아웃하면 `.env`가 없으니, 사용자에게 키를 다시 물어보거나 www.vworld.kr에서 새로 발급받아 `C:\aquaguard\.env`에 넣을 것 (형식은 `.env.example` 같은 게 없으니 이 문서 참고). 없어도 서버는 뜨지만 `/vworld/buildings`가 503을 반환하고 프론트는 OSM 폴백(`buildings-3d-osm` 레이어, 산간지역은 매핑이 드문드문)으로 자동 전환된다.

```bash
# 백엔드
cd C:\aquaguard
pip install -r requirements.txt
python -m uvicorn api_server:app --port 8000

# 프론트엔드 (별도 터미널)
cd C:\aquaguard\ui
npm install
npm run dev
# http://localhost:3000

# 테스트
cd C:\aquaguard
python -m pytest module_o_orchestrator/tests/ -v
```

이 세션에서 백그라운드로 띄워뒀던 프로세스(포트 3000/8000)는 **세션 종료와 함께 사라진다** — Codex가 이어받으면 위 명령으로 새로 띄워야 한다.

매 변경 후 검증 습관(이 세션 내내 지켜온 것, 계속 지킬 것):
```bash
cd ui && npm run build && npm run lint   # 프론트 변경 시
cd .. && python -m pytest module_o_orchestrator/tests/ -v   # 백엔드 변경 시
```

### 4.1 배포 (2026-08-27 준비 시작 — 회의 때 프로토타입 감 잡기용, 아직 완료 안 됨)

사용자 요청: "일단 회의할 때 감 잡게 배포하면서 보는 게 목표고 나중에 모듈 추가되고 뭐 추가되면 로컬에서 수정하고 최종적으로 배포할 것" — 즉 무거운 운영급 배포가 아니라, **한 번 연결해두면 이후 `git push`마다 자동 재배포되는** 가벼운 프리뷰용 배포. 프론트(Vercel)와 백엔드(Render)를 따로 호스팅한다 — Vercel은 Next.js 프론트만 서빙하고, 검색·건물·도로·챗봇 같은 기능은 별도로 호스팅한 `api_server.py`를 호출해야 동작한다.

**프론트 — Vercel** (계정 연결은 사용자가 직접 해야 함, Claude Code가 로그인/계정생성 대행 불가):
1. vercel.com → GitHub 계정으로 로그인 → `tradeprogram/Aquaguard` 저장소 Import
2. **Root Directory를 `ui`로 지정** (Next.js 앱이 저장소 루트가 아니라 `ui/` 안에 있음) — 안 하면 빌드 실패
3. 나머지 빌드 설정은 자동 감지된 기본값 그대로 Deploy
4. 백엔드(Render) URL이 정해지면 Vercel 프로젝트 Settings → Environment Variables에 `NEXT_PUBLIC_API_BASE=https://<render-서비스명>.onrender.com` 추가 후 재배포(`ui/src/lib/api.ts`의 `API_BASE`가 이 값을 읽음, 없으면 `http://localhost:8000`로 폴백)

**백엔드 — Render** (저장소 루트의 `render.yaml`이 이미 설정을 정의해뒀음, 계정 연결은 마찬가지로 사용자 몫):
1. render.com → GitHub 계정으로 로그인 → New → Blueprint → `tradeprogram/Aquaguard` 선택 (저장소 루트의 `render.yaml`을 자동으로 읽어서 서비스 설정을 구성함)
2. `VWORLD_API_KEY`(+ 나중에 쓸 `GEMINI_API_KEY`) 환경변수는 `render.yaml`에 `sync: false`로 표시돼 있어서 대시보드에서 수동으로 넣어야 함 — `VWORLD_API_KEY` 값은 로컬 `.env` 파일에 있는 것과 동일(`.env`는 git-ignore라 저장소에는 없음). `GEMINI_API_KEY`는 슬롯만 미리 마련해둔 것 — 아직 `api_server.py`의 `/chat`이 규칙기반(`_chat_reply`)이라 값을 넣어도 코드가 안 읽는다, 실제 LLM 연동 작업을 먼저 해야 함
3. 무료 플랜은 일정 시간 요청이 없으면 슬립 상태가 되고 첫 요청 시 30~60초 콜드스타트가 걸림 — **회의 직전에 한 번 `/health`를 호출해서 깨워둘 것**
4. 배포되면 URL(`https://aquaguard-api-XXXX.onrender.com` 형태)을 위 3번(Vercel 환경변수)에 넣어야 프론트가 실제로 연결됨

**코드에서 이미 해둔 준비**(2026-08-27):
- `api_server.py`의 CORS를 `http://localhost:3000` 고정에서 `https://*.vercel.app` 정규식 허용으로 확장(`allow_origin_regex`) — Vercel 프리뷰 배포마다 서브도메인이 바뀌어도 매번 코드 안 고쳐도 됨
- `render.yaml` 추가 — `buildCommand: pip install -r requirements.txt`, `startCommand: uvicorn api_server:app --host 0.0.0.0 --port $PORT`, `healthCheckPath: /health`, region은 한국에서 제일 가까운 `singapore`
- `data/vector/*.geojson`(§2 데이터 파이프라인)은 이미 전부 git에 커밋돼 있어 별도 데이터 업로드 없이 클론만으로 배포 가능(총 26MB, GitHub 용량 제한 안 걸림)

**아직 안 된 것**: 실제 Vercel/Render 연결(사용자 액션 대기), 배포 URL 확정 후 서로 연결(위 3~4단계), 배포 후 실제 curl/브라우저 스모크 테스트.

---

## 5. 다음으로 무엇을 할지 (우선순위 제안)

1. **(최우선, 사용자가 명시적으로 요청, §6.8·6.9는 완료·나머지는 미착수)** 주민 대피 경로 기능(네이버/카카오 길찾기) — 아래 **§6 전체**가 이 작업의 상세 명세다. 다른 항목보다 먼저 이걸 읽고 시작할 것. **2026-08-27 진행**: `EvacuationPanel.tsx`가 이제 브라우저 Geolocation으로 실제 현재 위치를 받아 하버사인 직선거리 기반 차량/도보 시간을 계산하고(§6.8), 선택한 대피소까지 `MapExplorer.tsx`에 점선 경로+마커로 그려준다(§6.9, `app/page.tsx`가 상태를 끌어올려 `route` prop으로 연결 — `EvacuationRoute` 타입은 `MapExplorer.tsx`에서 export). **아직 남은 것**: 대피소 좌표 3곳(`SHELTERS` 배열)이 여전히 손으로 넣은 값이고(§6.2), 차량/도보 시간도 진짜 도로 API가 아니라 가정 속도(차량 30km/h, 도보 4km/h) 기반 직선거리 근사(§6.3)다 — 카카오/네이버 키 받으면 `/evacuation-route` 백엔드(§6.4)부터 실연동하면 됨.
1-1. **(최우선, §6과 같은 우선순위 — 사용자가 "독창성 축"으로 직접 지목, UI는 개념 프리뷰만 있고 실제 알고리즘 미착수)** 고립마을 자동탐지(그래프 연결성 분석) — §6과 사실상 한 세트 기능이다. 아래 **§7 전체** 참조. `IsolationPanel.tsx`가 예시 시나리오만 보여주는 상태.
2. **(완료)** ~~토사 유실 + 침수 시뮬레이션~~ — §1.5에 있음, 커밋 `4759d2a` 이후 여러 번 개선(색상 버그 `4ce6ef1`, 건물 부족 문제는 VWorld 연동 `abcb95a`로 해결).
3. 트랙①②가 아직 안 왔으므로, 계속 목업 모드로 진행하되 `contracts/`가 실제로 맞는지 검증할 방법이 없다는 리스크를 사용자에게 상기시킬 것.
4. [ARCHITECTURE.md §9](ARCHITECTURE.md) 데모 시나리오(산청 타임라인 재연)를 위한 실제 리허설 — 지금은 각 기능이 개별적으로는 동작하지만, 처음부터 끝까지 이어지는 데모 스토리로 리허설된 적은 없음.
5. `/whatif` 페이지의 강수 슬라이더는 아직 목업이라 값이 안 바뀜 — 실제 Module A/B 붙거나 데모용 합성 응답을 만들면 살아남.
6. Module H(시민 신고 역검증) 트리거 UI가 아직 없음 — 지금은 `precursor_flag`가 목업이라 항상 `false`라 UI에서 확인 불가.
7. 3D 지도 로직이 트랙별로 계속 커지고 있음(도로/건물/교량 전부 VWorld 실데이터로 교체, 지형 z15 이상에서 exaggeration 감쇠 등) — 8/27 지도-메인-화면 개편으로 `ui/src/app/map3d/page.tsx`의 로직이 `ui/src/components/MapExplorer.tsx`로 옮겨졌다(`map3d/page.tsx`는 이제 그걸 감싸는 얇은 래퍼). §1.5를 이 문서보다 코드와 `git log`로 항상 재확인할 것, 이 문서가 못 따라잡았을 수 있음.
8. `app/page.tsx`(새 홈)가 이제 지도를 배경으로 깔고 메뉴(대시보드/모델 성능/대피소 찾기/고립마을 위험/What-if)를 누르면 지도 위 글라스 패널로 뜨는 구조다 — 원클릭 승인은 시민 화면에서 빠졌지만 `/approve` 라우트에는 그대로 남아있음(관 대응용). 새 패널 만들 때는 `GlassPanel.tsx`로 감싸고 `app/page.tsx`의 `MENU`/`PANEL_TITLE`에 등록하면 된다.
9. **(최우선급, 사용자가 명시적으로 요청, 2026-08-28)** 수해 모델 고도화 — 아래 **§8 전체** 참조. 모델 성능 시각화(§8.1)는 UI 목업까지 완료, 실시간 관측 데이터 연동(§8.2)은 외부 API 키(WAMIS 등)가 있어야 시작 가능 — 아직 미착수.
10. **(최우선, 외부 리서치 반영, 2026-08-28)** 공모전 수상 전략 — 위 1~9번 항목보다 먼저 **아래 §9 전체**를 읽을 것. 서비스 개발 부문으로 트랙 정정 완료, 개발 리소스를 새 기능:검증 = 20:80으로 재배분, 산청 leakage-free 백테스트(§9.3)가 프로젝트 전체 최우선 단일 과제로 확정됨. 특히 위 1~1-1번(대피경로·고립마을)과 9번(수해모델)의 실제 우선순위가 이 §9의 S/A/B/C 티어(§9.2)로 재정렬됐으니 착수 전 대조할 것.

---

## 6. 다음 작업 상세 명세 — 주민 대피 경로 (네이버/카카오 길찾기)

사용자 요청 원문(2026-08-27): "네이버 지도 최적경로처럼, 예상되는 피해를 벗어난 가장 가까운 대피소가 어딘지, 자동차로 이동시 이동시간 얼마 도보로 얼마" — 그리고 "네이버/카카오 길찾기로 해놓고" (자체 A* 대신 외부 길찾기 API로 확정).

이건 [ARCHITECTURE.md §5 Module E](ARCHITECTURE.md)(`module_e_routing`)에 이미 계약이 있는 기능이다. Module E의 "위험가중 A*" 알고리즘 서술은 **자체 구현 대신 네이버/카카오 길찾기 API로 대체**하기로 확정됐다 — 계약의 입출력 필드(`shelter_id`/`route_5179`/`eta_min`/`time_feasible`/`time_margin_min`/`fallback_used`)는 그대로 유지하되, 그 값을 만드는 내부 구현만 바뀌는 것.

> **업데이트(2026-08-27, 추가 요청)**: "대피소 찾기는 UI에 입력한 내 현재 위치를 기반으로 최적경로를 찾아 3D 지도에 표시하면서 길을 안내해야 한다"는 요청이 추가됐다 — 즉 출발지(`origin`)가 지금처럼 고정된 데모 좌표(`SANGCHEONG_DEMO_INPUT`)가 아니라 **사용자의 실제 현재 위치**여야 하고, 선택한 경로가 사이드 패널 리스트뿐 아니라 **3D 지도 위에 실제로 그려져야** 한다. 사용자 본인도 "카카오/네이버 지도 API 연결하면 해결되겠지?"라고 예상 — 맞다, 아래 6.1의 API가 그대로 해결책이다. 상세는 아래 **6.8**·**6.9**(신규) 참조. 현재 `ui/src/components/panels/EvacuationPanel.tsx`(대피소 리스트, 목업)와 `ui/src/components/panels/IsolationPanel.tsx`(고립마을, 개념 프리뷰)가 이미 메뉴에 들어가 있으니 — 실제 구현은 새 화면을 만드는 게 아니라 이 두 파일 + `MapExplorer.tsx`를 연결하는 작업이다.

### 6.1 사용자가 먼저 해야 하는 것 (Claude Code가 대신 못 함 — 계정 생성 금지 정책)
아래 중 하나(또는 둘 다) API 키가 필요하다. **VWorld 키를 받았던 것과 같은 순서로 진행**하면 된다: 사용자에게 회원가입 링크를 안내 → 발급받은 키를 받아서 `.env`에 추가 → 실제 키로 몇 가지 엔드포인트를 curl로 찔러보며 정확한 요청 형식을 확인(VWorld 때 `LT_C_SPBD`/`LT_L_MOCTLINK` 레이어 코드를 이렇게 찾았음, §1.5·§3 참조) → 백엔드 프록시 구현.

- **카카오모빌리티 길찾기 API** (추천, 가입이 더 간단함): [developers.kakao.com](https://developers.kakao.com) 가입 → 애플리케이션 생성 → "카카오내비"/"모빌리티" API 활성화 → REST API 키 발급. 무료 티어 있음(호출량 제한 있으니 developers.kakao.com에서 실제 한도 확인). **자동차 길찾기만 제공, 도보 길찾기 API는 없음** — 아래 6.3 참조.
- **네이버 클라우드플랫폼(NCP) Directions API**: [ncloud.com](https://www.ncloud.com) 가입 → Maps > Directions 5/15 API 활성화 → Client ID/Secret 발급. 결제수단(카드) 등록이 필요할 수 있음(무료 크레딧 있는지 가입 시점에 확인). 이것도 **자동차 전용**.

`.env`에 다음 중 확보한 것을 추가 (VWORLD_API_KEY와 같은 파일, 이미 git-ignore됨):
```
KAKAO_REST_API_KEY=...
# 또는
NAVER_MAPS_CLIENT_ID=...
NAVER_MAPS_CLIENT_SECRET=...
```

### 6.2 대피소 후보 데이터
- 이상적: 안전Dream / 국가재난안전포털 API, 또는 공공데이터포털의 "전국 대피소 표준데이터"(무료). VWorld처럼 실제 키로 레이어/엔드포인트를 프로빙해서 정확한 스펙을 확인할 것 — 공개 문서만 믿지 말 것(이번 세션에서 VWorld 건물/도로 레이어 코드를 문서로는 못 찾고 실제 API 호출 응답으로 찾아냈다, §1.5 참조).
- **이게 당장 없어도** 손으로 넣은 대피소 후보 2~3곳(위경도 좌표, 상능마을 근처)으로 나머지 파이프라인(경로탐색·UI)을 먼저 완성할 수 있다 — 데이터만 나중에 API로 교체하면 됨(이번 세션에서 건물/도로를 했던 것과 같은 패턴: 목업 → 실데이터 교체).

### 6.3 도보 시간 처리 — 중요한 제약사항
카카오/네이버 둘 다 **공개 개발자 API로는 도보 길찾기를 제공하지 않는다** (자체 확인 필요 — 이 문서 작성 시점 기준 웹 검색으로는 못 찾음, 최신 상황 다시 확인할 것). 그래서:
- **1차 구현**: 직선거리(하버사인 공식) ÷ 평균 도보속도(4km/h)로 근사. UI에 "실제 보행 경로 아님, 직선거리 근사치" 배지를 반드시 표시(§6 불확실성 표기 원칙과 동일한 원칙).
- **업그레이드 경로**: OSRM 공개 데모 서버의 foot 프로파일, 또는 GraphHopper 무료 티어(별도 API 키) 등 OSM 기반 보행자 라우터로 교체 가능하도록 함수를 분리해둘 것 (`getWalkingRoute(origin, dest)` 같은 인터페이스로 추상화해서 나중에 구현체만 갈아끼우기 쉽게).

### 6.4 백엔드 구현 (api_server.py에 추가할 것 — 지금 있는 `/vworld/*` 엔드포인트와 같은 패턴)
1. `GET /shelters?bbox=...` — 대피소 후보 목록 (실데이터 or 손으로 넣은 fallback 리스트). VWorld 프록시들처럼 서버에서만 외부 키를 다루고 프론트에는 안 보낸다.
2. `POST /evacuation-route` — 요청 바디: `{origin: {lon, lat}, hazard_polygon: GeoJSON Polygon}` (`hazard_polygon`은 지금 `/map3d`의 침수/토사 볼륨 폴리곤이나 나중에 실제 Module A/B `risk_polygons`를 그대로 재사용). **`origin`은 이제 고정 데모 좌표가 아니라 6.8에서 받는 사용자 현재 위치(또는 수동 입력 위치)다.**
   - 처리 순서 (문서 §5 Module E 알고리즘을 그대로 따름):
     1. `hazard_polygon` 안에 있는 대피소 후보 제외 (shapely `polygon.contains(point)` — geopandas 이미 의존성에 있음, 새 패키지 불필요)
     2. 남은 후보 각각 카카오/네이버 Directions API로 차량 경로·시간 요청 (서버 사이드 호출, `requests` 라이브러리 이미 있음)
     3. 도보 시간은 6.3 방식으로 계산
     4. `eta_min ≤ time_budget_hours×60` 만족하는 후보 중 최단시간 선택 (동률이면 수용인원 큰 쪽)
     5. 아무도 시간 내 도달 못하면 `fallback_used: true` + 가장 가까운 안전지대로 목적지 변경 + 경고 메시지 (§5 Module E: "생명안전상 가장 중요한 예외처리 — 절대 조용히 넘어가지 않는다")

### 6.5 프론트 구현 (`ui/src/components/panels/EvacuationPanel.tsx` + `ui/src/components/MapExplorer.tsx`)
- 사이드 패널에 "대피소 찾기" 섹션 추가 — 지금 있는 토사/침수 슬라이더(`debrisDepth`/`floodDepth`) 값이 바뀔 때마다 이 패널도 다시 계산되게 연결(디바운스). **위험지역이 넓어지면 대피소가 실시간으로 "도달 가능"→"불가능"으로 바뀌는 걸 보여주는 게 골든타임 서사에 제일 강하게 먹힌다** — 사용자가 이미 이 페이지에서 반복해서 강조한 패턴(3D 볼륨이 실제 건물/도로와 겹치는 걸 보여주는 것과 같은 논리).
- 대피소 후보 리스트(거리순), 각 항목에 차량 X분 / 도보 Y분(색으로 구분, 이모지 없음), 수용인원, 도달가능 배지(초록/빨강) — `EvacuationPanel.tsx`에 이미 있음(§6.8 완료로 geolocation 기반 하버사인 근사까지는 붙어있음), 실제로는 이 계산 로직을 `/evacuation-route` 응답으로 교체.
- 지도 위에 선택 대피소까지 실제 경로 라인 — 카카오/네이버가 반환하는 폴리라인 좌표를 그대로 GeoJSON LineString으로 그리면 됨(이미 5179→4326 재투영 패턴이 `module_o_orchestrator/geo.py`에 있으니 필요하면 참고, 단 카카오/네이버는 보통 4326으로 바로 응답하니 재투영 불필요할 가능성 높음 — 응답 스펙 직접 확인할 것)
- "부족" 배지는 크고 명확하게 — 기존 `/map3d`의 debris/flood 경고 UI 톤 참고

### 6.6 계약(`contracts/module_e`) 확장 제안 — 3인이 아니라 이제 4인 합의 필요, 임의로 바꾸지 말 것
지금 `module_e.example.json`은 이동수단 하나(`eta_min`)만 있다. 차량/도보 둘 다 보여주려면 필드 확장이 필요한데, 제안 형태:
```json
{
  "shelter_id": "S001",
  "route_5179": { "...": "..." },
  "modes": {
    "car": { "eta_min": 14.5, "route_confidence": "high", "source": "kakao_directions" },
    "walk": { "eta_min": 52.0, "route_confidence": "low", "source": "straight_line_approx" }
  },
  "time_feasible": true,
  "time_margin_min": 105.5,
  "fallback_used": false
}
```
**이건 제안일 뿐이다.** 문서 §4.3: "`contracts/` 변경은 Day 1 이후 4인 합의 없이 임의 수정 금지"(2026-08-27 4인 체제 개편 이후, ARCHITECTURE.md §11 참조) — 지금 Module E 소유는 트랙④(동현)이니 나머지 세 트랙에 먼저 공유하고 합의된 뒤에 `contracts/module_e.example.json`/`module_e.schema.json`을 실제로 바꿀 것. 그 전까지는 이 확장 필드를 API 응답에만 임시로 붙여서 써도 됨(계약 파일 자체는 안 건드림).

### 6.7 착수 순서 제안
1. 외부 키 없이: 손으로 넣은 대피소 후보 2~3곳 + 직선거리 도보시간 근사만으로 UI 뼈대부터 완성 (지도에 후보 마커, 사이드 패널 리스트, 도달가능 배지)
2. 카카오/네이버 키 받으면: 차량 경로만 실제 API로 교체 (`/evacuation-route` 백엔드 엔드포인트)
3. 대피소 실데이터 API 연동 (있으면)
4. `contracts/module_e` 확장 제안을 팀에 공유
5. 아래 6.8(현재 위치)·6.9(3D 지도 표시·안내)로 "찾기"에서 "안내"로 완성

### 6.8 신규 — 사용자 현재 위치를 출발지로 (2026-08-27 추가 요청, **완료**)
지금까지의 `origin`은 전부 `SANGCHEONG_DEMO_INPUT`(데모용 고정 좌표)이었다. 실제 배포에서는 **접속한 사용자의 현재 위치**가 출발지여야 한다.

> **완료(2026-08-27)**: `EvacuationPanel.tsx`의 "내 위치로 찾기" 버튼이 아래 1번대로 구현됨. 단 지금은 `/evacuation-route` 백엔드가 없어서 받은 좌표로 직접(하버사인) 거리를 계산해 화면에서 바로 보여준다 — 백엔드 연동은 아직임. 2번(폴백) 중 **①(지도 클릭)도 이제 구현됨** — "지도에서 선택" 버튼이 `MapExplorer`의 새 `pickOrigin`/`onOriginPicked` prop으로 다음 지도 클릭 한 번을 잡아 출발지로 쓴다(②는 원래 있던 검색창으로 대체). 3번(에러 메시지)도 구현됨. 실제 배포된 사이트에서 사용자가 직접 눌러서 정상 동작 확인함(이 세션 브라우저 pane은 MapLibre `load` 이벤트에 도달을 못 해 — §3의 WebGL 컴포지팅 한계와 동일 원인 — 직접 검증은 못 했었음, 실제 배포본에서 확인 완료).

1. **브라우저 Geolocation API**로 위치 요청: `navigator.geolocation.getCurrentPosition(success, error, { enableHighAccuracy: true, timeout: 8000 })`. 반환되는 `coords.longitude`/`coords.latitude`는 EPSG:4326 — `/evacuation-route`의 `origin: {lon, lat}`에 그대로 넣으면 된다(백엔드에서 5179로 변환).
2. **중요한 제약**: Geolocation API는 **secure context(HTTPS 또는 localhost)에서만 동작**한다 — 배포 도메인이 HTTP면 조용히 실패하니 배포 전 HTTPS 확인 필수.
3. **폴백(반드시 필요, 조용히 넘어가지 말 것 — §6 불확실성 표기 원칙과 같은 톤)**: 사용자가 위치 권한을 거부하거나 실패하면 ① 지도 위 클릭으로 직접 출발지 지정, 또는 ② 지금 있는 `/search`(주소 검색창)로 동네 이름을 검색해 그 결과의 `center`를 출발지로 쓰는 두 가지 수동 입력 경로를 제공할 것. "위치를 가져올 수 없습니다 — 지도를 클릭하거나 주소를 검색해주세요" 같은 명시적 안내가 있어야 한다.
4. UI 자리: `EvacuationPanel.tsx` 상단에 "내 위치로 찾기" 버튼 하나 + 위 폴백 두 가지를 같은 패널 안에 배치하는 게 가장 자연스럽다.

### 6.9 신규 — 3D 지도 위 경로 표시 + 길 안내 (2026-08-27 추가 요청, **완료(직선 근사 단계까지)**)
현재 `EvacuationPanel.tsx`(사이드 글라스 패널)와 `MapExplorer.tsx`(3D 지도)는 `app/page.tsx`의 형제 컴포넌트로 **서로 분리돼 있다** — 8/27 지도-메인-화면 개편 때 이렇게 나뉘었다.

> **완료(2026-08-27)**: 아래 "권장" 방식대로 구현됨 — `app/page.tsx`가 `evacuationRoute` 상태를 끌어올려 `MapExplorer`엔 `route` prop, `EvacuationPanel`엔 `onSelectRoute` 콜백으로 내려준다. `MapExplorer.tsx`가 `EvacuationRoute` 타입을 export하니 다른 곳에서 재사용 가능. 지도엔 `evacuation-route`(점선 시안색 라인, 아래 1번)·`evacuation-markers`(출발/도착 원형 마커, 2번) 두 소스가 추가됐고, 경로 선택 시 3번대로 카메라도 이동한다 — **다만 지금은 직선(하버사인) 좌표라 점선으로 그려서 "실제 도로 경로 아님"을 시각적으로도 표시함**. 카카오/네이버 실경로가 들어오면 `route.origin`/`route.destination` 대신 실제 폴리라인 좌표 배열을 넣도록만 바꾸면 되고, 레이어/이펙트 구조는 그대로 재사용된다.

패널에서 고른 경로를 지도가 그리려면 둘을 연결해야 하는데, 방법은 둘 중 하나였다(실제로는 아래 첫 번째로 구현):
- **(채택)** 선택된 경로/출발지 상태를 `app/page.tsx`로 끌어올려서(`useState`) `MapExplorer`에 `route` prop으로 내려주고, `MapExplorer`가 그 prop이 바뀔 때마다 지도에 그리는 `useEffect`를 추가.
- MapExplorer가 이미 여러 `useRef`(`simUpdateRef`, `highlightUpdateRef` 등)로 "외부에서 지도를 갱신하는 함수를 노출"하는 패턴을 쓰고 있으니, 같은 패턴으로 `routeUpdateRef`를 추가하는 방법도 있었음(안 씀 — prop 방식이 이 기능 규모엔 더 간단했음).

지도에 그린 것(기존 `bridges`/`debris-flow` GeoJSON 소스를 추가하던 것과 동일한 패턴 — `map.addSource` + `map.addLayer`):
1. **경로 라인**: 지금은 직선 좌표 2점을 GeoJSON `LineString` `line` 레이어로, 점선(`line-dasharray`)+시안색(`#22d3ee`)으로 — 토사=빨강/침수=파랑/고립=마젠타와 안 겹침. 카카오/네이버 실경로가 들어오면 좌표 배열만 폴리라인으로 교체하고 점선을 실선으로 바꾸면 됨.
2. **출발지·도착지 마커**: `circle` 레이어 하나에 `role` 속성(origin/destination)으로 색 분기(`#38bdf8`/`#f472b6`).
3. **카메라**: 경로 선택 시 `map.fitBounds(...)`로 출발/도착 둘 다 보이게 이동(기존 `flyTo`/검색 결과 이동과 같은 패턴).

**"길 안내"의 범위**: 카카오/네이버 웹 API 둘 다 턴바이턴 음성 안내는 앱 SDK/네이티브 상품 쪽이라 REST Directions API로는 보통 안 됨(가입 시점에 재확인할 것) — 이 프로젝트 MVP 범위는 "경로 시각화 + 총 소요시간/거리 표시 + 카메라 자동 이동"까지로 충분하다. 진행률 기반으로 카메라가 경로를 따라가는 애니메이션(진짜 내비게이션처럼)은 있으면 좋지만 우선순위 낮음(여유 있으면 §6.7의 5번 이후 확장 과제로).

---

## 7. 다음 작업 상세 명세 — 고립마을 자동탐지 (독창성 축 4, 신규 제안)

사용자 요청(2026-08-27): "독창성을 따졌을 때... 산사태홍수시뮬레이션은 기존에 있는 거라 뭔가 정말 신박한 게 필요한데." — 3D 침수/토사 볼륨 자체는 상용 CFD 툴(FLOW-3D 등)도 하는 거라 독창성 심사에서 차별화가 안 됨. 대신 문서 TL;DR("산사태→하천범람→**고립**까지 이어지는 재해 사슬")의 마지막 고리인 **"고립"**이 지금까지 한 번도 구현/시각화된 적이 없다는 걸 짚어서, 이걸 **독창성 축 4로 새로 제안**했고 사용자가 최우선으로 확정했다.

> **주의**: 이건 ARCHITECTURE.md v2.4 원문에 있던 계약이 아니라 **트랙③이 이번에 새로 제안한 기능**이다. §5 Module E/O 계약을 건드리는 게 아니라 완전히 새로운 파생 계산(그래프 분석)이라, 굳이 `contracts/`를 고칠 필요 없이 UI-3D 레이어에서 자체적으로 계산하면 된다. 다만 이게 데모의 핵심 서사가 될 거라면, 팀에 "독창성 축 4"로 문서에 정식 추가할지는 상의할 것.

### 7.1 핵심 아이디어
"물이 여기까지 찼다"(단순 침수 시각화)가 아니라 **"이 마을은 이제 대피소로 가는 길이 하나도 안 남았다"**를 그래프 알고리즘으로 증명한다. §6(대피 경로)의 자연스러운 연장 — 대피 경로 탐색이 "전부" 실패하는 지점이 곧 고립 지점이다.

### 7.2 알고리즘
1. **그래프 구성**: `/vworld/roads`(`LT_L_MOCTLINK`)로 받은 도로 링크들을 노드-엣지 그래프로 변환. 각 링크의 시작/끝 좌표를 노드로 삼되, **부동소수점 오차 때문에 좌표가 미세하게 다른 지점을 같은 노드로 스냅**해야 함(예: 소수점 5자리 반올림 또는 근접 반경 내 노드 병합) — 안 하면 도로가 실제로는 이어져 있는데 그래프상 끊긴 것처럼 나옴.
2. **위험 엣지 제거**: 현재 슬라이더 값 기준 침수/토사 볼륨 폴리곤과 **교차하는 엣지를 그래프에서 제거**(완전 통행불가로 볼지, 매우 높은 weight를 줘서 "우회 가능하지만 비효율"로 볼지는 구현하면서 결정 — 처음엔 단순하게 완전 제거로 시작 추천).
3. **도달가능성 계산**: 대피소 후보(§6의 shelter 목록) 각각의 그래프 노드에서 **역방향 BFS/Dijkstra**를 돌려 "대피소 중 최소 1곳이라도 도달 가능한 노드 집합"을 구함(Union of reachable sets). `networkx` 라이브러리 추천(`bfs_tree`, `single_source_shortest_path` 등) — 지금 의존성엔 없음, `requirements.txt`에 추가 필요.
4. **건물 매핑**: VWorld 건물(`/vworld/buildings`, `LT_C_SPBD`) 각각의 무게중심에서 가장 가까운 도로 노드를 찾고, 그 노드가 3번의 "도달 가능 집합"에 없으면 그 건물은 **고립**.
5. **클러스터링**: 개별 건물 단위로 빨갛게 칠하면 산발적으로 보이니, 고립된 건물들을 공간적으로 묶어서 하나의 "고립 구역" 폴리곤으로 — `shapely`의 `unary_union` + `convex_hull`(간단), 또는 DBSCAN(더 정교하지만 새 의존성 `scikit-learn` 필요, 굳이 안 써도 됨).

### 7.3 성능 — 슬라이더 반응성 위해 캐싱 필수
- 그래프 자체(도로 노드/엣지 스냅)를 슬라이더 움직일 때마다 매번 새로 만들면 느림 — **AOI(뷰포트) 진입 시 한 번만 구성해서 캐싱**하고, 슬라이더가 바뀔 때는 "위험 엣지 제거 + 도달가능성 재계산"만 다시 실행.
- `networkx`는 순수 파이썬이라 큰 그래프에서 느릴 수 있음 — 상능마을 같은 작은 AOI(노드 수 수백~수천)면 실시간 가능. 전국/대도시 단위로 넓히면 성능 재검토 필요(예: `igraph`로 교체 고려).

### 7.4 백엔드 (api_server.py에 추가)
- `POST /isolation-check` — body: `{hazard_polygon: GeoJSON Polygon, bbox: [minLon,minLat,maxLon,maxLat]}` (대피소 목록은 서버가 §6의 `/shelters`에서 재사용)
- 응답 제안: `{isolated_areas: GeoJSON FeatureCollection, isolated_building_count: N}`
- `requirements.txt`에 `networkx` 추가 필요

### 7.5 프론트 (`ui/src/components/MapExplorer.tsx` — 8/27 지도-메인-화면 개편으로 `app/map3d/page.tsx`에서 이 컴포넌트로 로직이 옮겨졌다, `app/map3d/page.tsx`는 이제 이걸 감싸는 얇은 래퍼일 뿐)
- 침수/토사 슬라이더(`debrisDepth`/`floodDepth`) 변경 시 디바운스 호출(기존 `updateVWorldRoads` 등과 같은 패턴) → `isolated_areas`를 새 GeoJSON 소스에 `setData`
- 시각화: **빨간색 pulse 애니메이션** 폴리곤(기존 토사=빨강/침수=파랑과 겹치지 않게 마젠타·자주 계열 검토) — MapLibre paint property를 `setInterval`로 주기적으로 바꾸거나 `line-opacity`/`fill-opacity` transition 활용
- 사이드 패널(`ui/src/components/panels/IsolationPanel.tsx`, 지금은 개념 프리뷰 목업)에 "N개 건물 고립 위험" 카운터(기존 `floodedBuildingCount` 패턴 그대로 재사용 가능)
- 가능하면 골든타임 시간슬라이더랑 연결해서 "T+N분에 이 마을이 고립됩니다" 같은 예측 문구까지 — 있으면 데모 임팩트 훨씬 커짐(우선순위 낮음, 여유 있으면)

### 7.6 착수 순서
1. `networkx` 추가, 그래프 구성 + 노드 스냅 로직부터 (제일 까다로운 부분 — 여기서 시간 많이 먹을 수 있음, 먼저 작은 AOI로 검증할 것)
2. 위험 엣지 제거 + 역방향 도달가능성 계산
3. 건물 매핑 + 클러스터링(간단한 convex hull로 시작, 나중에 정교화)
4. 프론트 시각화 + 슬라이더 연동
5. §6(대피 경로) 완료 후 셋을 하나의 서사로 리허설: "수위 상승 → 특정 대피소 도달 불가(§6) → 결국 마을 전체 고립(§7)"

---

## 8. 다음 작업 상세 명세 — 수해 모델 고도화 + 실시간 관측 데이터 연동 (신규, 2026-08-28)

사용자 요청 원문(2026-08-28): "시간은 아직 꽤 있으니까 수해를 담당하는 모듈들의 수준을 꽤 끌어올릴 필요가 있어... ML 기반으로 돌리는거면 그래프부터 포함해서 과학적으로 성능을 입증하고 결과를 입증할 수 있는 시각자료나 지표가 모두 떠있는게 더 좋을수도 있어. 그리고 실시간 수위센서 데이터 등 정확도를 높이고 실현도를 높일 수 있는 데이터는 모두 긁어와야돼. 산청 서울 기준으로."

**이건 두 갈래다:**

### 8.1 모델 성능 시각화 (트랙③ 완료, UI만) — Module A/B가 실제 학습되면 이어받을 것
"위험 78%, 신뢰구간 [65%,88%]" 텍스트만으론 진짜 ML 모델처럼 안 보인다는 지적 — AUC/ROC, 정밀도·재현율, 혼동행렬, 사례별 시계열 예측 곡선을 보여주는 전용 패널을 만들어뒀다. **완료(2026-08-28)**: `ui/src/components/panels/ModelPerformancePanel.tsx`(+ `ui/src/components/charts/MiniCharts.tsx`, 새 차트 라이브러리 없이 순수 SVG) — 메뉴에 "모델 성능"으로 들어가 있음. 산사태는 산청(2025.7.19), 하천범람·침수는 서울(2022.8.8 폭우) 사례 기준. **지금은 전부 목업 수치다** — 트랙①이 Module A/B를 실제로 학습시키면, 그 검증 결과(진짜 AUC/ROC/혼동행렬/시계열)로 이 파일의 `CASES` 객체 값만 갈아끼우면 화면은 그대로 재사용된다.

### 8.2 실시간 관측 데이터 연동 (신규, 아직 미착수 — 외부 API 키 필요)
Module A/B의 정확도·실현도를 높이려면 실시간 강수량·하천 수위 데이터를 입력으로 넣어야 한다. 이건 Module A/B의 실제 구현(트랙①, 민석)에 영향을 주는 작업이라 **UI 쪽에서 임의로 손댈 수 없고**, 아래는 실제로 연동할 때 참고할 후보 데이터 소스다(2026-08-27 세션에서 웹 검색으로 조사, 실제 API 키로 프로빙 안 해봤으니 VWorld 때처럼 공개 문서만 믿지 말고 키 받으면 직접 확인할 것):

- **국가수자원관리종합정보시스템(WAMIS)** — [wamis.go.kr](https://www.wamis.go.kr/) — 한강·낙동강·금강·영산강 4대강 홍수통제소를 전부 아우르는 통합 시스템. 실시간 수위·강수량·댐 수문정보 Open API 제공. **산청(낙동강 권역)과 서울(한강 권역)을 하나의 API로 커버할 가능성이 제일 높음 — 1순위 후보.**
- **한강홍수통제소(HRFCO)** — [hrfco.go.kr/web/openapiPage/openApi.do](https://www.hrfco.go.kr/web/openapiPage/openApi.do) — 수위·유량·강수량·댐·보·강우레이더·홍수예보 7종 Open API, 인증키는 `CertifyKeyMgr.do` 메뉴에서 발급. 이름은 "한강"이지만 실제 제공 자료가 전국 관측소까지 포함하는지는 실제 키로 확인 필요(경기데이터드림 등 2차 배포처도 있음).
- **기상청 API허브** — [apihub.kma.go.kr](https://apihub.kma.go.kr/) — 방재기상관측(AWS) 실시간 강수량·기온 등. 회원가입 + **휴대전화 연락처 등록 필수**(안 하면 API 이용 불가).
- **공공데이터포털** — [data.go.kr](https://www.data.go.kr/) — 위 기관들의 데이터셋을 REST(JSON/XML)로 재배포. 회원가입 + 활용신청 필요, 승인까지 시간이 걸릴 수 있음.

**사용자가 먼저 해야 하는 것**(VWorld/카카오 때와 같은 정책 — Claude Code가 계정 생성 대행 불가): 위 중 최소 WAMIS 하나는 가입해서 인증키를 받아 `.env`에 추가(`WAMIS_API_KEY=...` 같은 이름으로, VWORLD_API_KEY와 같은 파일). 받으면 VWorld 때처럼 실제 키로 산청·서울 인근 관측소 목록/실시간 값을 curl로 찔러봐서 정확한 응답 스펙부터 확인하고 `api_server.py`에 프록시 엔드포인트를 추가하는 순서로 진행할 것 — 이 부분은 Module A/B 입력에 실제로 들어가는 데이터라 트랙①과 먼저 상의하고 시작하는 게 맞다.

---

## 9. 공모전 수상 전략 (외부 리서치 반영, 2026-08-28)

사용자가 외부 리서치(ChatGPT 심층 리서치 PDF, 분석기준일 2026.8.28)를 공유하며 "이걸 우리 프로젝트에 반영해서 문서화하라"고 지시. 공식 공모전 배점·역대 수상작 44개의 질적 패턴·현재 GitHub 구현 상태(56커밋 시점)를 교차분석한 결과다. **원본 PDF는 로컬(`C:\Users\user\Desktop\하수범_공모전\Aquaguard.AI\`)에만 있고 저장소엔 없음** — 이 섹션이 실질적인 원본 대체다. README.md §15에 이 내용의 요약판(배점표+전략)이 이미 올라가 있으니, 여기서는 실행 단위까지 상세하게만 다룬다.

### 9.1 핵심 결론
아이디어 자체가 약해서가 아니라 **"아이디어·UI가 실제 모델·실데이터·검증보다 너무 앞서 있다"**는 게 현재 가장 큰 리스크. (사용자 지침: 이건 처음부터 UI를 먼저 만들고 모듈은 나중에 붙이는 의도된 개발 순서였으므로 "모듈보다 UI가 앞서갔다"는 지적 자체는 가볍게 볼 것 — 다만 **지금부터 그 격차를 실제로 좁혀야 한다는 결론은 유효**하다.) 그래서 개발 방향은 **새 기능 20% : 실데이터·검증·사용자 실증 80%**로 전환.

### 9.2 개발 우선순위 재정렬 (S/A/B/C 티어, 리서치 원문 기준)
예선·본선 기대효과·난이도·실패위험·시연효과를 종합한 상대적 우선순위다 — 합산 가능한 공식 점수가 아니라 작업 순서 비교용.

**S 티어 (지금 당장 최우선)**
- 공모전 공식 지원 플랫폼 자원 연결 + 배포 (Naver/KT/NHN Cloud, 위기데이터 중 최소 1곳 — 지금 Vercel/Render는 개발 프리뷰로 유지하되 제출용은 별도 연동 필요, 상세 규정상 플랫폼 활용이 필수로 명시됨)
- 산청 leakage-free 백테스트 (§9.3)
- Module A 실제 baseline (mock/example JSON 없이 실제 input→probability 출력 — 트랙①)
- 외부 재난전문가/실사용자 테스트 (협력성 15점 + 유용성 25점에 직접 영향, 의외로 가장 효율 높음)
- 실제 대피소·도로경로 연결 (직선 `route_placeholder` 제거 — 트랙④ §6과 연결됨)
- "자동 전파"를 human-in-the-loop로 재설계 (오늘 README/ARCHITECTURE §0에 이미 반영 완료)

**A 티어 (여유 되면)**
- What-if를 실모델에 연결 (트랙①의 실제 모델이 붙으면 자동으로 됨, 이미 그렇게 설계돼 있음)
- 두 번째 지역 out-of-sample 실행 (전국 지도보다 "같은 파이프라인이 코드 변경 없이 다른 지역에서 돌아간다"가 확장성 25점에 더 직접적)
- 고립마을 그래프 분석 (HANDOFF §7, 독창성 축 4)
- Module B 정교한 ML 모델

**B 티어 (낮은 우선순위)**
- 피해금액 상세 계산, 시민신고 역검증 완성, 모바일 최적화

**C 티어 (거의 효과 없음 — 발표에서 비중 최소화, 새로 안 만들어도 됨)**
- **3D 그래픽 추가 고도화** — 이미 충분히 앞서 있음, 더 예뻐져도 심사표엔 거의 안 잡힘
- **AI 챗봇/LLM 추가** — 본선 배점에 "AI 성능" 항목 자체가 없음. **지금 만들어둔 챗봇 UI는 유지하되, Gemini API 실제 연동은 우선순위 낮음** — 이 리소스를 S 티어 항목에 쓰는 게 훨씬 남는 장사
- 새로운 재난 종류 추가 — 오히려 범위 과다로 감점 위험

### 9.3 산청 백테스트 방법론 (leakage-free counterfactual backtesting)
Module A/B(트랙①) 담당이지만, 이 하나가 프로젝트 전체 약점을 한 번에 보완할 수 있는 가장 중요한 단일 과제라 상세히 남겨둔다.

**원칙**: 시간 `t`에서 모델이 보는 데이터는 반드시 그 시각 이전에 실제로 이용 가능했던 정보로 제한. 7/19 이후 확정된 산사태 위치·피해지도를 입력에 섞으면 data leakage.

**단계별로 반드시 보여줄 것**:
1. 산불 이전/직후 Sentinel-2로 burn scar·dNBR 산출
2. **첫 번째 검증(가장 중요, 아직 미검증)**: 3월 burn scar와 7월 landslide inventory가 실제로 같은 사면·소유역에서 공간적으로 중첩하는가 — GIS로 확인. 안 겹치면 산청은 "의사결정 지연 사례"로만 쓰고, fire→landslide 증폭 검증은 실제로 중첩하는 별도 사례를 찾아야 함(같은 "산청군"이라는 것과 같은 사면이라는 것은 전혀 다른 주장)
3. 입력시점: 그 시각까지의 AWS 강우 + 당시 발행된 예보만 사용
4. 위험판단: 모델 버전·threshold·confidence interval 표시
5. 핵심 시점 3개: `T_agent`(모델이 처음 임계치를 넘은 시간) / `T_event`(신뢰 가능한 자료로 확인한 최초 피해) / `T_official`(실제 경보·재난문자 시각)
6. 핵심 지표 2개(하나로 뭉뚱그리지 말 것): `hazard_lead = T_event - T_agent`(재난을 몇 분 먼저 맞혔는가) 와 `decision_latency_recovered = T_official - T_agent`(행정 의사결정 시간을 얼마나 회복했는가)는 서로 다른 주장이다
7. 결과: 그 시점에 실제로 접근 가능했던 대피소·도로·마을
8. 불확실성: threshold를 바꾸면 lead time과 false alarm이 어떻게 달라지는지
9. **Ablation study 권장**: `동일 모델 - dNBR` vs `동일 모델 + dNBR`을 비교해 산불흉터 계수의 실제 기여도를 증명(산림청도 이미 산불피해지를 반영하고 있으므로, "멋있어서 붙인 계수"가 아니라 실제 성능 차이를 보여줘야 함)
10. 평가지표는 ROC보다 **PR-AUC/Brier score/공간 hit rate**를 우선 — 산사태는 희귀 positive 이벤트라 ROC만으론 과대평가될 수 있음

**절대 하면 안 되는 말**: "이 시스템이 있었다면 N명을 살릴 수 있었다"(대피순응률·이동시간·현장접근성 검증 없이는 causal claim 아님). 대신 "공식 경보보다 N분 빠른 actionable signal을 생성했다", "그 시점 기준 N가구가 아직 안전대피소까지 도달 가능한 경로를 가지고 있었다"처럼 증명 가능한 결과만 말할 것.

`ui/src/components/panels/ModelPerformancePanel.tsx`가 이 결과값(AUC/ROC 좌표, 정밀도·재현율·F1, 혼동행렬, T_agent/T_event/T_official 시계열)을 받을 UI로 이미 완성돼 있다 — 목업 `CASES` 객체를 실제 값으로 갈아끼우면 됨.

### 9.4 Minimum Award-Worthy Product (MAWP) 체크리스트
모든 모듈을 완성할 필요는 없다 — 오히려 지금의 광범위한 기능 목록을 다 살리려는 게 위험. 반드시 살아있어야 하는 흐름 하나: **실제 입력 → 실제 위험판단 → 재해연쇄 → 실제 경로/고립 판단 → 담당자 의사결정 → 확보된 시간의 정량적 결과.**

| 순서 | 작업 | 완료 기준 |
|---|---|---|
| 1 | 서비스 개발 부문 전략 확정 + 공식 지원 플랫폼 자원 신청 | cloud/data 자원 승인·실제 API 호출 |
| 2 | README/ARCHITECTURE 사실성 정리 | mock/real 구분, 08:00·A_max 표현 — **오늘 완료** |
| 3 | 산청 burn scar × landslide 공간검증 | 실제 overlap map과 비율 산출 |
| 4 | Module A 실제 baseline 완성 | example JSON 없이 실제 input→probability |
| 5 | 산청 leakage-free backtest | T_agent/T_event/T_official, leadtime·오차지표 |
| 6 | 실제 대피소·도로 routing | 직선 `route_placeholder` 제거, 위험구간 회피 |
| 7 | 외부 전문가·실사용자 pilot | 최소 3~5명 task test, 시간·만족도·피드백 기록 |
| 8 | 지원 플랫폼 기반 공개 배포 | 외부 URL에서 end-to-end 실행·smoke test |
| 9 | 두 번째 지역 또는 negative-control 검증 | 같은 pipeline이 코드 변경 없이 실행 |
| 10 | 10분 데모 동결·반복 리허설 | 문제→실데이터→위험→경로→승인→골든타임이 중단 없이 10분 내 완료 |

우선순위 충돌 시 원칙: 3D 기능 vs 검증 → 검증. 고립마을 기능 vs 모델 정확도 → 모델. Module B를 거대한 AI로 만들기 vs 실제 도로경로 완성 → 실제 경로.

### 9.5 가장 위험한 심사질문과 준비된 답
| 예상 질문 | 왜 치명적인가 | 준비할 답 |
|---|---|---|
| "예측이 실제로 맞습니까?" | 핵심 A/B가 현재 mock | 산청 hold-out backtest, PR-AUC/Brier/공간 hit rate |
| "산림청도 산불피해지를 위험도에 반영하는데 뭐가 다르죠?" | 독창성 축 하나를 바로 무너뜨릴 수 있음 | "예측 자체가 아니라 downstream 의사결정 체인" 비교도 (§0.1에 이미 반영) |
| "화재지역과 7월 산사태 위치가 실제로 겹칩니까?" | 같은 '산청군'≠같은 사면·유역 | 3월 dNBR burn scar × 7월 landslide inventory 공간교차 (§9.3-2, 미검증) |
| "공무원이 진짜 이 시스템으로 경보를 자동 발령할 수 있나요?" | 법·책임성 공격 | ~~human-in-the-loop, advisory mode, audit log, SOP~~ — **2026-08-29부로 이 답이 더 이상 유효하지 않음.** 사용자가 "시민 직접배포 앱 취지에 안 맞고 위험도가 높다"는 이유로 지자체 담당자 승인 게이트("원클릭 승인")를 핵심 아키텍처에서 완전히 제외하기로 결정 — Module O는 이제 승인 대기 없이 시민 역검증(Module H)만으로 곧바로 경보격상·주민전파로 넘어간다(§5 Module O 상태머신 7단계로 축소, ARCHITECTURE.md 동일 반영). 관련 코드(`store.py`의 `AlertStore` 승인 상태머신, `POST /approve/{alert_id}`, `ApprovePanel.tsx`, `/approve` 라우트)는 아직 삭제 안 하고 남겨뒀다 — 문서·아키텍처에서만 제외, 코드 삭제 여부는 별도 확인 필요. **이 질문에 대한 새 답은 아직 미해결** — 승인 게이트가 없는 채로 법·책임성 공격에 어떻게 답할지 발표 전까지 반드시 정리할 것(예: 시민 역검증 신뢰도 임계치를 매우 보수적으로 잡기, 오탐 시 자동 정정 채널, 법률 자문). |
| "이 화면의 숫자는 실제인가요, 데모인가요?" | 여러 핵심 값이 example JSON·placeholder | 모든 화면에 REAL/MODEL/SIMULATION provenance 표시 — **아직 미착수, UI 작업 후보** |

### 9.6 본선 10분 발표 구조 (나중에 발표자료 만들 사람 참고용)
10분 동안 기능을 하나씩 소개하는 방식은 비추천("Module A입니다, B입니다, 3D지도입니다..."는 복잡해 보이기만 함). 하나의 질문을 처음부터 끝까지 밀어붙이는 구조 권장: **"산청에서 위험신호가 있었던 시각과 실제 대피 사이에 사라진 시간을 AquaGuard가 얼마나 되찾을 수 있었는가?"**

| 시간 | 내용 | 화면 |
|---|---|---|
| 0:00~0:45 | 실제 산청 사건과 문제 | 실제 타임라인 하나 |
| 0:45~1:30 | 기존 시스템이 이미 잘하는 것과 남는 gap | 산림청 시스템 vs AquaGuard 비교 |
| 1:30~2:10 | AquaGuard 한 문장 | disaster-chain 구조도 |
| 2:10~2:40 | 데이터·모델 검증 | dNBR·강우·backtest metrics |
| 2:40~6:20 | **LIVE DEMO** | 실제 2025 타임슬라이더 |
| 6:20~7:10 | 실제 경보 vs AquaGuard | 골든타임 카운터 |
| 7:10~8:00 | 사용자 실증 | 공무원/전문가 테스트 결과 |
| 8:00~8:50 | 전국 확장 | 두 번째 지역 실행 결과 |
| 8:50~9:30 | 운영·플랫폼 | 공모전 플랫폼 cloud/data architecture |
| 9:30~10:00 | 마지막 메시지 | "위험지도를 대피결정으로 바꾼다" |

LIVE DEMO에서 중요한 건 기능 개수가 아니라 **상태 변화**: 강우 시간슬라이더를 움직인다 → 산사태 위험 상승 → 특정 도로가 위험영역과 겹침 → 대피소 A 경로 불가능 → 대피소 B로 재계산 → 마을이 "접근 가능"에서 "고립 위험"으로 변함 → 경보 초안+근거 생성 → 실제 공식 경보 시각과 비교해 확보시간 표시. 이 30~60초가 본선 승부처 — 3D가 얼마나 예쁜지보다 슬라이더 한 번에 "도로가 끊기니까 대피소가 바뀌는구나"를 심사위원이 직관적으로 이해하는 게 훨씬 중요.

### 9.7 개발 로드맵 (리서치 제안, 참고용 — 실제 일정은 §12 2주 로드맵과 별개로 운영)
- **지금~9월 중순**: 공모전 플랫폼 자원 신청, Module A 최소 baseline, 산청 burn scar×landslide 공간중첩 검증
- **9월 중순~말**: 실제 대피소·도로경로 연결, README 과장/미검증 표현 정리(오늘 상당 부분 완료)
- **10월**: 산청 full backtest 완성 + 외부 전문가·실사용자 테스트(실제 task 부여 방식 — "이 화면만 보고 어느 마을에 먼저 대피명령 초안을 만들겠습니까?" 등)
- **11월 3일까지**: 새 기능 거의 동결, 상세기획서는 문제→기존 gap→사용자→데이터→실제 구현→산청 검증→협력→확장 순서로
- **예선 통과 이후~본선**: 새 AI 넣지 않음, 완성도·확장성·유용성 75점에 집중 — uptime, 두 번째 지역 실행, 추가 사용자 평가, fallback, 리허설

---

## 10. 커뮤니케이션 스타일 참고

사용자는 한국어로 소통하고, 진행하면서 실제 브라우저에서 검증한 뒤 문제를 보고하는 방식으로 협업했다(코드만 짜고 끝내지 않고, 실행해서 확인하고, 안 되면 원인을 깊게 파고들어 고침). 매 기능 단위로 git commit + push를 바로바로 했고, 커밋 메시지에 "왜"를 상세히 남기는 걸 중요하게 여겼다. 이 패턴을 유지할 것.
