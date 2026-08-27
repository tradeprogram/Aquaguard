# contracts/

문서 `AquaGuard_AI_아키텍처_v2.4.pdf` §5의 모듈별 입출력 예시를 그대로 옮긴 계약 파일. 3개 트랙이 서로의 실제 구현을 몰라도 이 파일만으로 병행 개발한다.

- `module_X.example.json` — `input`(모듈이 받는 값) / `output`(§4.2 공통 봉투 형식: `status/fallback_tier/data/warnings`)
- `module_X.schema.json` — 위 example의 타입 검증용 JSON Schema (draft-07)

## 주의
- **Day 1 이후 이 폴더의 필드를 바꿀 때는 3인 합의 필수** (문서 §4.3). 한쪽에서 조용히 바꾸면 다른 두 트랙이 깨진다.
- 좌표는 전부 `EPSG:5179`(미터). 4326(GeoJSON 표준)으로의 재투영은 Module UI/UI-3D 출력 직전에만 수행 (문서 §4.1).
- `module_o.example.json`의 `input` 필드(`alert_id`/`trigger_location`/`timestamp`/`auto_approve_timeout_min`/`safety_margin_hours`)는 문서 §5에 명시적 예시가 없어 §5 본문 서술(상태머신·시간예산 계산·`auto_approve_timeout_min` 언급)을 근거로 트랙③이 추론한 값이다 — Day 1 리뷰 때 3인이 함께 확정할 것.
- Module O의 `POST /approve/{alert_id}` 요청 바디는 `module_o.example.json`의 `approve_endpoint`에 별도로 정리해뒀다 (output data와는 별개 엔드포인트).
