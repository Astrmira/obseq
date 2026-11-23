from os import environ
import sqlite3,hashlib,math,struct,json,pathlib
from osgeo import gdal,ogr
gdal.UseExceptions()
policy=json.load(open('selection.json'))
p=pathlib.Path(environ['OBSEQ_QGIS_WORLD_MAP'])
def wkb(blob):
 assert blob[:2]==b'GP' and blob[2]==0
 flags=blob[3];assert flags&0xf0==0
 env=(flags>>1)&7; assert env in (0,1,2,3,4)
 start=8+[0,32,48,48,64][env]
 def read_geom(pos):
  order=blob[pos];assert order in (0,1)
  F='<' if order else '>'; t=struct.unpack_from(F+'I',blob,pos+1)[0];pos+=5
  def count():
   nonlocal pos
   n=struct.unpack_from(F+'I',blob,pos)[0];pos+=4
   assert n<1000000
   return n
  if t==3:
   rings=[]
   for _ in range(count()):
    n=count()
    ring=list(struct.iter_unpack(F+'dd',blob[pos:pos+16*n]));pos+=16*n
    assert len(ring)==n and n>=4 and ring[0]==ring[-1]
    assert all(math.isfinite(a) and math.isfinite(b) for a,b in ring)
    rings.append(ring)
   assert rings
   return [rings],pos
  assert t==6
  result=[]
  for _ in range(count()):
   assert struct.unpack_from(('<' if blob[pos] else '>')+'I',blob,pos+1)[0]==3
   x,pos=read_geom(pos);result.extend(x)
  return result,pos
 result,end=read_geom(start)
 assert result and end==len(blob)
 return result
def extent(poly):
 coords=[x for part in poly for ring in part for x in ring]
 a,b=zip(*coords)
 return min(a),max(a),min(b),max(b)
def rect_domain(shapes,env):
 if any(not v.is_integer() for v in env):return 'noninteger-envelope'
 if len(shapes)!=1 or len(shapes[0])!=1:return 'not-one-rectangle-ring'
 x0,x1,y0,y1=env
 ring=shapes[0][0]
 if len(ring)!=5 or set(ring[:-1])!={(x0,y0),(x0,y1),(x1,y0),(x1,y1)}:
  return 'not-four-corners'
 if not all((a==x)!=(b==y) for (a,b),(x,y) in zip(ring,ring[1:])):
  return 'non-axis-edge'
 return 'admitted'
def ident(s):
 assert s.replace('_','').isalnum()
 return '"'+s+'"'
def main():
 d=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
 n,c,ty,z,m=d.execute('select table_name,column_name,geometry_type_name,z,m from gpkg_geometry_columns order by table_name collate binary limit 1').fetchone()
 assert (z,m)==(0,0) and ty in ('POLYGON','MULTIPOLYGON')
 ids=[r[1] for r in d.execute(f'pragma table_info({ident(n)})') if r[5]]
 assert len(ids)==1
 i=ident(ids[0]);column=ident(c)
 rows=d.execute(f'select {i},{column} from {ident(n)} where {column} is not null order by {i} limit 12').fetchall();d.close()
 assert len(rows)==12
 ds=gdal.OpenEx(str(p),gdal.OF_VECTOR|gdal.OF_READONLY)
 lay=ds.GetLayerByName(n)
 result=[];matched=0
 for fid,blob in rows:
  if blob[:2]!=b'GP':
   result.append([fid,'outside-declared-standard-gpkg-wrapper'])
   continue
  poly=wkb(blob);bb=extent(poly)
  f=lay.GetFeature(fid);assert f.GetFID()==fid
  g=f.GetGeometryRef()
  assert g.GetEnvelope()==bb;matched+=1
  result.append([fid,rect_domain(poly,bb)])
 assert not all(reason=='admitted' for i,reason in result)
 print(json.dumps({'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'policy_sha256':hashlib.sha256(pathlib.Path('selection.json').read_bytes()).hexdigest(),
  'layer':n,'gdal':gdal.VersionInfo(),'sqlite':sqlite3.sqlite_version,
  'independent_envelope_matches':matched,'admission':result,'unchanged_overlap_runner_admitted':False},sort_keys=True,indent=2))
if __name__=='__main__':main()
