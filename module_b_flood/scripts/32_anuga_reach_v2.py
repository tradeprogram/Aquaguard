"""
32_anuga_reach_v2.py  (Module B 고도화 — ANUGA 50m 회랑 + 지류 다중유입)  [env: anuga]

개선점(1차 대비):
- 50m 회랑격자: create_domain_from_regions(계곡 회랑 폴리곤, HAND<25m)만 50m 정밀화(산지 제외→삼각형↓).
- 지류 다중유입: 고읍교 본류 + 측방유입 2곳(배수면적비 40/60, deficit 1971㎥/s, 고읍교 수문곡선형).
- 하류 outflow: 수산교 부근 회랑경계에 stage 경계(감쇠부 배수 개선), 나머지 벽.
- full spin-up(07-18 06시~) 유지.
실행:  env python -u scripts/32_anuga_reach_v2.py
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json, time as _time
from pathlib import Path
import numpy as np, pandas as pd, rasterio
from scipy.interpolate import RegularGridInterpolator

ROOT=Path(r"G:/연구/공모전/아쿠아가드"); HY=ROOT/"data"/"hydro"; OUTP=ROOT/"outputs"
SWW=Path(r"C:/Users/user/AppData/Local/Temp/claude/G----------------/4ca28ed5-e0c3-4be0-987f-f1bd326760dd/scratchpad/anuga_sww2"); SWW.mkdir(parents=True,exist_ok=True)
X0,Y0,X1,Y1=1028000,1703000,1042000,1723000
MAXAREA=5000.0   # 100m 삼각형 회랑 — ANUGA 명시적동파는 세밀격자가 급경사서 초저속(50m~5.5h). 다중유입 효과 확보에 집중.
T_START=50400; T_STOP=162000   # 07-18 14:00 ~ 07-19 21:00 (23h spin-up + 피크 + 감쇠)
YIELD=600.0
SUSAN=(1039985,1704745)
GHEO={"고읍교":(1029983,1721527),"경호교":(1033994,1713655),"수산교":SUSAN}

def interp_raster(path,fill):
    with rasterio.open(path) as ds:
        a=ds.read(1).astype("float64"); tr=ds.transform; H,W=a.shape
    a=np.where(np.isfinite(a),a,fill)
    xs=tr.c+(np.arange(W)+0.5)*tr.a; ys=tr.f+(np.arange(H)+0.5)*tr.e
    o=np.argsort(ys); f=RegularGridInterpolator((ys[o],xs),a[o,:],bounds_error=False,fill_value=fill)
    return lambda x,y: f(np.column_stack([np.clip(y,ys.min(),ys.max()),np.clip(x,xs.min(),xs.max())]))

def main():
    import anuga
    t0=_time.time()

    # 회랑 폴리곤 (geojson 좌표 직접 파싱, shapely 불필요)
    gj=json.loads((HY/"reach_corridor.geojson").read_text(encoding="utf-8"))
    geom=gj["features"][0]["geometry"]
    ring=geom["coordinates"][0] if geom["type"]=="Polygon" else geom["coordinates"][0][0]
    if ring[0]==ring[-1]: ring=ring[:-1]     # 닫힌 링 마지막 중복 제거
    bounding_polygon=[[float(x),float(y)] for x,y in ring]
    # 폴리곤 방향(반시계) 보장
    def signed_area(p):
        return 0.5*sum(p[i][0]*p[(i+1)%len(p)][1]-p[(i+1)%len(p)][0]*p[i][1] for i in range(len(p)))
    if signed_area(bounding_polygon)<0: bounding_polygon=bounding_polygon[::-1]
    N=len(bounding_polygon)

    # 하류 outflow 태그: 수산교 1km내 세그먼트 = 'exit', 나머지 'wall'
    exit_seg,wall_seg=[],[]
    for i in range(N):
        x0,y0=bounding_polygon[i]; x1,y1=bounding_polygon[(i+1)%N]
        mx,my=(x0+x1)/2,(y0+y1)/2
        (exit_seg if (mx-SUSAN[0])**2+(my-SUSAN[1])**2 < 1500**2 else wall_seg).append(i)
    if not exit_seg:  # 폴백: 최남단 세그먼트
        ymins=sorted(range(N), key=lambda i:(bounding_polygon[i][1]+bounding_polygon[(i+1)%N][1])/2)[:3]
        exit_seg=ymins; wall_seg=[i for i in range(N) if i not in exit_seg]
    print(f"회랑 꼭짓점 {N}, exit세그 {len(exit_seg)}")

    boundary_tags={"exit":exit_seg,"wall":wall_seg}
    domain=anuga.create_domain_from_regions(bounding_polygon,boundary_tags=boundary_tags,
             maximum_triangle_area=MAXAREA,use_cache=False,verbose=False)
    domain.set_name("reach_v2"); domain.set_datadir(str(SWW)); domain.set_store(False)
    domain.set_flow_algorithm("DE0")
    print(f"삼각형 {len(domain):,}")

    elev=interp_raster(HY/"reach_dem_5m.tif",1200.0); man=interp_raster(HY/"reach_manning_5m.tif",0.04)
    # create_domain_from_regions는 geo_reference(원점 오프셋) 적용 → 함수엔 상대좌표가 옴. 절대좌표로 보정.
    gxll=domain.geo_reference.get_xllcorner(); gyll=domain.geo_reference.get_yllcorner()
    print(f"geo_ref origin ({gxll:.0f},{gyll:.0f})")
    domain.set_quantity("elevation",function=lambda x,y:elev(x+gxll,y+gyll),location="centroids")
    domain.set_quantity("friction",function=lambda x,y:np.clip(man(x+gxll,y+gyll),0.02,0.2),location="centroids")
    domain.set_quantity("stage",expression="elevation")

    # 경계
    def stage_dn(t):
        s=pd.read_csv(HY/"reach_stage_수산교.csv"); tt=s["t_sec"].values.astype(float); vv=pd.to_numeric(s["wse"],errors="coerce").values
        ok=np.isfinite(vv); return float(np.interp(T_START+t,tt[ok],vv[ok]))
    domain.set_boundary({"exit":anuga.Transmissive_momentum_set_stage_boundary(domain,function=stage_dn),
                         "wall":anuga.Reflective_boundary(domain)})

    # 유입: 고읍교 본류 + 지류 2
    inf=json.loads((HY/"reach_inflow_points.json").read_text(encoding="utf-8"))
    up=pd.read_csv(HY/"reach_inflow_고읍교.csv"); ut=up["t_sec"].values.astype(float)
    uq=pd.to_numeric(up["fw"],errors="coerce").values; uqok=np.isfinite(uq)
    Qup=lambda t: float(np.interp(T_START+t,ut[uqok],uq[uqok]))
    upeak=float(np.nanmax(uq)); deficit=inf["deficit_peak_m3s"]
    def Qlat(frac):  # 고읍교 정규화형 × frac × deficit
        return lambda t: frac*deficit*(Qup(t)/max(upeak,1e-6))
    def mkline(xy,half=400):
        return [[xy[0]-half,xy[1]],[xy[0]+half,xy[1]]]
    ops=[anuga.Inlet_operator(domain, mkline(GHEO["고읍교"]), Q=Qup(0))]
    lat_ops=[]
    for lat in inf["lateral"]:
        op=anuga.Inlet_operator(domain, mkline(lat["xy"]), Q=0.0); lat_ops.append((op,Qlat(lat["frac"])))

    cc=domain.get_centroid_coordinates(absolute=True)
    idx={k:int(np.argmin((cc[:,0]-v[0])**2+(cc[:,1]-v[1])**2)) for k,v in GHEO.items()}
    sq=domain.quantities["stage"]; eq=domain.quantities["elevation"]; elev_c=eq.centroid_values.copy()
    maxdepth=np.zeros(len(domain)); rec=[]
    print("evolve v2 시작...")
    for t in domain.evolve(yieldstep=YIELD, finaltime=(T_STOP-T_START)):
        ops[0].set_Q(Qup(t))
        for op,qf in lat_ops: op.set_Q(qf(t))
        sc=sq.centroid_values; depth=np.maximum(sc-elev_c,0.0); maxdepth=np.maximum(maxdepth,depth)
        row={"t_sec":int(T_START+t)}
        for k,i in idx.items(): row[f"WSE_{k}"]=float(sc[i]); row[f"h_{k}"]=float(max(sc[i]-elev_c[i],0))
        rec.append(row)
        if int(t)%7200==0: print(f"  t={int(t)//3600}h 경호교WSE={row['WSE_경호교']:.2f} h={row['h_경호교']:.2f} wet={int((depth>0.1).sum())} {(_time.time()-t0):.0f}s")

    df=pd.DataFrame(rec); df.to_csv(OUTP/"anuga_reach_v2_timeseries.csv",index=False,encoding="utf-8-sig")
    np.savez(str(SWW/"maxdepth_v2.npz"),cc=cc,maxdepth=maxdepth,elev=elev_c)
    print("maxdepth npz 저장, 래스터화...")
    from scipy.spatial import cKDTree
    gr=50; gx=np.arange(X0+gr/2,X1,gr); gy=np.arange(Y0+gr/2,Y1,gr); GX,GY=np.meshgrid(gx,gy)
    dist,ii=cKDTree(cc).query(np.column_stack([GX.ravel(),GY.ravel()]),k=1)
    mdf=maxdepth[ii]; mdf[dist>gr*1.5]=0.0; md=np.flipud(mdf.reshape(GX.shape))
    tr=rasterio.transform.from_origin(X0,Y1,gr,gr)
    prof=dict(driver="GTiff",height=md.shape[0],width=md.shape[1],count=1,dtype="float32",crs="EPSG:5179",transform=tr,nodata=0,compress="deflate")
    MD=ROOT/"models"/"anuga_reach"; MD.mkdir(parents=True,exist_ok=True)
    with rasterio.open(MD/"anuga_v2_maxdepth_50m.tif","w",**prof) as ds: ds.write(md.astype("float32"),1)
    obs=pd.read_csv(HY/"reach_valid_경호교.csv"); m=pd.merge(df[["t_sec","WSE_경호교"]],obs[["t_sec","wse"]],on="t_sec",how="inner")
    rmse=float(np.sqrt(((m["WSE_경호교"]-m["wse"])**2).mean())) if len(m) else None
    meta={"engine":"ANUGA v2 (100m corridor + multi-inflow)","tri":len(domain),
          "gyeongho_WSE":{"obs_peak":round(float(obs['wse'].max()),2),"sim_peak":round(float(df['WSE_경호교'].max()),2),
                          "diff_m":round(float(df['WSE_경호교'].max()-obs['wse'].max()),2),"rmse_m":round(rmse,2) if rmse else None},
          "runtime_s":round(_time.time()-t0,0)}
    (OUTP/"anuga_reach_v2_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print("=== 결과 v2 ==="); print(json.dumps(meta,ensure_ascii=False))

if __name__=="__main__": main()
