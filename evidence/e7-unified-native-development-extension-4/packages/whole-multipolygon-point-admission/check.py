from os import environ
from osgeo import gdal,ogr
from pathlib import Path
from hashlib import sha256
from runpy import run_path
from fractions import Fraction as F
import json,sqlite3,itertools
gdal.UseExceptions()
Q=Path(__file__).resolve().parent
raw=run_path(str(Q/'raw.py'))['wkb']
globals().update({k:v for k,v in run_path(str(Q/'oracle.py')).items() if not k.startswith('__')})
PIN='386bc75f4ac46c329cdc44caff01e2e27385d3d89ca3ded26495090def11f669'
SRC=Path(environ['OBSEQ_QGIS_WORLD_MAP'])
LIMIT=420
def seg(r):return list(zip(r,r[1:]))
def boundary(P):return list(itertools.chain.from_iterable(map(seg,P)))
def status(P,p):
 s=classify(P[0],p)
 if s!='interior':return s
 for r in P[1:]:
  s=classify(r,p)
  if s!='exterior':return 'boundary' if s=='boundary' else 'exterior'
 return 'interior'
def boxes(a,b,c,d):return all(max(a[i],b[i])>=min(c[i],d[i]) and max(c[i],d[i])>=min(a[i],b[i]) for i in (0,1))
def stage(parts):
 if not 2<=len(parts)<=12 or sum(len(r)-1 for P in parts for r in P)>LIMIT:return 'scope-size',set(),None
 R=[[list(map(exact,r)) for r in P] for P in parts]
 for P,L in zip(parts,R):
  if not all(scoped([r]) for r in P):return 'ring-unqualified',set(),None
  for U,V in itertools.combinations(L,2):
   if any(boxes(*a,*b) and intersect(*a,*b) for a,b in itertools.product(seg(U),seg(V))):
    return 'within-component-contact',set(),None
  if any(classify(L[0],r[0])!='interior' for r in L[1:]):return 'hole-outside',set(),None
  if any(classify(U,V[0])!='exterior' or classify(V,U[0])!='exterior' for U,V in itertools.combinations(L[1:],2)):
   return 'nested-holes',set(),None
 contacts=set()
 for P,L in itertools.combinations(R,2):
  E=boundary(P);G=boundary(L)
  ep=[{a,b} for a,b in E];gp=[{a,b} for a,b in G]
  for i,(a,b) in enumerate(E):
   for j,(c,d) in enumerate(G):
    if not boxes(a,b,c,d):continue
    A,B,C,D=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
    if A*B<0 and C*D<0:return 'proper-crossing',set(),None
    I={v for o,v in [(A,c),(B,d)] if not o and between(a,b,v)}|{v for o,v in [(C,a),(D,b)] if not o and between(c,d,v)}
    if len(I)>1:return 'shared-edge',set(),None
    ep[i]|=I;gp[j]|=I;contacts|=I
  for cuts,other in ((ep,L),(gp,P)):
   for ps in cuts:
    ps=sorted(ps)
    for a,b in zip(ps,ps[1:]):
     if status(other,((a[0]+b[0])/2,(a[1]+b[1])/2))!='exterior':
      return 'interior-overlap',set(),None
 return 'admitted',contacts,R
def point(q):
 G=ogr.Geometry(ogr.wkbPoint);G.AddPoint_2D(*map(float,q))
 assert (G.GetX().hex(),G.GetY().hex())==tuple(float(v).hex() for v in q)
 return G
def pg(P):
 g=ogr.Geometry(ogr.wkbPolygon)
 for r in P:
  o=ogr.Geometry(ogr.wkbLinearRing)
  for a,b in r:o.AddPoint_2D(a,b)
  g.AddGeometry(o)
 return g
def native_control(parts,expected):
 decision,C,R=stage(parts)
 assert decision==expected
 if not R:return {}
 M=ogr.Geometry(ogr.wkbMultiPolygon)
 for P in parts:M.AddGeometry(pg(P))
 assert M.IsValid()
 tests=set(itertools.chain.from_iterable(points(r) for P in parts for r in P))
 tests|={tuple(map(float,q)) for q in C}
 mismatches,shared=audit(M,R,tests,C)

 return {'contacts':len(C),'point_probes':len(tests),'contact_probes':shared,'differences':mismatches}
def audit(M,R,tests,C):
 mismatches=[];shared=0
 for q in sorted(tests):
  qs=exact(q);V=[status(P,qs) for P in R]
  expected=('interior' in V,any(x!='exterior' for x in V));p=point(q)
  observed=(bool(M.Contains(p)),bool(M.Intersects(p)))
  components=tuple(any(bool(getattr(M.GetGeometryRef(i),op)(p)) for i in range(M.GetGeometryCount())) for op in ('Contains','Intersects'))
  if qs in C:
   shared+=1;assert expected==(False,True)
  if expected!=observed or expected!=components:mismatches.append({'xy_binary64':[float(v).hex() for v in q],'exact':expected,'native_whole':observed,'native_component_or':components})
 return mismatches,shared
def square(a,b,c,d):
 return [(a,b),(c,b),(c,d),(a,d),(a,b)]
auth={}
auth['vertex']=native_control([[square(0,0,1,1)],[square(1,1,2,2)]],'admitted')
tr=[(1,0),(1.5,1),(.5,1),(1,0)]
auth['T_touch']=native_control([[square(0,-1,2,0)],[tr]],'admitted')

# Exact power-of-two rescaling of the *same* failing point and geometry; no claim
# that scaling is a universal numerical remedy.
K=1<<20
zp=[[square(0,-1,2,0)],[tr]];sm=ogr.Geometry(ogr.wkbMultiPolygon)
for P in zp:sm.AddGeometry(pg([[(K*x,K*y) for x,y in r] for r in P]))
tiny=float.fromhex('0x0.0000000000001p-1022');sp=point((K,K*tiny))
assert sm.Contains(sp) and sm.Intersects(sp)
auth['power_two_scaled_stress_same_membership']=[True,True]
mm=ogr.Geometry(ogr.wkbMultiPolygon)
for P in zp:mm.AddGeometry(pg(P))
normal=float.fromhex('0x1p-1022')
controls=[('contact',(1.,0.),(False,True)),('smallest_normal_interior',(1.,normal),(True,True)),('regular_exterior',(1.75,.125),(False,False))]
for n,q,ans in controls:
 pt=point(q)
 v=(bool(mm.Contains(pt)),bool(mm.Intersects(pt)));assert v==ans
 auth['T_'+n]={'exact_and_native':ans,'xy_binary64':[v.hex() for v in q]}
tr2=[(3,1),(4,2),(2,2),(3,1)]
auth['touch_hole_inside']=native_control([[square(0,0,6,6),square(1,1,5,5)],[tr2]],'admitted')
auth['edge_rejected']=native_control([[square(0,0,1,1)],[square(1,0,2,1)]],'shared-edge')
auth['tangent_nested_rejected']=native_control([[square(0,0,1,1)],[[(0,2),(-2,0),(0,-2),(2,0),(0,2)]]],'interior-overlap')
auth['nested_rejected']=native_control([[square(0,0,3,3)],[square(1,1,2,2)]],'interior-overlap')
auth['cross_rejected']=native_control([[square(0,0,2,2)],[square(1,1,3,3)]],'proper-crossing')
A,B=pg([square(0,0,1,1)]),pg([square(1,0,2,1)]);X=pg([square(0,0,2,1)])
p=point((1,.5));assert not (A.Contains(p) or B.Contains(p)) and X.Contains(p)
def main():
 assert sha256(SRC.read_bytes()).hexdigest()==PIN
 db=sqlite3.connect(SRC.as_uri()+'?mode=ro',uri=True)
 n,col,t,z,m=db.execute('select table_name,column_name,geometry_type_name,z,m from gpkg_geometry_columns order by table_name collate binary limit 1').fetchone()
 assert (t,z,m)==('MULTIPOLYGON',0,0)
 fid,= [r[1] for r in db.execute(f'pragma table_info({name(n)})') if r[5] and r[2].upper()=='INTEGER']
 rows=db.execute(f'select {name(fid)},{name(col)} from {name(n)} where {name(fid)}>118 and {name(col)} is not null order by {name(fid)} limit 92').fetchall()
 db.close()
 ds=gdal.OpenEx(str(SRC),gdal.OF_VECTOR|gdal.OF_READONLY); layer=ds.GetLayerByName(n)
 summary={};admitted=[];allv=[]
 for i,blob in rows:
  try:parts=raw(blob)
  except (AssertionError,IndexError):
   st='unsupported-wrapper';summary[st]=summary.get(st,0)+1;allv.append([i,st,None,0]);continue
  st,C,R=stage(parts);summary[st]=summary.get(st,0)+1;allv.append([i,st,len(parts),len(C)])
  if R is None or (not C and sum(v['n_contacts']==0 for v in admitted)>=4):continue
  x=layer.GetFeature(i);M=x.GetGeometryRef()
  assert M.GetGeometryName()=='MULTIPOLYGON' and M.GetGeometryCount()==len(parts)
  for a,P in enumerate(parts):
   g=M.GetGeometryRef(a);assert g.GetGeometryCount()==len(P)
   for b,r in enumerate(P):assert [(u,v) for u,v,*_ in g.GetGeometryRef(b).GetPoints()]==r
  tests=set(itertools.chain.from_iterable(points(r) for P in parts for r in P))
  tests|={tuple(map(float,q)) for q in C}
  diff,k=audit(M,R,tests,C)
  admitted.append({'fid':i,'n_contacts':len(C),'point_probes':len(tests),'contact_probes':k,'differences':diff,'native_valid_postcheck':bool(M.IsValid())})
 print(json.dumps({'native':gdal.VersionInfo(),'geos':[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()],
 'source_sha256':PIN,'full_scanned':len(rows),'all_scope_receipts':allv,'qualification':summary,
 'external':admitted,'authored':auth,'dissolved_seam_not_component_contains':True},indent=2,sort_keys=True))
if __name__=='__main__':main()
