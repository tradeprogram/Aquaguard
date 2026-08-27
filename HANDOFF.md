# 인수인계 — Codex용 (트랙③ 오케스트레이션·UI·3D)

이 문서는 Claude Code 세션이 지금까지 한 작업을 Codex가 컨텍스트 없이 이어받을 수 있도록 정리한 것이다. **먼저 [README.md](README.md)와 [ARCHITECTURE.md](ARCHITECTURE.md)를 읽어라** — 프로젝트 배경(산청 산사태, 골든타임 격차)과 §4~5 통합 규약은 거기 있고 여기서 반복하지 않는다. 이 문서는 "지금까지 뭘 만들었고, 왜 그렇게 만들었고, 다음에 뭘 해야 하는지"에 집중한다.

담당자: 하수범 — 트랙③(오케스트레이션·UI·3D), 소유 모듈: Module O, UI, UI-3D. 트랙①(예측모델, 김민석)·트랙②(대응로직, 나정우)는 **아직 아무 코드도 없다** — 이 저장소는 지금 100% 트랙③ 산출물이다.

---

## 0. 저장소 정보

- GitHub: https://github.com/tradeprogram/Aquaguard (owner: `tradeprogram`)
- 로컬 경로(이 세션 기준): `C:\aquaguard`
- 브랜치: `main` 하나. 지금까지 15개 커밋, 전부 push 완료 (최신 커밋 `564146d`).
- 커밋 작성자: `tradeprogram <chanvab1@gmail.com>` (git config, 로컬 repo 한정)
- `git log --oneline`으로 전체 히스토리 확인 가능 — 각 커밋 메시지에 "왜"가 상세히 적혀 있어서 되짚어보기 좋다.

---

## 1. 지금까지 한 일 (요약)

### 1.1 계약(contracts/) — Day 1 산출물
`contracts/module_{a,b,c,d,e,g,h,o}.{example.json,schema.json}` — 문서 §5의 모듈별 입출력 예시를 그대로 옮긴 것. **다른 두 트랙이 아직 안 왔으므로 이 계약은 실제로 검증된 적이 없다** — 트랙①②가 실제 모듈을 만들면 이 계약과 어긋나는 부분이 나올 수 있음을 감안할 것. `Module O`의 `input` 스키마(`alert_id`/`trigger_location`/`timestamp`/`auto_approve_timeout_min`/`safety_margin_hours`)는 문서에 명시적 예시가 없어 트랙③이 추론해 넣은 값이라고 `contracts/README.md`에 명시해뒀다.

### 1.2 Module O 오케스트레이터 (`module_o_orchestrator/`)
- `orchestrator.py`: `run(input) -> envelope`. A/B 호출 → 임계치(`landslide_prob≥0.7` 또는 `flood_prob≥0.7`) 초과 시 D/E/G 순차 호출 → `precursor_flag`면 H 호출 → `golden_time_saved_min` 계산 → `AlertStore`에 등록.
- `modules_client.py`: `AQUAGUARD_MOCK_MODE`(기본 `1`)로 목업/실제 모듈 호출을 스위칭. `MODULE_PACKAGES` 딕셔너리에 트랙①②의 실제 패키지명이 매핑돼 있음 — **트랙①②가 코드를 넣으면 이 파일 수정 없이 `AQUAGUARD_MOCK_MODE=0`만으로 실제 연동됨.**
- `store.py`: 인메모리 `AlertStore`. 원클릭 승인 상태머신(`대기`/`승인`/`거부`/`자동승인(timeout)`), 오탐(`오탐판정`)이면 자동승인 안 함.
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

### 1.4 Next.js 대시보드 (`ui/`)
Next.js 16(App Router) + TypeScript + Tailwind v4. 페이지 4개:
- `/` — 메인 대시보드: "산청 시나리오 실행" 버튼, 골든타임 카운터, 위험/대피소/피해비용 패널
- `/approve` — 원클릭 승인 화면, 실시간 타임아웃 카운트다운
- `/whatif` — What-if 강수 슬라이더 (지금은 목업이라 값 고정 — 트랙①이 실제 Module A/B 붙이면 바로 반영됨)
- `/map3d` — **3D 지도** (아래 1.5 참조, 가장 최근에 많이 작업한 부분)

실행: `cd ui && npm install && npm run dev` → http://localhost:3000
빌드 검증: `npm run build && npm run lint` (매 변경마다 이걸로 검증해왔음, 계속 그렇게 할 것)

### 1.5 3D 지도 (`ui/src/app/map3d/page.tsx`) — 가장 공들인 부분
스택: MapLibre GL JS `5.24.0`(⚠️ 버전 중요, 아래 §3 참조) + deck.gl `9.3` + `@turf/buffer`.

구성 요소:
- **지형**: `api_server.py`의 `/terrain-tiles` 프록시를 통해 AWS 공개 지형 데이터(terrarium 인코딩) → `map.setTerrain()`
- **위성영상**: Esri World Imagery (무료, 키 불필요) + Esri 지명 레이블 레이어
- **건물**: OpenFreeMap 무료 벡터타일(OSM, OpenMapTiles 스키마) → `render_height`/`render_min_height`로 실제 높이 압출(`fill-extrusion`)
- **도로망**: 같은 벡터타일의 `transportation` 소스레이어 → 도로 등급별 폭/색 스타일링, 터널은 점선
- **교량**: `brunnel=='bridge'`인 도로를 `querySourceFeatures`로 실시간 조회 → `@turf/buffer`로 폭만큼 버퍼링 → `fill-extrusion`으로 지면에서 3~11m 띄운 "진짜 뜬" 데크 (단순 라인 색칠이 아님)
- **행정경계 3계층**: 사용자가 준 `BND_ADM_DONG_PG`(읍면동 레벨) 원본을 코드 접두어로 dissolve해서 시군구/시도 경계까지 만듦(아래 §2 데이터 파이프라인 참조). 뷰포트 bbox로 실시간 갱신, 데모 AOI(생비량면)만 노란색.
- **검색창**: 시/도/군/구/읍/면/동 이름 검색 → 결과 클릭 시 `fitBounds`로 이동
- **골든타임 시간슬라이더**: `timeline_actual` vs `timeline_agent` 이벤트를 스크럽하면서, 에이전트 탐지/발송 시점을 지나야 위험/대피 레이어가 나타나도록 단계적 노출(관의 실제 대응보다 에이전트가 먼저 안다는 서사를 시각적으로 증명)
- **카메라 조작**: 좌클릭 드래그=이동, 스크롤=줌(화면 중앙 기준 고정), 우클릭/Ctrl+드래그=회전·기울기. `maxPitch:70`.
- 테스트용 빠른 이동 버튼: 산청(AOI)/서울 강남/부산 해운대

**아직 안 한 것 / 다음 목표 (사용자가 명시적으로 요청함, 최우선 후속 작업)**:
> "나중에 여기다 3D로 토사가 어느 정도 쓸려 내려가고 물이 차오르고를 표현할 건데, 도로나 건물 등이 실제 스케일로 튀어나와 있어야 시뮬레이션이 의미 있지 않을까"

→ 건물/도로/교량을 실제 스케일로 세우는 작업(1.5절 내용)은 **이 시뮬레이션을 위한 사전 준비**로 진행한 것. 다음 단계는:
1. Module A(산사태) 출력의 `landslide_prob`/`amplification_factor`를 이용해 **토사 유실 시각화** — 산사태 위험 지점 주변에 토사가 흘러내리는 애니메이션/볼륨을 지형 위에 표현 (아마 `deck.gl`의 `TerrainLayer` 커스텀이나 시간에 따라 지형 메시를 낮추는 방식, 혹은 단순화해서 위험 폴리곤 위에 갈색 텍스처/파티클 오버레이)
2. Module B(하천범람) 출력의 `inundation_extent_5179`를 이용해 **침수 볼륨 시각화** — bathtub 모델(§5 문서가 "정밀 수리모형 아님" 배지 필수라고 명시)로 물 높이를 슬라이더로 조절하면서 어느 건물/도로/교량이 잠기는지 표시. 지금 만들어둔 `fill-extrusion` 건물/교량이 있어서 "수위가 몇 m일 때 이 건물이 잠긴다"를 시각적으로 보여줄 수 있는 기반이 됨.
3. 현재 Module A/B가 **목업 모드**라 실제 지오메트리(`risk_polygons`, `inundation_extent_5179`)가 비어있음(`contracts/module_a·b.example.json` 참조) — 시뮬레이션을 제대로 보여주려면 (a) 트랙①의 실제 모델이 들어오거나 (b) 데모용 합성 지오메트리를 트랙③이 직접 만들어야 함. §9 데모 시나리오(산청 재연)를 위해서는 후자가 더 현실적일 수 있음 — 상능마을 AOI 안에 그럴듯한 토사/침수 폴리곤을 손으로 만들어 데모에 쓰는 방법을 고려할 것.

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

**환경 관련 주의사항**: 이 세션이 쓰던 내부 "Browser pane" 미리보기 도구는 WebGL을 컴포짓하지 못하는 상태였다(스크린샷 자체가 실패함). 그래서 3D 지도 관련 버그의 상당수는 **사용자의 실제 브라우저 스크린샷**을 보고서야 진단할 수 있었다. Codex도 자체 미리보기 환경이 WebGL을 제대로 못 띄울 수 있다는 걸 염두에 두고, 필요하면 사용자에게 스크린샷을 요청할 것.

---

## 4. 실행 방법 (처음부터)

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

---

## 5. 다음으로 무엇을 할지 (우선순위 제안)

1. **(최우선, 사용자가 명시적으로 요청)** 토사 유실 + 침수 시뮬레이션 — §1.5 "아직 안 한 것" 참조.
2. 트랙①②가 아직 안 왔으므로, 계속 목업 모드로 진행하되 `contracts/`가 실제로 맞는지 검증할 방법이 없다는 리스크를 사용자에게 상기시킬 것.
3. §9 데모 시나리오(산청 타임라인 재연)를 위한 실제 리허설 — 지금은 각 기능이 개별적으로는 동작하지만, 처음부터 끝까지 이어지는 데모 스토리로 리허설된 적은 없음.
4. `/whatif` 페이지의 강수 슬라이더는 아직 목업이라 값이 안 바뀜 — 실제 Module A/B 붙거나 데모용 합성 응답을 만들면 살아남.
5. Module H(시민 신고 역검증) 트리거 UI가 아직 없음 — 지금은 `precursor_flag`가 목업이라 항상 `false`라 UI에서 확인 불가.

---

## 6. 커뮤니케이션 스타일 참고

사용자는 한국어로 소통하고, 진행하면서 실제 브라우저에서 검증한 뒤 문제를 보고하는 방식으로 협업했다(코드만 짜고 끝내지 않고, 실행해서 확인하고, 안 되면 원인을 깊게 파고들어 고침). 매 기능 단위로 git commit + push를 바로바로 했고, 커밋 메시지에 "왜"를 상세히 남기는 걸 중요하게 여겼다. 이 패턴을 유지할 것.
