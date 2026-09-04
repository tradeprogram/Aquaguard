# policies/

트랙②(대응로직·데이터통합) 소유 정책 파일. **`contracts/`와는 성격이 다르다** —
`contracts/`는 트랙 간 입출력 계약이라 4인 합의 없이 못 바꾸지만, 여기 있는 값은
트랙② 내부 정책이므로 나정우가 단독으로 바꿀 수 있다. 대신 판정 결과가 바뀌므로
각 모듈의 스냅샷 테스트를 함께 갱신해야 한다.

| 파일 | 쓰는 모듈 | 내용 |
|---|---|---|
| `use_type_vocabulary.json` | **D + G 공유** | 건축물 용도 어휘 7종과 원본 속성값 매핑 |
| `module_d.json` | D | 점 버퍼 반경, min_risk_prob, 속성키 후보, 면적 반올림 |
| `policy.schema.json` | 전부 | 위 두 파일의 구조 검증용 |

## 왜 최상위에 두는가

Module D의 `exposed_buildings[].use_type`이 곧 Module G의 원단위 테이블 키다
(`module_o_orchestrator/orchestrator.py`가 `call_module("g", {**exposure, ...})`로
D의 출력을 그대로 G의 입력에 펼친다). 두 모듈이 같은 어휘를 봐야 하는데 한쪽
패키지 안에 두면 다른 쪽이 그 패키지에 의존하게 된다 — ARCHITECTURE §4.2의
"각 모듈 폴더는 다른 모듈 없이 독립 테스트 가능" 요건과 어긋난다. 그래서 어느
모듈에도 속하지 않는 자리에 뒀다.

ARCHITECTURE §8 디렉토리 구조에는 이 디렉토리가 없다. 계약을 바꾸는 변경은
아니지만 트리에 없는 디렉토리를 늘린 것이므로 Day 1 계약 회의에 보고한다
(`TRACK2_CONTRACT_AGENDA.md` 참조).

Module C의 임계값 룰셋은 `module_c_urban_rule/rulesets/`에 남아 있다 — C는 다른
모듈과 공유할 정책이 없어서다. 통일이 필요해지면 그때 옮긴다.
