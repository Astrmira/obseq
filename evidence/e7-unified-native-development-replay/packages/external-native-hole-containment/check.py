from os import environ
from osgeo import gdal,ogr
import runpy,sqlite3,pathlib,hashlib,json,itertools
gdal.UseExceptions()
root=pathlib.Path(__file__).resolve().parent
globals().update({k:v for k,v in runpy.run_path(str(root/'oracle.py')).items() if not k.startswith('__')})
wkb=runpy.run_path(str(root/'raw.py'))['wkb']
policy=root/'policy.json';mf=json.loads(policy.read_text())
path=pathlib.Path(environ['OBSEQ_QGIS_WORLD_MAP']);h=hashlib.sha256(path.read_bytes()).hexdigest();assert h==mf['sha256']
def qualifies(p):
 if len(p)<2 or sum(len(r)-1 for r in p)>220:return False
 if not all(scoped([r]) for r in p):return False
 ex=[list(map(exact,r)) for r in p]
 bounds=[list(zip(r,r[1:])) for r in ex]
 # Disjoint boundaries, including zero-dimensional contacts.
 for a,b in itertools.combinations(bounds,2):
  if any(intersect(*x,*y) for x,y in itertools.product(a,b)):return False
 # Once disjoint, one strictly interior hole vertex is enough for whole hole.
 if not all(classify(ex[0],r[0])=='interior' for r in p[1:]):return False
 if any(classify(ex[a],p[b][0])!='exterior' or classify(ex[b],p[a][0])!='exterior'
        for a,b in itertools.combinations(range(1,len(p)),2)):return False
 return True
def status(poly,q):
 shell=classify(poly[0],q)
 if shell!='interior':return 'shell-boundary' if shell=='boundary' else 'outside'
 for hole in poly[1:]:
  h=classify(hole,q)
  if h!='exterior':return 'hole-boundary' if h=='boundary' else 'hole-interior'
 return 'interior'
def main():
 d=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
 n,c,t,z,m=d.execute('select table_name,column_name,geometry_type_name,z,m from gpkg_geometry_columns order by table_name collate binary limit 1').fetchone()
 assert (z,m)==(0,0) and t=='MULTIPOLYGON'
 ids=[(r[1],r[2]) for r in d.execute(f'pragma table_info({name(n)})') if r[5]]
 assert len(ids)==1 and ids[0][1].upper()=='INTEGER'
 i=name(ids[0][0]);col=name(c)
 rows=d.execute(f'select {i},{col} from {name(n)} where {i}>21 and {col} is not null order by {i} limit 96').fetchall()
 d.close()
 ds=gdal.OpenEx(str(path),gdal.OF_VECTOR|gdal.OF_READONLY);layer=ds.GetLayerByName(n)
 report={k:0 for k in ('shell-boundary','hole-boundary','outside','interior','hole-interior')}
 audit=[];diff=[];selected=0
 for fid,blob in rows:
  if blob[:2]!=b'GP':audit.append([fid,'wrapper-unqualified']);continue
  parts=wkb(blob)
  chosen=next(((i,r) for i,r in enumerate(parts) if qualifies(r)),None)
  if chosen is None:audit.append([fid,'no-qualifying-holed-component']);continue
  idx,rings=chosen
  selected+=1
  xf=layer.GetFeature(fid)
  g=xf.GetGeometryRef().GetGeometryRef(idx)
  assert g.GetGeometryCount()==len(rings)
  for i,r in enumerate(rings):assert [(a,b) for a,b,*_ in g.GetGeometryRef(i).GetPoints()]==r
  Q=sorted(set(itertools.chain.from_iterable(points(r) for r in rings)))
  rr=[list(map(exact,r)) for r in rings]
  for q in Q:
   st=status(rr,q);report[st]+=1
   P=ogr.Geometry(ogr.wkbPoint);P.AddPoint_2D(*q)
   C,I=bool(g.Contains(P)),bool(g.Intersects(P))
   gold=st=='interior',st in ('interior','shell-boundary','hole-boundary')
   if (C,I)!=gold:diff.append([fid,idx,[b.hex() for b in q],st,C,I])
  audit.append([fid,idx,len(rings)-1,len(Q)])
  if selected==4:break
 print(json.dumps({'gdal':gdal.VersionInfo(),'geos':[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()],
  'artifact_sha256':h,'policy_sha256':hashlib.sha256(policy.read_bytes()).hexdigest(),
  'layer':n,'selected':selected,'counts':report,'cohort':audit,'differences':diff},indent=2,sort_keys=True))
if __name__=='__main__':main()
