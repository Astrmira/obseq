"""Exact orient2d from native binary64 values; use only the stated bounded grid."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import ctypes,hashlib,json,resource,statistics,struct,sys,time

symbol=ctypes.CDLL("libgeos_c.so.1")
symbol.GEOSversion.restype=ctypes.c_char_p
symbol.GEOS_init_r.restype=ctypes.c_void_p
ctx=symbol.GEOS_init_r();assert ctx
orient=symbol.GEOSOrientationIndex_r
orient.argtypes=[ctypes.c_void_p]+[ctypes.c_double]*6
orient.restype=ctypes.c_int
def geos(*values):return orient(ctx,*values)
src=Path(sys.argv[1]); n=int(sys.argv[2])
pre=json.loads(Path(__file__).with_name('SOURCE.json').read_text())
raw=src.read_bytes()
assert hashlib.sha256(raw).hexdigest()==pre['native_wedges_sha256']
wedges=tuple(struct.iter_unpack('<6d',raw))
assert len(wedges)==sum(pre['wedges_by_layer'].values())
def sign(x):return (x>0)-(x<0)
def exact(t):
    rs=[v.as_integer_ratio() for v in t]
    X=max(rs[0][1],rs[2][1],rs[4][1]);Y=max(rs[1][1],rs[3][1],rs[5][1])
    ax,ay,bx,by,cx,cy=[num*((Y if i%2 else X)//den) for i,(num,den) in enumerate(rs)]
    return sign((ax-cx)*(by-cy)-(ay-cy)*(bx-cx))
U=2.0**-53
A=(3.0+16.0*U)*U
def parts(t):
    x,y,bx,by,cx,cy=t
    return (x-cx)*(by-cy),(y-cy)*(bx-cx)
def filtered(t):
    p,q=parts(t);det=p-q
    if abs(det)>A*(abs(p)+abs(q)):
        return sign(det),False
    return exact(t),True
def separate_oracle(t):
    a,b,c,d,e,f=map(Fraction,t)
    return sign((c-a)*(f-b)-(d-b)*(e-a))
def authored(j):
    t=float(10**8-j%999)
    a=(t,t-1.); b=(t-1.,t-2.); c=(0.,0.)
    return a+b+c if j%3==0 else b+a+c if j%3==1 else (t,t,t-1.,t-1.,0.,0.)
# Four increasingly hard code paths, no semantic timing across Python vs GEOS.
# 'ring_tiled' is the ordered native wedge list repeated if needed, not unique features.
modes='ring_tiled','one_in_64_cancellation_controls'
if n==len(wedges):
    offset=0
    order=['ne_110m_admin_0_countries','gis_osm_buildings_a_free','gis_osm_landuse_a_free','gis_osm_natural_a_free','gis_osm_water_a_free']
    ring_stats={}
    for name in order:
        q=pre['wedges_by_layer'][name]
        fast_fail=geos_fail=fallback=0
        for t in wedges[offset:offset+q]:
            det=exact(t)
            p,r=parts(t);fast_fail+=sign(p-r)!=det
            g=geos(*t); assert g in (-1,0,1)
            geos_fail+=g!=det
            f,slow=filtered(t);assert f==det
            fallback+=slow
        ring_stats[name]=dict(n=q,candidate_uncertified=fallback,float_sign_mismatch=fast_fail,geos_sign_mismatch=geos_fail)
        offset+=q
    assert offset==n
else:ring_stats=None
# Independently check exact rational pair differences on a predetermined subset and every authored control.
at=range(0,len(wedges),257)
assert all(exact(wedges[i])==separate_oracle(wedges[i]) for i in at)
for j in range(300):
    t=authored(j)
    label=(-1,1,0)[j%3]
    assert exact(t)==label==separate_oracle(t)==filtered(t)[0] and filtered(t)[1]
counts={}
for mode in modes:
    stress=(mode==modes[1])
    def data():
        for i in range(n):
            yield authored(i//64) if stress and i%64==0 else wedges[i%len(wedges)]
    def pass1(audit):
        pack=bytearray();fall=0
        f=filtered if audit=='filtered' else exact
        if audit=='filtered':
            for t in data():
                v,slow=f(t);pack.append(v+1);fall+=slow
        else:
            for t in data():pack.append(f(t)+1)
        return pack,fall
    times={'filtered':[],'always_exact':[]}
    baseline=None;fall_n=None
    for k in range(3):
        for name in ('filtered','always_exact')[::1 if k%2==0 else -1]:
            t0=time.perf_counter_ns()
            buffer,fall=pass1(name)
            times[name].append(time.perf_counter_ns()-t0)
            if baseline is None:baseline=buffer
            else:assert baseline==buffer
            if name=='filtered':
                assert fall_n is None or fall_n==fall
                fall_n=fall
    counts[mode]=dict(fallback_count=fall_n,samples=times,median_ns={k:statistics.median(x) for k,x in times.items()},
                      exact_labels_sha=hashlib.sha256(baseline).hexdigest(), label_counts=dict(Counter(baseline)))
print(json.dumps(dict(n=n,ring_pool=len(wedges),gdal=pre['gdal'],geos=symbol.GEOSversion().decode(),
                      hard_control_geos_mismatch=sum(geos(*authored(j))!=exact(authored(j)) for j in range(300)),
                      ring_native_comparison=ring_stats,
                      measurements=counts,worker_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),sort_keys=True,indent=2))
