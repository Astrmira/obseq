from osgeo import gdal
from pathlib import Path
import hashlib,json,sys
import numpy as np
gdal.UseExceptions()
inputs=sys.argv[1:] or ['/tmp/r93-source.nc','/tmp/r94-20250102.nc','/tmp/r94-20250201.nc']
expected=[x.split()[0] for x in Path(__file__).with_name('SOURCES.sha256').read_text().splitlines()]
assert len(inputs)==len(expected)==3
def open_t(p,h):
    with open(p,'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==h
    d=gdal.Open(f'NETCDF:{p}:sst')
    b=d.GetRasterBand(1)
    assert d.GetGeoTransform()==(0.,.25,0.,90.,0.,-.25) and (d.RasterYSize,d.RasterXSize)==(720,1440)
    assert b.DataType==gdal.GDT_Int16 and b.GetNoDataValue()==-999
    x=b.ReadAsArray().astype(np.int64)
    m=x!=-999
    assert np.array_equal(m,b.GetMaskBand().ReadAsArray()!=0)
    return x,m,d.GetProjection()
data=[open_t(p,h) for p,h in zip(inputs,expected)]
assert all(np.array_equal(a[1],data[0][1]) and a[2]==data[0][2] for a in data)
def tiles(x,b):
    return x.reshape(720//b,b,1440//b,b).transpose(0,2,1,3).reshape(720//b,1440//b,b*b)
def run_native(q,b,prj):
    u=gdal.GetDriverByName('MEM').Create('',1440,720,3,gdal.GDT_Float64)
    u.SetProjection(prj);u.SetGeoTransform((0.,.25,0.,90.,0.,-.25))
    for j,x in enumerate(q,1):u.GetRasterBand(j).WriteArray(x)
    w=gdal.Warp('',u,format='MEM',outputType=gdal.GDT_Float64,resampleAlg='sum',
                outputBounds=(0,-90,360,90),width=1440//b,height=720//b)
    assert w.GetGeoTransform()==(0.,b*.25,0.,90.,0.,-b*.25)
    return w.ReadAsArray()
out={}
planes={}
for b in (2,4,8):
    rows=[]
    for a,m,crs in data:
        P=[m.astype(np.int64),a*m,a*a*m]
        weighted=[tiles(x,b).sum(axis=-1) for x in P]
        assert np.array_equal(run_native(P,b,crs),weighted)
        rows.append((tiles(a,b),tiles(m,b),weighted))
    for (left,right),name in [(rows[:2],'Jan01-Jan02'),(rows[1:],'Jan02-Feb01')]:
        a,ma,(n,s1,sq1)=left
        z,mz,(nz,s2,sq2)=right
        assert np.array_equal(ma,mz) and np.array_equal(n,nz)
        changed=(a!=z)&ma
        dirty=changed.any(axis=-1)
        assert np.all(n[dirty]>0)
        hides=dirty&(s1==s2)
        square=hides&(sq1==sq2)
        # Equal exact multiset of the complete payload codes (same sentinel
        # positions already certified) implies all symmetric moments agree.
        bag=hides&np.all(np.sort(a,axis=-1)==np.sort(z,axis=-1),axis=-1)
        ext=hides&(np.min(np.where(ma,a,99999),axis=-1)==np.min(np.where(mz,z,99999),axis=-1))&(
                 np.max(np.where(ma,a,-99999),axis=-1)==np.max(np.where(mz,z,-99999),axis=-1))
        assert np.all(~bag|(square&ext))
        delta=z-a
        assert np.all(((delta>0)&changed).any(axis=-1)[hides])
        assert np.all(((delta<0)&changed).any(axis=-1)[hides])
        planes[name,b]=(dirty,s1==s2,(s1==s2)&(sq1==sq2),~dirty|bag)
        out[f'{name}:{b}']=dict(windows=int(n.size),nonempty=int((n>0).sum()),dirty_windows=int(dirty.sum()),
          equal_count_sum_dirty_tiles=int(hides.sum()),dirty_pixels_hidden_by_count_sum=int(changed[hides].sum()),
          still_hidden_after_squares=int(square.sum()),still_hidden_after_minmax=int(ext.sum()),
          still_hidden_after_squares_and_extrema=int((square&ext).sum()),still_hidden_after_exact_bag=int(bag.sum()),
          dirty_pixels_hidden_by_exact_bag=int(changed[bag].sum()))
        assert out[f'{name}:{b}']['equal_count_sum_dirty_tiles']>0
nested={}
def compact(mask,factor):
    H,W=mask.shape
    return mask.reshape(H//factor,factor,W//factor,factor).all(axis=(1,3))
for name in ('Jan01-Jan02','Jan02-Feb01'):
    dirty,eq,_,_=planes[name,8]
    r={}
    for fine in (4,2):
        _,c,sq,bg=planes[name,fine]
        r[fine]=dict(mass_sum=int((dirty&compact(c,8//fine)).sum()),
                     mass_sum_squares=int((dirty&compact(sq,8//fine)).sum()),
                     exact_positionless_bag_per_child=int((dirty&compact(bg,8//fine)).sum()))
        for v in r[fine].values():assert v<=int((dirty&eq).sum())
    assert all(r[4][k]>=r[2][k] for k in r[4])
    nested[name]=r
print(json.dumps(dict(nested_8x8_dirty_admissions=nested,gdal=gdal.VersionInfo('--version'),result=out),sort_keys=True,indent=2))
