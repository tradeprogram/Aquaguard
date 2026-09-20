"""
28b_rasterize_from_npz.py  (28의 maxdepth.npz → 침수 래스터 + meta)
scripts/28이 evolve까지 완료 후 저장한 maxdepth.npz를 100m 래스터로 변환(cKDTree nearest).
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd, rasterio
from scipy.spatial import cKDTree

ROOT=Path(r"G:/연구/공모전/아쿠아가드"); HY=ROOT/"data"/"hydro"; MD=ROOT/"models"/"anuga_reach"; OUTP=ROOT/"outputs"
SWW=Path(r"C:/Users/user/AppData/Local/Temp/claude/G----------------/4ca28ed5-e0c3-4be0-987f-f1bd326760dd/scratchpad/anuga_sww")
X0,Y0,X1,Y1=1028000,1703000,1042000,1723000; RES=100
MD.mkdir(parents=True,exist_ok=True)

def main():
    d=np.load(SWW/"maxdepth.npz"); cc=d["cc"]; maxdepth=d["maxdepth"]
    gx=np.arange(X0+RES/2,X1,RES); gy=np.arange(Y0+RES/2,Y1,RES)
    GX,GY=np.meshgrid(gx,gy)
    tree=cKDTree(cc); dist,ii=tree.query(np.column_stack([GX.ravel(),GY.ravel()]),k=1)
    md=maxdepth[ii]; md[dist>RES*1.5]=0.0
    md=md.reshape(GX.shape); md=np.flipud(md)
    tr=rasterio.transform.from_origin(X0,Y1,RES,RES)
    prof=dict(driver="GTiff",height=md.shape[0],width=md.shape[1],count=1,dtype="float32",
              crs="EPSG:5179",transform=tr,nodata=0,compress="deflate")
    with rasterio.open(MD/"anuga_maxdepth_100m.tif","w",**prof) as ds: ds.write(md.astype("float32"),1)

    # 경호교 WSE 검증(시계열)
    sim=pd.read_csv(OUTP/"anuga_reach_timeseries.csv"); obs=pd.read_csv(HY/"reach_valid_경호교.csv")
    m=pd.merge(sim[["t_sec","WSE_경호교"]],obs[["t_sec","wse"]],on="t_sec",how="inner")
    rmse=float(np.sqrt(((m["WSE_경호교"]-m["wse"])**2).mean())) if len(m) else None
    meta={"engine":"ANUGA (SPEC 승인 대체; SFINCS 바이너리 로그인배포로 미확보)",
          "mesh":"93x133 rect @150m (49476 tri)","sim_window":"2025-07-19 04:00~20:00",
          "valid_경호교_WSE":{"obs_peak_m":round(float(obs['wse'].max()),2),
                              "sim_peak_m":round(float(sim['WSE_경호교'].max()),2),
                              "diff_m":round(float(sim['WSE_경호교'].max()-obs['wse'].max()),2),
                              "rmse_m":round(rmse,2) if rmse else None},
          "maxdepth_km2(>0.3m)":round(float((md>0.3).sum())*RES*RES/1e6,2),
          "maxdepth_max_m":round(float(md.max()),2)}
    (OUTP/"anuga_reach_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(meta,ensure_ascii=False,indent=2))
    print("saved -> models/anuga_reach/anuga_maxdepth_100m.tif")

if __name__=="__main__": main()
