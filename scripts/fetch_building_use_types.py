"""
AOI 건물의 주용도(건축물대장 표제부)를 받아 bd_mgt_sn -> 주용도 매핑으로 저장하는
1회성 배치 스크립트.

왜 필요한가 (policies/use_type_vocabulary.json, TRACK2_CONTRACT_AGENDA.md 6번):
아쿠아가드가 쓰는 VWorld LT_C_SPBD(건물통합정보) 레이어에는 용도 속성이 아예 없다.
2026-09-04 실측으로 산청 57,681건·서울 652,026건 전부(709,707건) Module D에서 '미상'으로
분류되는 것을 확인했다. 그래서 Module D의 use_type은 어휘를 고쳐서가 아니라 주용도를
실어오는 소스를 붙여야 살아난다. 그 조인키가 bd_mgt_sn이다.

bd_mgt_sn(건물관리번호, 25자리) 분해 — 2026-09-04 산청 57,681건 전수 검증:
    [0:5]   시군구코드   (시도 앞 2자리가 sido 속성과 57,681/57,681 일치)
    [5:10]  법정동코드
    [10]    대지구분     (1=대지 54,548 / 2=산 3,132)
    [11:15] 번           (전 건 숫자)
    [15:19] 지           (전 건 숫자)
    [19:25] 일련번호

조회 단위를 대지가 아니라 법정동으로 잡은 이유: 대지 단위로 부르면 유니크 대지가
산청 32,426개·서울 555,932개라 일 10,000건 한도로 서울만 56일이 걸린다. 법정동 단위로
페이징하면 산청 177개 동(약 178회)·서울 605개 동(약 1,067회)로 떨어져 하루 한도 안에
들어온다.

준비:
    1. https://www.data.go.kr 에서 "국토교통부_건축물대장정보 서비스" 활용신청
    2. 발급받은 일반 인증키(Decoding)를 .env에 추가:
           BLDRGST_API_KEY=발급키
    3. python scripts/fetch_building_use_types.py

첫 실행 시 확인이 필요한 것(키가 없어 작성 시점에 실호출 검증을 못 했다):
    - 응답의 관리건축물대장PK 필드명이 mgmBldrgstPk가 맞는지, 그 값이 bd_mgt_sn과
      같은 25자리 체계인지. 다르면 JOIN_KEY_FIELD를 고치면 된다.
    - 주용도 필드명이 mainPurpsCdNm이 맞는지. 다르면 USE_TYPE_FIELD를 고친다.
  --probe 옵션으로 법정동 하나만 불러 원본 응답 키를 그대로 찍어볼 수 있다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
PRECOMPUTED_DIR = REPO_ROOT / "data" / "precomputed"
OUTPUT_PATH = PRECOMPUTED_DIR / "building_use_types.json"
CACHE_PATH = PRECOMPUTED_DIR / "_bldrgst_cache.json"

API_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
PAGE_SIZE = 1000
SLEEP_SEC = 0.2  # 연속 호출 간격 — 공공데이터포털 트래픽 초과 방지

# 첫 실행에서 --probe로 확인하고 필요하면 바꿀 것 (모듈 상단 docstring 참조)
JOIN_KEY_FIELD = "mgmBldrgstPk"
USE_TYPE_FIELD = "mainPurpsCdNm"

AOI_FILES = {
    "sancheong": PRECOMPUTED_DIR / "sancheong_buildings.geojson",
    "seoul": PRECOMPUTED_DIR / "seoul_buildings.geojson",
}


def split_bd_mgt_sn(sn: str) -> tuple[str, str, str, str, str] | None:
    """건물관리번호를 (시군구, 법정동, 대지구분, 번, 지)로 분해. 형식이 아니면 None."""
    if not isinstance(sn, str) or len(sn) != 25 or not sn.isdigit():
        return None
    return sn[0:5], sn[5:10], sn[10], sn[11:15], sn[15:19]


def collect_dong_keys(aoi_names: list[str]) -> dict[tuple[str, str], int]:
    """AOI 건물 파일에서 조회해야 할 (시군구코드, 법정동코드)와 건물 수를 모은다."""
    counts: Counter[tuple[str, str]] = Counter()
    for name in aoi_names:
        path = AOI_FILES[name]
        if not path.exists():
            print(f"  [건너뜀] {path} 없음 — scripts/fetch_aoi_data.py로 먼저 생성", file=sys.stderr)
            continue
        with open(path, encoding="utf-8") as f:
            features = json.load(f)["features"]
        skipped = 0
        for feat in features:
            parts = split_bd_mgt_sn((feat.get("properties") or {}).get("bd_mgt_sn", ""))
            if parts is None:
                skipped += 1
                continue
            counts[(parts[0], parts[1])] += 1
        print(f"  {name}: 건물 {len(features):,}건 → 법정동 {len({k for k in counts}):,}개"
              + (f" (형식 불일치 {skipped:,}건 제외)" if skipped else ""))
    return dict(counts)


def fetch_dong(service_key: str, sigungu_cd: str, bjdong_cd: str) -> list[dict]:
    """법정동 하나의 표제부를 전부(페이징) 받아 원본 item 목록으로 돌려준다."""
    items: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            API_URL,
            params={
                "serviceKey": service_key,
                "sigunguCd": sigungu_cd,
                "bjdongCd": bjdong_cd,
                "numOfRows": PAGE_SIZE,
                "pageNo": page,
                "_type": "json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        try:
            body = resp.json()["response"]["body"]
        except (ValueError, KeyError) as exc:
            # 인증키 오류·트래픽 초과는 JSON이 아니라 XML/HTML로 오는 경우가 있다.
            raise RuntimeError(f"응답 파싱 실패({type(exc).__name__}): {resp.text[:300]}") from exc

        raw_items = (body.get("items") or {}).get("item") or []
        if isinstance(raw_items, dict):  # 결과가 1건이면 dict로 온다
            raw_items = [raw_items]
        items.extend(raw_items)

        total = int(body.get("totalCount", 0))
        if page * PAGE_SIZE >= total or not raw_items:
            return items
        page += 1
        time.sleep(SLEEP_SEC)


def probe(service_key: str, aoi_names: list[str]) -> None:
    """법정동 하나만 불러 응답 필드명을 그대로 보여준다 — 첫 실행 시 필드명 확인용."""
    keys = collect_dong_keys(aoi_names)
    if not keys:
        print("조회할 법정동이 없다.", file=sys.stderr)
        return
    (sgg, bjd) = next(iter(keys))
    print(f"\n[probe] 시군구={sgg} 법정동={bjd} 1페이지만 조회한다.")
    items = fetch_dong(service_key, sgg, bjd)
    if not items:
        print("  결과 0건 — 다른 법정동으로 다시 시도해볼 것.")
        return
    print(f"  {len(items)}건 수신. 첫 항목의 필드:")
    for k, v in sorted(items[0].items()):
        mark = ""
        if k == JOIN_KEY_FIELD:
            mark = "   <= JOIN_KEY_FIELD"
        elif k == USE_TYPE_FIELD:
            mark = "   <= USE_TYPE_FIELD"
        print(f"    {k:22s} = {str(v)[:40]!r}{mark}")
    missing = [f for f in (JOIN_KEY_FIELD, USE_TYPE_FIELD) if f not in items[0]]
    if missing:
        print(f"\n  주의: {missing} 가 응답에 없다. 위 목록에서 대응 필드를 찾아 "
              f"스크립트 상단 상수를 고칠 것.")
    else:
        pk = str(items[0][JOIN_KEY_FIELD])
        print(f"\n  조인키 샘플: {pk!r} (길이 {len(pk)}) — bd_mgt_sn과 같은 25자리여야 조인된다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AOI 건물 주용도 수집 (건축물대장 표제부)")
    parser.add_argument("--aoi", nargs="*", default=list(AOI_FILES), choices=list(AOI_FILES),
                        help="대상 AOI (기본: 전부)")
    parser.add_argument("--probe", action="store_true", help="법정동 1개만 조회해 응답 필드명 확인")
    args = parser.parse_args()

    service_key = os.environ.get("BLDRGST_API_KEY")
    if not service_key:
        print("BLDRGST_API_KEY가 .env에 없다. 모듈 상단 '준비' 항목 참조.", file=sys.stderr)
        sys.exit(1)

    print("AOI 건물 파일에서 법정동 목록 수집:")
    if args.probe:
        probe(service_key, args.aoi)
        return

    dong_keys = collect_dong_keys(args.aoi)
    if not dong_keys:
        sys.exit(1)
    print(f"\n조회 대상 법정동 {len(dong_keys):,}개 (건물 {sum(dong_keys.values()):,}건 커버)")

    # 중단돼도 이어서 받을 수 있게 법정동 단위로 캐시한다.
    cache: dict[str, list[dict]] = {}
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"캐시에서 법정동 {len(cache):,}개 복원 — 나머지만 받는다.")

    todo = [k for k in dong_keys if f"{k[0]}{k[1]}" not in cache]
    for i, (sgg, bjd) in enumerate(sorted(todo), 1):
        try:
            cache[f"{sgg}{bjd}"] = fetch_dong(service_key, sgg, bjd)
        except Exception as exc:  # noqa: BLE001 - 한 동 실패로 전체를 잃지 않는다
            print(f"  [{i}/{len(todo)}] {sgg}{bjd} 실패: {exc}", file=sys.stderr)
            cache[f"{sgg}{bjd}"] = []
        if i % 25 == 0 or i == len(todo):
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
            print(f"  [{i}/{len(todo)}] 진행 중 (캐시 저장)")
        time.sleep(SLEEP_SEC)

    # bd_mgt_sn -> 주용도 매핑으로 접는다.
    mapping: dict[str, str] = {}
    missing_field = 0
    for items in cache.values():
        for item in items:
            pk = str(item.get(JOIN_KEY_FIELD, "")).strip()
            use = str(item.get(USE_TYPE_FIELD, "")).strip()
            if not pk or not use:
                missing_field += 1
                continue
            mapping[pk] = use

    PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=0, sort_keys=True)

    print(f"\n저장: {OUTPUT_PATH} ({len(mapping):,}건)")
    if missing_field:
        print(f"  조인키/주용도가 비어 건너뛴 항목 {missing_field:,}건 "
              f"— 필드명이 맞는지 --probe로 확인할 것.")

    dist = Counter(mapping.values())
    print("\n실제 주용도 값 분포 상위 20 (policies/use_type_vocabulary.json의 "
          "source_value_mapping을 이 값 기준으로 교체할 것):")
    for value, count in dist.most_common(20):
        print(f"   {count:8,d}  {value}")


if __name__ == "__main__":
    main()
