from os import environ
import os,sqlite3,hashlib,math,struct,json,pathlib,runpy
from fractions import Fraction as F
from osgeo import gdal,ogr
gdal.UseExceptions()
root=pathlib.Path(__file__).resolve().parent
wkb=runpy.run_path(str(root/'raw.py'))['wkb']
mf=root/'policy.json';policy=json.loads(mf.read_text())
p=pathlib.Path(environ['OBSEQ_QGIS_WORLD_MAP'])
actual=hashlib.sha256(p.read_bytes()).hexdigest();assert actual==policy['sha256']
def exact(point):return tuple(map(F,point))
def orient(a,b,c):
 return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def between(a,b,p):return all(min(a[i],b[i])<=p[i]<=max(a[i],b[i]) for i in range(2))
def line(a,b,p):return orient(a,b,p)==0 and between(a,b,p)
def intersect(a,b,c,d):
 if line(a,b,c) or line(a,b,d) or line(c,d,a) or line(c,d,b):return True
 return orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0
def scoped(part):
 if len(part)!=1:return False
 r=list(map(exact,part[0]));n=len(r)-1
 if not 3<=n<=80 or len(set(r[:-1]))!=n:return False
 if not all(orient(r[i-1 if i else n-1],r[i],r[i+1]) for i in range(n)):return False
 if not sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(r,r[1:])):return False
 edges=list(zip(r,r[1:]))
 return not any(intersect(*edges[i],*edges[j]) for i in range(n) for j in range(i+2,n)
                if not (i==0 and j==n-1))
def classify(ring,p):
 p=exact(p)
 parity=False
 for a,b in zip(ring,ring[1:]):
  o=orient(a,b,p)
  if not o and between(a,b,p):return 'boundary'
  if (a[1]>p[1])!=(b[1]>p[1]) and (o>0)==(b[1]>a[1]):parity=not parity
 return 'interior' if parity else 'exterior'
def points(ring):
 p=set(ring[:-1]);anchor=sorted(p)
 for (x,y) in anchor:
  for sign in (-math.inf,math.inf):
   p.add((math.nextafter(x,sign),y));p.add((x,math.nextafter(y,sign)))
 for a,b in zip(ring,ring[1:]):
  target=tuple((x+y)/2 for x,y in zip(exact(a),exact(b)))
  candidate=tuple(map(float,target))
  if exact(candidate)==target:p.add(candidate)
 xx,yy=zip(*ring);a,b=min(xx),max(xx);c,d=min(yy),max(yy)
 for i in range(7):
  for j in range(7):p.add((a+(b-a)*(i+1)/8,c+(d-c)*(j+1)/8))
 p.add((a-(b-a),c-(d-c)))
 return sorted(p)
def name(s):
 assert s.replace('_','').isalnum()
 return '"'+s+'"'
def main():
 d=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
 n,c,t,z,m=d.execute('select table_name,column_name,geometry_type_name,z,m from gpkg_geometry_columns order by table_name collate binary limit 1').fetchone()
 assert (z,m)==(0,0) and t in ('POLYGON','MULTIPOLYGON')
 ids=[(r[1],r[2]) for r in d.execute(f'pragma table_info({name(n)})') if r[5]]
 assert len(ids)==1 and ids[0][1].upper()=='INTEGER'
 i=name(ids[0][0]);col=name(c)
 rows=d.execute(f'select {i},{col} from {name(n)} where {col} is not null order by {i} limit 12').fetchall();d.close()
 assert len(rows)==12
 ds=gdal.OpenEx(str(p),gdal.OF_VECTOR|gdal.OF_READONLY);layer=ds.GetLayerByName(n)
 report={'interior':0,'boundary':0,'exterior':0}
 audit=[];diff=[]
 for fid,blob in rows:
  if blob[:2]!=b'GP':audit.append([fid,'wrapper-unqualified']);continue
  parts=wkb(blob)
  chosen=next(((j,part[0]) for j,part in enumerate(parts) if scoped(part)),None)
  if chosen is None:audit.append([fid,'no-simple-component-under-cap']);continue
  j,ring=chosen;f=layer.GetFeature(fid)
  shape=f.GetGeometryRef()
  if shape.GetGeometryName()=='MULTIPOLYGON':shape=shape.GetGeometryRef(j)
  else:assert j==0 and shape.GetGeometryName()=='POLYGON'
  assert shape.GetGeometryCount()==1 and [(a,b) for a,b,*_ in shape.GetGeometryRef(0).GetPoints()]==ring
  count=0;exact_ring=list(map(exact,ring))
  for q in points(ring):
   match=classify(exact_ring,q)
   P=ogr.Geometry(ogr.wkbPoint);P.AddPoint_2D(*q)
   C,I=bool(shape.Contains(P)),bool(shape.Intersects(P))
   gold=match=='interior',match!='exterior'
   if (C,I)!=gold:diff.append([fid,j,[x.hex() for x in q],match,C,I])
   report[match]+=1;count+=1
  audit.append([fid,j,len(ring)-1,count])
 assert all(report.values())
 print(json.dumps({'gdal':gdal.VersionInfo(),'geos':[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()],
  'artifact_sha256':actual,'policy_sha256':hashlib.sha256(mf.read_bytes()).hexdigest(),'layer':n,
  'counts':report,'cohort':audit,'differences':diff},indent=2,sort_keys=True))
if __name__=='__main__':main()
