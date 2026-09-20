"""산청군 전체 고립분석 실측 — 캐시 콜드/웜 시간과 결과 요약을 출력한다.
사용: PYTHONPATH=. python scripts/smoke_test_isolation_county.py
"""
import time

import requests
import shapely.geometry as sg
from dotenv import load_dotenv

load_dotenv(".env")
from module_e_routing import isolation as I  # noqa: E402

BBOX = (127.72, 35.19, 128.12, 35.56)  # 산청군 외접 사각형(인접 시군 일부 포함)
shelters = requests.get(
    "https://sansatai.forest.go.kr/mhms_pub/mhms/shelter/shelterList.do",
    params={"searchAddress": "경상남도 산청군"}, timeout=20,
).json()["shelterList"]
S = [(float(x["evctnPlaceXcrd"]), float(x["evctnPlaceYcrd"])) for x in shelters]
mid = (BBOX[0] + BBOX[2]) / 2
hazard = sg.mapping(sg.box(mid - 0.002, BBOX[1], mid + 0.002, BBOX[3]))  # 데모용 세로 띠

for label in ("1차(캐시 없으면 다운로드)", "2차(캐시)"):
    t = time.time()
    r = I.check_isolation(BBOX, S, hazard)
    print(f"{label}: {time.time()-t:.1f}s | 고립 건물 {r['isolated_building_count']} | 구역 {len(r['isolated_areas']['features'])}")
    for w in r["warnings"]:
        print("   -", w)
