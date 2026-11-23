import ctypes as C
import json,hashlib,subprocess,sys
from collections import Counter
from pathlib import Path
import numpy as np
import shapely as S
assert S.__version__=='2.2.0' and S.geos_version_string=='3.14.1'
base=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/pvl-eab-submission/e4/inputs')
datasets={
  'ne':(base/'ne/ne_110m_admin_0_countries.shp','ne_110m_admin_0_countries'),
  'osm_buildings':(base/'osm/liechtenstein.gpkg','gis_osm_buildings_a_free'),
}
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
g=C.CDLL('libgeos_c.so.1')
V=C.c_void_p
def bind(n,r,*a):
    f=getattr(g,n);f.restype=r;f.argtypes=a;return f
v=bind('GEOSversion',C.c_char_p)().decode();assert v.startswith('3.13.1')
ctx=bind('GEOS_init_r',V)()
r=bind('GEOSWKBReader_create_r',V,V)(ctx)
read=bind('GEOSWKBReader_read_r',V,V,V,C.c_char_p,C.c_size_t)
setp=bind('GEOSGeom_setPrecision_r',V,V,V,C.c_double,C.c_int)
rel=bind('GEOSRelate_r',V,V,V,V)
free=bind('GEOSFree_r',None,V,V)
destroy=bind('GEOSGeom_destroy_r',None,V,V)
valid=bind('GEOSisValid_r',C.c_byte,V,V)
isempty=bind('GEOSisEmpty_r',C.c_byte,V,V)
def relation(t):
    assert len(t)==9
    if t[0]=='2':return 'area'
    assert t[0]=='F'
    if t[4]=='1':return 'edge'
    if t[4]=='0':return 'point'
    assert t[4]=='F'
    return 'disjoint'
def within(A):
    q=S.STRtree(A).query(A)
    return {(int(i),int(j)) for i,j in zip(*q) if i<j}
def measure(path,layer):
    process=subprocess.run(['/usr/bin/python3','-IB',str(Path(__file__).with_name('extract.py')),str(path),layer],
                           check=True,capture_output=True)
    w=sorted(json.loads(l) for l in process.stdout.splitlines())
    G=S.from_wkb([bytes.fromhex(b) for _,b in w])
    assert len({i for i,b in w})==len(w) and np.all(np.isin(S.get_type_id(G),[3,6]))
    eligible=S.is_valid(G)&~S.is_empty(G)
    data=[(f,bytes.fromhex(b)) for (f,b),keep in zip(w,eligible) if keep]
    A=G[eligible]
    B=[read(ctx,r,b,len(b)) for _,b in data]
    assert all(q and valid(ctx,q)==1 and isempty(ctx,q)==0 for q in B)
    z={}
    original_candidates=within(A)
    for h in (0.0,1e-5,1e-4):
        Q=S.set_precision(A,h,mode='valid_output')
        checks=[setp(ctx,b,h,0) for b in B]
        assert all(c and valid(ctx,c)==1 for c in checks) and np.all(S.is_valid(Q))
        newempty=S.is_empty(Q)
        oldempty=np.array([isempty(ctx,c)==1 for c in checks])
        assert np.array_equal(newempty,oldempty)
        # Need both releases' bbox candidates if they may reduce differently.
        # Read GEOS C output envelopes via min/max coordinates and cross-check
        # all four bounds against the Shapely output, exactly for nonempty.
        for l,api in enumerate(['XMin','YMin','XMax','YMax']):
            bound=bind('GEOSGeom_get'+api+'_r',C.c_int,V,V,C.POINTER(C.c_double))
            xyz=C.c_double()
            for b,x,e in zip(checks,S.bounds(Q)[:,l],newempty):
                if not e:assert bound(ctx,b,C.byref(xyz))==1 and xyz.value==x
        pairs=sorted(original_candidates|within(Q))
        i,j=map(np.array,zip(*pairs))
        before=[relation(q) for q in S.relate(A[i],A[j])]
        after=[relation(q) for q in S.relate(Q[i],Q[j])]
        def older(arr,x,y):
            ptr=rel(ctx,arr[x],arr[y]);assert ptr
            val=relation(C.string_at(ptr).decode())
            free(ctx,ptr);return val
        for x,y,a,b in zip(i,j,before,after):
            assert (a,b)==(older(B,x,y),older(checks,x,y))
        mat=Counter(f'{a}->{b}' for a,b in zip(before,after))
        z[str(h)]=dict(candidate_pairs=len(pairs),empty=int(newempty.sum()),invalid=0,transition=dict(mat),
                      changed=sum(a!=b for a,b in zip(before,after)),
                      changed_nonempty=sum(a!=b and not(newempty[x] or newempty[y]) for x,y,a,b in zip(i,j,before,after)))
        for c in checks:destroy(ctx,c)
    for b in B:destroy(ctx,b)
    source=[path]+([path.with_suffix(x) for x in ('.shx','.dbf','.prj')] if path.suffix=='.shp' else [])
    return dict(total=len(w),admitted=len(data),excluded_invalid_or_empty=int((~eligible).sum()),
                source={x.name:sha(x) for x in source},metrics=z)
out={name:measure(*a) for name,a in datasets.items()}
bind('GEOSWKBReader_destroy_r',None,V,V)(ctx,r)
bind('GEOS_finish_r',None,V)(ctx)
print(json.dumps(dict(geos_new=S.geos_version_string,geos_old=v,datasets=out),sort_keys=True,indent=2))
