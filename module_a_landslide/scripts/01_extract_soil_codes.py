"""
01_extract_soil_codes.py  (AquaGuard 트랙① / Module A)

농진청 정밀토양도(1:25,000) 전국 shapefile 레이어에서 FoS(무한사면 안전율)
계산에 필요한 속성별 코드→분류 사전을 추출해 UTF-8 CSV로 저장한다.

- 입력: G:/연구/산사태/데이터/토양도/{layer}/{LAYER}_이름.shp  (CRS=EPSG:5174, .prj 없음)
- 출력: outputs/soil_code_dictionary.csv
- 인코딩: dbf 한글은 CP949 → pyogrio encoding='cp949'로 읽어 UTF-8로 저장
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import pandas as pd
import pyogrio

SOIL_ROOT = Path(r"G:/연구/산사태/데이터/토양도")
OUT = Path(r"G:/연구/공모전/아쿠아가드/outputs")
OUT.mkdir(parents=True, exist_ok=True)

# FoS에 직접 쓰이는 핵심 레이어 + 보조 레이어
LAYERS = {
    "AD_유효토심": "ad",       # z (토심)
    "DC_배수등급": "dc",       # m (젖음/지하수위) 기저값
    "SL_경사":     "sl",       # beta (경사)
    "TT_표토토성": "tt",       # c', phi', gamma (표토)
    "ST_심토토성": "st",       # c', phi', gamma (심토=파괴면)
    "SG_심토자갈함량": "sg",   # 강도 보정
    "TG_표토자갈함량": "tg",
    "SS_토양구조": "ss",
    "PM_모재":     "pm",       # 모재(기반암)
    "LF_지형":     "lf",
    "SD_퇴적양식": "sd",
}

rows = []
for layer_name, folder in LAYERS.items():
    shp = SOIL_ROOT / folder / f"{layer_name}.shp"
    if not shp.exists():
        print(f"[skip] {shp} not found"); continue
    df = pyogrio.read_dataframe(shp, read_geometry=False, encoding="cp949")
    code_cols = [c for c in df.columns if c.upper().startswith("CODE")]
    codecol = code_cols[0] if code_cols else None
    if codecol is None:
        print(f"[warn] {layer_name}: no CODE column ({list(df.columns)})"); continue
    label_cols = [c for c in df.columns
                  if c not in ("AREA", "PERIMETER") and not c.upper().startswith("CODE")]
    lc = label_cols[0] if label_cols else None
    if lc is None:
        print(f"[warn] {layer_name}: no label column ({list(df.columns)})"); continue
    grp = (df.groupby([codecol, lc]).size().reset_index(name="polygon_count")
             .sort_values(codecol))
    for _, r in grp.iterrows():
        rows.append({
            "layer": layer_name,
            "code": r[codecol],
            "class": r[lc],
            "polygon_count": int(r["polygon_count"]),
        })
    print(f"[ok] {layer_name}: {len(grp)} classes, {len(df):,} polygons")

out = pd.DataFrame(rows)
csv_path = OUT / "soil_code_dictionary.csv"
out.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"\nsaved -> {csv_path}  ({len(out)} rows)")
print(out.to_string(index=False))
