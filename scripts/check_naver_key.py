"""네이버 Directions 키가 실제로 동작하는지 확인한다. **키 값은 출력하지 않는다.**

    python scripts/check_naver_key.py

실패하면 사유를 그대로 보여준다 — 키 미설정인지, 인증 거부인지, 좌표가 도로에서
너무 먼지가 갈린다. 이 구분이 없으면 "몇 분째 근사로 뜬다"를 진단할 수가 없다.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from module_e_routing import _naver_driving_route  # noqa: E402

# 산청 데모: 트리거 지점 → 대피소 S001 (가계마을회관2)
ORIGIN = (128.0559, 35.3505)
DEST = (128.08145, 35.36157)


def main() -> int:
    for name in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
        value = os.environ.get(name)
        print(f"{name:22} {'설정됨(' + str(len(value)) + '자)' if value else '없음'}")
    if not (os.environ.get("NAVER_CLIENT_ID") and os.environ.get("NAVER_CLIENT_SECRET")):
        print("\n.env 에 두 값을 넣고 다시 실행하십시오. 채팅에 붙여넣지 마십시오.")
        return 1

    route, reason = _naver_driving_route(ORIGIN, DEST)
    if route is None:
        print(f"\n실패: {reason}")
        print("  · '미설정'      -> .env 값 확인")
        print("  · 인증/권한 오류 -> 네이버클라우드 콘솔에서 Maps > Directions 5 이용신청 여부 확인")
        print("  · 좌표 관련 오류 -> 출발/도착이 도로에서 너무 먼 경우")
        return 1

    print(f"\n성공: {len(route['path_lonlat'])}점, {route['duration_min']:.1f}분")
    print("이제 python scripts/build_demo_snapshot.py 로 저장본을 다시 구우십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
