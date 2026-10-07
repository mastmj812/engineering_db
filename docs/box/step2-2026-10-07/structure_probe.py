"""BOX step 2 side-probe (2026-10-07, read-only, not a pipeline step): do Holden's 2BS structure
grids add edge information for BS2_S? Run from the repo root after scripts.box_edge_gap:
    python docs/box/step2-2026-10-07/structure_probe.py <out_dir>
Reads the GGX xyz grids (UTM 14N NAD83 US-ft, Z = KB-relative MD/TVD) from the Engineering
SharePoint sync folder and outline_BS2_S.geojson; writes structure_probe.png + prints the tables."""
import shapely.ops
import sys, json, numpy as np, pandas as pd, shapely, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from shapely.geometry import shape
from pyproj import Transformer
SP=sys.argv[1]; G="C:/Users/MichaelMast/Blue Ox Resources/Engineering - General/Structure Grids/Delaware/"
USFT=1200/3937
def grid(name):
    a=np.loadtxt(G+f"HCA_{name}_STRUCTURE_MDXYZ_grid.xyz",delimiter=",")
    xs=np.unique(a[:,0]); ys=np.unique(a[:,1]); Z=np.full((len(ys),len(xs)),np.nan)
    ix=np.searchsorted(xs,a[:,0]); iy=np.searchsorted(ys,a[:,1]); z=a[:,2]; z[z>1e9]=np.nan; Z[iy,ix]=z
    return xs,ys,Z
xs,ys,top=grid("2BSPGS"); bx_,by_,b0=grid("3BSPGC")
from scipy.interpolate import RegularGridInterpolator as _R
_X,_Y=np.meshgrid(xs,ys); base=_R((by_,bx_),b0,bounds_error=False,fill_value=np.nan)(np.column_stack([_Y.ravel(),_X.ravel()])).reshape(_X.shape)
print("base lattice",b0.shape,"x0",bx_[0]-xs[0],"y0",by_[0]-ys[0])
dx=np.diff(xs).mean(); print("nodes",top.shape,"spacing ft",round(dx),"top non-null",np.isfinite(top).mean().round(3))
ctl=pd.read_csv(G+"HCA_2BSPGS_STRUCTURE_MDXYZ_data.xyz",header=None,names=["x","y","z"])
# BS2_S main body outline (4326) -> UTM14N usft
gj=json.load(open("docs/box/step2-2026-10-07/outline_BS2_S.geojson"))
tr=Transformer.from_crs("EPSG:4326","EPSG:32614",always_xy=True)
def tous(g): return shapely.transform(g,lambda c: np.column_stack(tr.transform(c[:,0],c[:,1]))/USFT)
body=[tous(shape(f["geometry"])) for f in gj["features"] if f["properties"]["layer"]=="outline" and f["properties"]["main_body"]][0]
segs=pd.DataFrame([{**f["properties"],"g":tous(shape(f["geometry"]))} for f in gj["features"] if f["properties"]["layer"]=="segment"])
# derived surfaces
gy,gx=np.gradient(top,dx)
dip=np.hypot(gx,gy)*5280                       # ft/mi
lap=(np.roll(top,1,0)+np.roll(top,-1,0)+np.roll(top,1,1)+np.roll(top,-1,1)-4*top)  # ft per node^2: local bend
iso=base-top
X,Y=np.meshgrid(xs,ys)
pts=shapely.points(X.ravel(),Y.ravel()); inside=shapely.contains(body,pts).reshape(X.shape)
ring=shapely.contains(body.buffer(5*5280),pts).reshape(X.shape)&~inside
def s(a,m): v=a[m&np.isfinite(a)]; return f"n={len(v)} p10/50/90 {np.percentile(v,10):.0f}/{np.median(v):.0f}/{np.percentile(v,90):.0f}" if len(v) else "n=0"
print("coverage inside body",np.isfinite(top[inside]).mean().round(3),"ring 0-5mi out",np.isfinite(top[ring]).mean().round(3))
print("dip ft/mi  inside",s(dip,inside)," ring",s(dip,ring))
print("|lap| ft   inside",s(np.abs(lap),inside)," ring",s(np.abs(lap),ring))
print("isopach ft inside",s(iso,inside)," ring",s(iso,ring))
# control wells: inside / near laterals?
cp=shapely.points(ctl.x,ctl.y); cin=shapely.contains(body,cp); cring=shapely.contains(body.buffer(5*5280),cp)&~cin
print("control pts",len(ctl),"inside body",cin.sum(),"0-5 mi outside",cring.sum())
# per edge segment: sample 1 mi outside vs 1 mi inside along the normal ~ use buffers
from scipy.interpolate import RegularGridInterpolator as RGI
def samp(A):
    f=RGI((ys,xs),A,bounds_error=False,fill_value=np.nan); return lambda x,y: f(np.column_stack([y,x]))
fdip,fiso,flap=samp(dip),samp(iso),samp(np.abs(lap))
rows=[]
out1=body.buffer(5280).exterior; in1=body.buffer(-5280)
for _,r in segs.iterrows():
    m=r.g.interpolate(0.5,normalized=True)
    po=out1.interpolate(out1.project(m)); 
    inb=shapely.boundary(in1); pi=shapely.ops.nearest_points(inb,m)[0] if not in1.is_empty else m
    rows.append(dict(side=r.side,kind=r.kind,len=r.length_ft,
        dip_out=fdip(po.x,po.y)[0],dip_in=fdip(pi.x,pi.y)[0],iso_out=fiso(po.x,po.y)[0],iso_in=fiso(pi.x,pi.y)[0],lap_out=flap(po.x,po.y)[0],
        ctl_out=int(shapely.dwithin(cp,po,2640).sum())))
e=pd.DataFrame(rows); e["w"]=e.len
def wm(g,c): v=g[np.isfinite(g[c])]; return np.average(v[c],weights=v.w) if len(v) else np.nan
t=e.groupby("side").apply(lambda g: pd.Series({"mi":g.len.sum()/5280,"cov_out":np.isfinite(g.dip_out).mean(),"dip_in":wm(g,"dip_in"),"dip_out":wm(g,"dip_out"),
   "iso_in":wm(g,"iso_in"),"iso_out":wm(g,"iso_out"),"lap_out":wm(g,"lap_out"),"ctl_within_half_mi_out":g.ctl_out.mean()}))
print(t.reindex(["N","NE","E","SE","S","SW","W","NW"]).round(2).to_string())
print(e.groupby("kind").apply(lambda g: pd.Series({"iso_out":wm(g,"iso_out"),"iso_in":wm(g,"iso_in"),"dip_out":wm(g,"dip_out")})).round(1))
# map
fig,axs=plt.subplots(1,3,figsize=(24,9))
for ax,(A,ttl,cm) in zip(axs,[(top,"2BS sand top (MD/KB-TVD, ft)","viridis_r"),(dip,"dip, ft/mi","magma"),(iso,"2BS sand isopach 2BSPGS→3BSPGC, ft","cividis")]):
    im=ax.pcolormesh(xs,ys,A,cmap=cm,shading="nearest",vmin=np.nanpercentile(A,2),vmax=np.nanpercentile(A,98)); fig.colorbar(im,ax=ax,shrink=.7)
    for _,r in segs.iterrows():
        c=np.asarray(r.g.coords); ax.plot(c[:,0],c[:,1],color="#16a34a" if r.kind=="pinned" else "#ef4444",lw=1.5)
    ax.scatter(ctl.x,ctl.y,s=1,c="k",alpha=.3)
    bx=body.bounds; ax.set_xlim(bx[0]-80000,bx[2]+80000); ax.set_ylim(bx[1]-150000,bx[3]+40000); ax.set_aspect("equal"); ax.set_title(ttl); ax.set_xticks([]); ax.set_yticks([])
fig.tight_layout(); fig.savefig(SP+"/structure_probe_BS2_S.png",dpi=60)
