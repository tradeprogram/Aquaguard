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

2026-09-04 실호출로 확정된 사항 (--probe 산청 48850/40025, 48860/37023):

    조인은 필지 단위다. 동(棟) 단위가 아니다.
      mgmBldrgstPk는 조인키로 못 쓴다 - JSON 숫자로 오고 길이가 10/14/22자리로
      제각각이라 25자리 bd_mgt_sn과 체계가 다르다. 대신 응답의
      sigunguCd+bjdongCd+platGbCd+bun+ji로 bd_mgt_sn 앞 19자리(필지 식별부)를
      재구성해 조인한다. 일련번호 [19:25]에 해당하는 필드가 응답에 없어서
      한 필지에 여러 동이 있으면 전부 같은 주용도를 받는다(ASSUMPTION).
      한 필지에 표제부가 여러 건이면 주건축물(mainAtchGbCd=="0") 우선, 동률이면
      연면적(totArea) 최대로 대표 1건을 고른다(ASSUMPTION).

    platGbCd -> bd_mgt_sn[10] 대지구분은 0->1(대지), 1->2(산).
      48860/37023(산 필지 건물 197건)로 검증했다. platGbCd=1 레코드의 platPlc가
      실제로 "산 81번지" 형태였고, 필지 일치도 0->1,1->2가 436개로 대안(1->1은
      435개, 0->2,1->1은 1개)보다 낫다. 대지구분을 아예 무시한 18자리 조인의
      상한이 437개라 이 치환으로 잃는 게 사실상 없다.

    주용도 필드는 mainPurpsCdNm이 맞다.

    numOfRows는 서버가 100건으로 캡한다.
      1000을 요청해도 100건만 온다. 종료 판정을 요청한 PAGE_SIZE로 하면 1페이지만
      받고 조용히 끝나므로(totalCount=695인 동에서 100건만 받고 종료 - 86% 무경고
      누락) 반드시 실제 누적 수신량으로 판정한다.

    정상 키로도 간헐적으로 빈 응답이 온다. 페이지 단위 재시도가 필요하다.

--probe [--dong 48850/40025] 로 법정동 하나를 전부 받아 필드명·필지키 재구성·
건물 커버리지를 확인할 수 있다.

산출물:
    data/precomputed/building_use_types.json       필지키(19자리) -> 주용도
    data/precomputed/building_use_types.meta.json  조인 방식·대표 선택 규칙·커버리지
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
# 산출물 옆에 조인 방식·대표 선택 규칙·커버리지를 남긴다. 필지 단위 조인이라는
# 사실이 파일만 보고도 드러나야 Module D 쪽에서 오해 없이 쓴다.
META_PATH = PRECOMPUTED_DIR / "building_use_types.meta.json"

API_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
# 2026-09-04 실측: numOfRows에 1000을 넣어도 서버가 100건으로 캡해서 돌려준다.
# 요청값을 실제 상한과 맞춰두지 않으면 아래 종료 조건이 어긋난다.
PAGE_SIZE = 100
SLEEP_SEC = 0.2  # 연속 호출 간격 — 공공데이터포털 트래픽 초과 방지
PAGE_MAX_RETRIES = 4   # 간헐적 빈 응답 대비 (2026-09-04 실측으로 확인)
RETRY_BACKOFF_SEC = 1.5

# 2026-09-04 --probe 실측으로 확정.
USE_TYPE_FIELD = "mainPurpsCdNm"          # 확인됨: 실제 주용도 문자열이 들어온다

# mgmBldrgstPk는 조인키로 쓸 수 없다 — JSON 숫자로 오고 길이가 10/14/22자리로
# 제각각이라 25자리 bd_mgt_sn과 체계가 다르다. 대신 응답 필드로 bd_mgt_sn의
# 앞 19자리(= 필지 식별부)를 재구성해 조인한다. 일련번호 [19:25]는 응답에 없어
# 동 단위까지는 못 내려가고 필지 단위 조인이 된다.
PARCEL_KEY_FIELDS = ("sigunguCd", "bjdongCd", "platGbCd", "bun", "ji")

# platGbCd(0/1) -> bd_mgt_sn[10] 대지구분(1=대지, 2=산)
PLAT_GB_TO_DAEJI_GUBUN = {"0": "1", "1": "2"}

# 한 필지에 표제부가 여러 건(동별)일 때의 대표 선택 규칙 (ASSUMPTION):
#   ① 주건축물(mainAtchGbCd == "0") 우선, ② 동률이면 연면적(totArea) 최대
MAIN_BUILDING_CODE = "0"

AOI_FILES = {
    "sancheong": PRECOMPUTED_DIR / "sancheong_buildings.geojson",
    "seoul": PRECOMPUTED_DIR / "seoul_buildings.geojson",
}


def split_bd_mgt_sn(sn: str) -> tuple[str, str, str, str, str] | None:
    """건물관리번호를 (시군구, 법정동, 대지구분, 번, 지)로 분해. 형식이 아니면 None."""
    if not isinstance(sn, str) or len(sn) != 25 or not sn.isdigit():
        return None
    return sn[0:5], sn[5:10], sn[10], sn[11:15], sn[15:19]


def parcel_key(item: dict) -> str | None:
    """표제부 응답 1건에서 bd_mgt_sn 앞 19자리(필지 식별부)를 재구성한다.

    bd_mgt_sn[0:19] = 시군구(5) + 법정동(5) + 대지구분(1) + 번(4) + 지(4)
    일련번호 [19:25]는 응답에 없으므로 여기까지가 조인 가능한 최대 정밀도다.
    """
    sigungu = str(item.get("sigunguCd") or "").strip()
    bjdong = str(item.get("bjdongCd") or "").strip()
    plat_gb = PLAT_GB_TO_DAEJI_GUBUN.get(str(item.get("platGbCd") or "").strip())
    bun = str(item.get("bun") or "").strip().zfill(4)
    ji = str(item.get("ji") or "").strip().zfill(4)
    if len(sigungu) != 5 or len(bjdong) != 5 or plat_gb is None or len(bun) != 4 or len(ji) != 4:
        return None
    return f"{sigungu}{bjdong}{plat_gb}{bun}{ji}"


def _total_area(item: dict) -> float:
    try:
        return float(item.get("totArea") or 0)
    except (TypeError, ValueError):
        return 0.0


def pick_representative(items: list[dict]) -> dict:
    """한 필지에 표제부가 여러 건일 때의 대표 1건 (ASSUMPTION, 모듈 상단 docstring 참조).

    ① 주건축물(mainAtchGbCd == "0") 우선 ② 동률이면 연면적 최대.
    """
    return max(
        items,
        key=lambda i: (
            str(i.get("mainAtchGbCd") or "").strip() == MAIN_BUILDING_CODE,
            _total_area(i),
        ),
    )


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
        # 2026-09-04 실측: 정상 키로도 간헐적으로 본문이 빈 응답(HTTP 200, 길이 0)이
        # 돌아온다. 재시도 없이 예외를 올리면 호출측이 그 법정동을 통째로 버리므로
        # (177개 동 x 약 10페이지면 거의 확실히 발생) 페이지 단위로 물러섰다 다시 친다.
        body = None
        last_error = ""
        for attempt in range(PAGE_MAX_RETRIES):
            try:
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
                body = resp.json()["response"]["body"]
                break
            except Exception as exc:  # noqa: BLE001 - 네트워크·파싱 오류를 같이 물러선다
                # 인증키 오류·트래픽 초과는 JSON이 아니라 XML/HTML로 오는 경우가 있다.
                text = locals().get("resp").text[:200] if "resp" in locals() and resp is not None else ""
                last_error = f"{type(exc).__name__}: {exc} | 본문 {text!r}"
                time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))
        if body is None:
            raise RuntimeError(
                f"{sigungu_cd}{bjdong_cd} page={page} 응답 파싱 실패"
                f"({PAGE_MAX_RETRIES}회 재시도 후): {last_error}"
            )

        raw_items = (body.get("items") or {}).get("item") or []
        if isinstance(raw_items, dict):  # 결과가 1건이면 dict로 온다
            raw_items = [raw_items]
        items.extend(raw_items)

        total = int(body.get("totalCount", 0))
        # 종료 판정은 반드시 "실제로 받은 누적 건수"로 한다. 요청한 PAGE_SIZE로
        # 판정하면 서버가 100건으로 캡할 때 1페이지만 받고 조용히 끝난다
        # (2026-09-04 실측: totalCount=695인 법정동에서 100건만 받고 종료 — 86% 누락).
        if not raw_items or len(items) >= total:
            if total and len(items) < total:
                print(f"    [WARN] {sigungu_cd}{bjdong_cd}: {len(items)}/{total}건만 수신",
                      file=sys.stderr)
            return items
        page += 1
        time.sleep(SLEEP_SEC)


def probe(service_key: str, aoi_names: list[str], dong: str | None = None) -> None:
    """법정동 하나를 전부 받아 필드명과 필지키 조인 가능성을 확인한다.

    --dong 48850/40025 처럼 특정 법정동을 지정할 수 있다(산 필지가 있는 동으로
    platGbCd 0->1 치환이 맞는지 검증할 때 쓴다).

    콘솔이 cp949인 환경이 있어 출력에 em dash 같은 비-cp949 문자를 쓰지 않는다.
    """
    counts = collect_dong_keys(aoi_names)
    if dong:
        sgg, bjd = dong.split("/")
    elif counts:
        sgg, bjd = next(iter(counts))
    else:
        print("조회할 법정동이 없다.", file=sys.stderr)
        return

    print()
    print(f"[probe] 시군구={sgg} 법정동={bjd} 전부 조회한다.")
    items = fetch_dong(service_key, sgg, bjd)
    if not items:
        print("  결과 0건. 다른 법정동으로 다시 시도해볼 것.")
        return

    print(f"  {len(items)}건 수신. 첫 항목의 필드:")
    for k, v in sorted(items[0].items()):
        mark = "   <= USE_TYPE_FIELD" if k == USE_TYPE_FIELD else ""
        print(f"    {k:22s} = {str(v)[:40]!r}{mark}")

    if USE_TYPE_FIELD not in items[0]:
        print()
        print(f"  주의: {USE_TYPE_FIELD} 가 응답에 없다. 위 목록에서 대응 필드를 찾아 "
              f"스크립트 상단 상수를 고칠 것.")

    plat_gb = Counter(str(i.get("platGbCd")) for i in items)
    print()
    print(f"  platGbCd 분포: {dict(plat_gb)}")
    unknown_gb = set(plat_gb) - set(PLAT_GB_TO_DAEJI_GUBUN)
    if unknown_gb:
        print(f"  주의: PLAT_GB_TO_DAEJI_GUBUN에 없는 platGbCd {sorted(unknown_gb)} "
              f"가 등장한다. 치환표를 보강할 것.")

    keys = [parcel_key(i) for i in items]
    good = [k for k in keys if k]
    print(f"  필지키 재구성: {len(good)}/{len(items)}건 성공, 유니크 {len(set(good))}개")
    if good:
        print(f"  샘플: {good[0]!r} (길이 {len(good[0])}) - bd_mgt_sn 앞 19자리와 같아야 조인된다.")

    # 실제 건물 파일과 대조해 커버리지를 바로 보여준다.
    bld = _load_building_parcels(aoi_names, sgg, bjd)
    if not bld:
        print("  건물 파일에서 이 법정동을 못 찾았다. 커버리지 확인 생략.")
        return
    matched = {k for k in good if k in bld}
    n_buildings = sum(bld.values())
    n_matched_buildings = sum(cnt for k, cnt in bld.items() if k in matched)
    print(f"  건물 파일 필지 {len(bld)}개 / 건물 {n_buildings}건")
    print(f"  필지 일치 {len(matched)}개, 그 필지에 속한 건물 {n_matched_buildings}건 "
          f"({n_matched_buildings / n_buildings * 100:.1f}%)")

    gb_in_buildings = Counter(k[10] for k in bld)
    print(f"  건물 bd_mgt_sn 대지구분 분포: {dict(gb_in_buildings)} (1=대지, 2=산)")
    if "2" in gb_in_buildings:
        san_matched = sum(1 for k in matched if k[10] == "2")
        print(f"  산 필지 {gb_in_buildings['2']}개 중 일치 {san_matched}개 "
              f"- platGbCd 1 -> 대지구분 2 치환 검증 결과")
    else:
        print("  이 법정동에는 산 필지가 없어 platGbCd 1 -> 2 치환은 검증되지 않았다.")


def _load_building_parcels(aoi_names: list[str], sgg: str, bjd: str) -> dict[str, int]:
    """건물 파일에서 해당 법정동의 필지키(bd_mgt_sn 앞 19자리) -> 건물 수."""
    counts: Counter[str] = Counter()
    for name in aoi_names:
        path = AOI_FILES[name]
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for feat in json.load(f)["features"]:
                sn = (feat.get("properties") or {}).get("bd_mgt_sn", "")
                if isinstance(sn, str) and len(sn) == 25 and sn[:10] == f"{sgg}{bjd}":
                    counts[sn[:19]] += 1
    return dict(counts)


def building_coverage(aoi_names: list[str], mapping: dict[str, str]) -> dict:
    """만들어진 매핑이 실제 건물 몇 건을 덮는지 AOI별로 센다."""
    per_aoi: dict[str, dict] = {}
    total = matched = 0
    for name in aoi_names:
        path = AOI_FILES[name]
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            features = json.load(f)["features"]
        n = hit = 0
        for feat in features:
            sn = (feat.get("properties") or {}).get("bd_mgt_sn", "")
            if not (isinstance(sn, str) and len(sn) == 25):
                continue
            n += 1
            if sn[:19] in mapping:
                hit += 1
        per_aoi[name] = {
            "buildings": n,
            "matched": hit,
            "matched_ratio_pct": round(hit / n * 100, 1) if n else 0.0,
        }
        total += n
        matched += hit
    return {
        "per_aoi": per_aoi,
        "total_buildings": total,
        "matched_buildings": matched,
        "matched_ratio_pct": round(matched / total * 100, 1) if total else 0.0,
    }


def write_meta(aoi_names: list[str], mapping: dict[str, str], multi_record_parcels: int,
               coverage: dict, unusable_key: int, missing_use: int) -> None:
    """산출물 옆 메타 파일 — 이 매핑이 어떤 조인으로 만들어졌는지 남긴다."""
    meta = {
        "generated_by": "scripts/fetch_building_use_types.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "aoi": list(aoi_names),
        "source": {
            "agency": "국토교통부",
            "service": "건축물대장정보 서비스 - 표제부(getBrTitleInfo)",
            "endpoint": API_URL,
            "use_type_field": USE_TYPE_FIELD,
        },
        "join": {
            "granularity": "parcel",
            "key": "bd_mgt_sn[0:19]",
            "key_composition": "시군구(5) + 법정동(5) + 대지구분(1) + 번(4) + 지(4)",
            "reconstructed_from": list(PARCEL_KEY_FIELDS),
            "plat_gb_cd_mapping": PLAT_GB_TO_DAEJI_GUBUN,
            "caveat": (
                "필지 단위 조인이며 동(棟) 단위가 아니다. bd_mgt_sn의 일련번호"
                " [19:25]에 해당하는 필드가 표제부 응답에 없어서, 한 필지에 여러 동이"
                " 있으면 모든 동이 같은 주용도를 받는다 (ASSUMPTION)."
            ),
            "why_not_mgmBldrgstPk": (
                "mgmBldrgstPk는 JSON 숫자로 오고 길이가 10/14/22자리로 제각각이라"
                " 25자리 bd_mgt_sn과 체계가 다르다. 조인키로 쓸 수 없다 (2026-09-04 실측)."
            ),
        },
        "representative_rule": {
            "description": "한 필지에 표제부가 여러 건일 때 대표 1건을 고르는 규칙",
            "steps": ["주건축물(mainAtchGbCd == '0') 우선", "동률이면 연면적(totArea) 최대"],
            "status": "ASSUMPTION",
            "multi_record_parcels": multi_record_parcels,
        },
        "counts": {
            "parcels_with_use_type": len(mapping),
            "parcel_key_rebuild_failed": unusable_key,
            "records_without_use_type": missing_use,
        },
        "coverage": coverage,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="AOI 건물 주용도 수집 (건축물대장 표제부)")
    parser.add_argument("--aoi", nargs="*", default=list(AOI_FILES), choices=list(AOI_FILES),
                        help="대상 AOI (기본: 전부)")
    parser.add_argument("--probe", action="store_true",
                        help="법정동 1개를 전부 조회해 응답 필드명·필지키 조인 가능성 확인")
    parser.add_argument("--dong", default=None, metavar="시군구/법정동",
                        help="--probe 대상 법정동 지정 (예: 48850/40025). 산 필지가 있는 동으로 "
                             "platGbCd 치환을 검증할 때 쓴다")
    args = parser.parse_args()

    service_key = os.environ.get("BLDRGST_API_KEY")
    if not service_key:
        print("BLDRGST_API_KEY가 .env에 없다. 모듈 상단 '준비' 항목 참조.", file=sys.stderr)
        sys.exit(1)

    print("AOI 건물 파일에서 법정동 목록 수집:")
    if args.probe:
        probe(service_key, args.aoi, args.dong)
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

    # 필지키(bd_mgt_sn 앞 19자리) -> 표제부 목록으로 모은 뒤 대표 1건을 고른다.
    by_parcel: dict[str, list[dict]] = {}
    unusable_key = 0
    missing_use = 0
    for items in cache.values():
        for item in items:
            key = parcel_key(item)
            if key is None:
                unusable_key += 1
                continue
            if not str(item.get(USE_TYPE_FIELD, "")).strip():
                missing_use += 1
                continue
            by_parcel.setdefault(key, []).append(item)

    mapping = {
        key: str(pick_representative(group)[USE_TYPE_FIELD]).strip()
        for key, group in by_parcel.items()
    }
    multi_record_parcels = sum(1 for group in by_parcel.values() if len(group) > 1)

    PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=0, sort_keys=True)

    coverage = building_coverage(args.aoi, mapping)
    write_meta(args.aoi, mapping, multi_record_parcels, coverage, unusable_key, missing_use)

    print()
    print(f"저장: {OUTPUT_PATH} (필지 {len(mapping):,}개)")
    print(f"  메타: {META_PATH}")
    if unusable_key:
        print(f"  필지키 재구성 실패 {unusable_key:,}건 (시군구/법정동/대지구분/번/지 중 결측)")
    if missing_use:
        print(f"  주용도가 비어 건너뛴 항목 {missing_use:,}건")
    print(f"  표제부가 2건 이상인 필지 {multi_record_parcels:,}개 "
          f"(주건축물 우선, 동률 시 연면적 최대로 대표 선택)")
    print()
    print(f"건물 커버리지: {coverage['matched_buildings']:,}/{coverage['total_buildings']:,} "
          f"({coverage['matched_ratio_pct']}%). 나머지는 Module D에서 '미상'으로 남는다.")

    dist = Counter(mapping.values())
    print("\n실제 주용도 값 분포 상위 20 (policies/use_type_vocabulary.json의 "
          "source_value_mapping을 이 값 기준으로 교체할 것):")
    for value, count in dist.most_common(20):
        print(f"   {count:8,d}  {value}")


if __name__ == "__main__":
    main()
