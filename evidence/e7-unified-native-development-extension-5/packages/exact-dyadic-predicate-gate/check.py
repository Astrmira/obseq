from os import environ
from math import nextafter,ldexp,isfinite,inf
from fractions import Fraction as F
from pathlib import Path
from runpy import run_path
from collections import Counter
from hashlib import sha256
from osgeo import ogr,gdal
import sqlite3,itertools,json,sys
H=Path(__file__).resolve().parent
data=run_path(str(H/'oracle.py'))
classify,points,orient=[data[k] for k in ('classify','points','orient')]
wkb=run_path(str(H/'raw.py'))['wkb']
gdal.UseExceptions()
SMALL=float.fromhex('0x0.0000000000001p-1022')
assert sys.float_info.radix==2 and sys.float_info.mant_dig==53
assert SMALL>0 and nextafter(0.,inf)==SMALL and SMALL+SMALL==2*SMALL and ldexp(SMALL,20)>0
def exact_scale(x,k):
 try:y=ldexp(x,k);z=ldexp(y,-k)
 except OverflowError:return None
 if not isfinite(y) or z.hex()!=x.hex() or F(y)!=F(x)*F(2)**k:return None
 return y
def scale(x,k):
 out=tuple(exact_scale(v,k) for v in x)
 return None if any(v is None for v in out) else out
def outward(a,b):
 if not isfinite(a) or not isfinite(b):raise OverflowError
 x,y=nextafter(a,-inf),nextafter(b,inf)
 if not isfinite(x) or not isfinite(y):raise OverflowError
 return (x,y)
def sub(X,Y):return outward(X[0]-Y[1],X[1]-Y[0])
def mul(X,Y):
 L=[x*y for x in X for y in Y]
 if not all(isfinite(z) for z in L):raise OverflowError
 return outward(min(L),max(L))
def isgn(a,b,c,C):
 # Degenerate-axis exact-zero shortcuts, when warranted by identical coordinate bits.
 if a==b or a==c or b==c or a[0]==b[0]==c[0] or a[1]==b[1]==c[1]:
  C['structural_zero']+=1;return 0
 X=[(x,x) for x in a+b+c]
 try:
  q=sub(mul(sub(X[2],X[0]),sub(X[5],X[1])),mul(sub(X[3],X[1]),sub(X[4],X[0])))
  if q[0]>0 or q[1]<0:
   z=1 if q[0]>0 else -1
   C['interval_sign']+=1
   o=orient(*[tuple(map(F,x)) for x in (a,b,c)])
   assert z==int(o>0)-int(o<0)
   return z
 except OverflowError:
  C['overflow_fallback']+=1
 else:C['zero_containing_fallback']+=1
 v=orient(*[tuple(map(F,x)) for x in (a,b,c)])
 return int(v>0)-int(v<0)
def fclass(R,p,C):
 inside=False
 for a,b in zip(R,R[1:]):
  ray=(a[1]>p[1])!=(b[1]>p[1])
  bb=all(min(x,y)<=z<=max(x,y) for x,y,z in zip(a,b,p))
  if not ray and not bb:continue
  s=isgn(a,b,p,C)
  if s==0 and bb:return 'boundary'
  if ray and (s>0)==(b[1]>a[1]):inside=not inside
 return 'interior' if inside else 'exterior'
def exclass(R,p):
 return classify([tuple(map(F,x)) for x in R],p)
def status(P,p,c,mode):
 f=(lambda R,q:fclass(R,q,c)) if mode=='filter' else exclass
 o=f(P[0],p)
 if o!='interior':return o
 for R in P[1:]:
  s=f(R,p)
  if s!='exterior':return 'boundary' if s=='boundary' else 'exterior'
 return 'interior'
def pred(polys,p,mode,C):
 S=[status(P,p,C,mode) for P in polys]
 return ('interior' in S, any(x!='exterior' for x in S))
square=lambda a,b,c,d:[(a,b),(c,b),(c,d),(a,d),(a,b)]
T=[[square(0.,-1.,2.,0.)],[[(1.,0.),(1.5,1.),(.5,1.),(1.,0.)]]]
P=(1.,SMALL)
def native(PP,p):
 M=ogr.Geometry(ogr.wkbMultiPolygon)
 for P0 in PP:
  G=ogr.Geometry(ogr.wkbPolygon)
  for R in P0:
   ring=ogr.Geometry(ogr.wkbLinearRing)
   for x,y in R:ring.AddPoint_2D(x,y)
   G.AddGeometry(ring)
  M.AddGeometry(G)
 x=ogr.Geometry(ogr.wkbPoint);x.AddPoint_2D(*p)
 assert (x.GetX().hex(),x.GetY().hex())==tuple(v.hex() for v in p)
 return bool(M.Contains(x)),bool(M.Intersects(x))
cases=[]
for k in (0,20):
 J=[[[scale(q,k) for q in R] for R in L] for L in T]
 p=scale(P,k);assert p and all(all(all(x is not None for x in R) for R in L) for L in J)
 C=Counter();ex=pred(T,P,'exact',C)
 assert ex==pred(J,p,'exact',C)==pred(J,p,'filter',C)==(True,True)
 no=native(J,p)
 cases.append({'scale':k,'native':no,'exact_filter':ex,'arithmetic_route':C,'point_hex':[v.hex() for v in p]})
assert cases[0]['native']==(False,True) and cases[1]['native']==(True,True)
# Products can still underflow even if coordinate scaling is exactly admissible.
a,b,c=(0.,0.),(SMALL,0.),(0.,SMALL)
mixed=(ldexp(1.,1023),SMALL)
assert scale(mixed,1) is None and scale(mixed,-1) is None
L=[scale(v,20) for v in (a,b,c)];assert all(L)
assert (L[1][0]-L[0][0])*(L[2][1]-L[0][1])==0.
C=Counter();assert isgn(*L,C)==1 and C['zero_containing_fallback']==1
assert isgn((0.,0.),mixed,(0.,mixed[0]),C)==1 and C['overflow_fallback']==1
# Repeat precisely the externally admitted original four disjoint fixtures.
old=json.loads((H/'prior-whole-receipt.json').read_text())
SRC=Path(environ['OBSEQ_QGIS_WORLD_MAP'])
assert sha256(SRC.read_bytes()).hexdigest()==old['source_sha256']
db=sqlite3.connect(SRC.as_uri()+'?mode=ro',uri=True)
n,c,*_=db.execute('select table_name,column_name,geometry_type_name,z,m from gpkg_geometry_columns order by table_name collate binary limit 1').fetchone()
ids=[r['fid'] for r in old['external']];N=data['name']
fid,=[r[1] for r in db.execute(f'pragma table_info({N(n)})') if r[5] and r[2].upper()=='INTEGER']
count=0;pr=Counter();scale_count=0
for i in ids:
 value,=db.execute(f'SELECT {N(c)} FROM {N(n)} WHERE {N(fid)}=?',(i,)).fetchone()
 PP=wkb(value);Q=set(itertools.chain.from_iterable(points(r) for p in PP for r in p))
 assert all(scale(q,20) is not None for p in PP for rr in p for q in rr)
 for q in Q:
  assert pred(PP,q,'filter',pr)==pred(PP,q,'exact',pr);count+=1
  scale_count+=scale(q,20) is not None
assert count==1479
print(json.dumps({'gdal':gdal.VersionInfo(),'geos':[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()], 'same_authored_T':cases,
 'external_probes':count,'external_probe_coords_2p20_exactly_scaled':scale_count,
 'external_orientation_routes':pr,'external_all_vertices_2p20_exactly_scaled':True,'mixed_or_underflow_control_routes':C,
 'mixed_global_scale_nonzero_admissible':False},sort_keys=True,indent=2))
