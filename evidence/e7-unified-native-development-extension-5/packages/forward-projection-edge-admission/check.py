import json,math,itertools
from fractions import Fraction as F
from osgeo import gdal,ogr,osr
ogr.UseExceptions()
def srs(code):
 s=osr.SpatialReference();s.ImportFromEPSG(code);s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER);return s
S,T=srs(4326),srs(3857); X=osr.CoordinateTransformation(S,T)
def geom(p,typ):
 g=ogr.Geometry(typ)
 for x,y in p:g.AddPoint_2D(float(x),float(y))
 return g
def rn(g):return ogr.CreateGeometryFromWkb(g.ExportToIsoWkb())
def project(g):
 g=g.Clone();assert g.Transform(X)==0;return rn(g)
def xy(g):return [tuple(map(F,p[:2])) for p in g.GetPoints()]
def det(a,b,p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
def on(a,b,p):return det(a,b,p)==0 and all(min(x,y)<=v<=max(x,y) for x,y,v in zip(a,b,p))
def check(g,p):
 z,=xy(p); v=xy(g)
 answer=any(on(a,b,z) for a,b in zip(v,v[1:]))
 assert answer==bool(g.Intersects(p))
 return answer
def sample(a,b,t):return tuple(F(x)*(1-t)+F(y)*t for x,y in zip(a,b))
def gap(a,b,p):
 if a[0]==b[0]:return F(0)
 return det(a,b,p)/(b[0]-a[0])
def bound(a,b,n):
 R=6378137
 z=max(abs(math.radians(a[1])),abs(math.radians(b[1])))
 h=math.radians(b[1]-a[1])/n
 return R*abs(math.tan(z)/math.cos(z))*h*h/8
def box_orientation(a,b,p,budget):
 cr=[(v-budget,v+budget) for v in a+b+p]
 ds=[det(t[:2],t[2:4],t[4:]) for t in itertools.product(*cr)]
 return min(ds),max(ds)
cases=[('north',(-5,10),(5,30)),('south',(-5,-10),(5,-30)),('horizontal',(-5,20),(5,20)),('vertical', (3,10),(3,30)),('equator_symmetric',(-5,-20),(5,20)),('north_heldout',(11,38),(19,56))]
allrows=[]
for name,a,b in cases:
 ns=2
 while bound(a,b,ns)>100:ns*=2
 src=rn(geom([a,b],ogr.wkbLineString))
 chord=project(src)
 dense=project(geom([sample(a,b,F(i,ns)) for i in range(ns+1)],ogr.wkbLineString))
 assert len(xy(chord))==2 and len(xy(dense))==ns+1
 rows=[]
 for t in [F(0),F(1,2),F(ns+1,2*ns),F(1)]:
  p=rn(geom([sample(a,b,t)],ogr.wkbPoint));j=project(p); pt,=xy(j)
  # Keep identity of selected interior source edge and its exact rational parameter.
  assert check(src,p)
  c=check(chord,j);d=check(dense,j)
  assert d if (t*ns).denominator==1 else True
  a0,b0=xy(chord); diff=gap(a0,b0,pt)
  q=min(int(t*ns),ns-1); seg=xy(dense)[q:q+2]
  g2=gap(*seg,pt)
  assert abs(float(g2))<=bound(a,b,ns)+1e-7
  if t in (0,1) or name in ('horizontal','vertical'):
   assert c and d
  elif name in ('north','south','north_heldout'):
   assert not c and (diff>0)==(name=='south')
   if (t*ns).denominator!=1:assert not d
  if name=='equator_symmetric' and t==F(1,2):assert c and d
  corners=box_orientation(a0,b0,pt,F(1,100))
  # Illustrative hypothetical bound on the stored coordinates, not certified PROJ error.
  sign='positive' if corners[0]>0 else 'negative' if corners[1]<0 else 'unresolved'
  if t not in (0,1) and name in ('north','south','north_heldout'):assert sign!='unresolved'
  rows.append(dict(t=str(t),chord_native_and_exact=c,dense_native_and_exact=d,source_native_and_exact=True,
     chord_vertical_signed_gap_m=round(float(diff),8),dense_vertical_signed_gap_m=round(float(g2),8),illustrative_centimeter_box_chord_sign=sign))
 allrows.append(dict(case=name,n=ns,analytic_real_arithmetic_bound_m=round(bound(a,b,ns),8),rows=rows))
print(json.dumps(dict(gdal=gdal.VersionInfo('RELEASE_NAME'),proj=[osr.GetPROJVersionMajor(),osr.GetPROJVersionMinor(),osr.GetPROJVersionMicro()],geos=[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()],cases=allrows),sort_keys=True,indent=2))
