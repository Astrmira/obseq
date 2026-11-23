from osgeo import ogr,gdal
from pathlib import Path
import json,tempfile,hashlib
gdal.UseExceptions()
m=json.load(open('manifest.json')); assert m['schema']=='spatial-receipt/v1'
def geom(r):
 x0,y0,x1,y1=r
 return ogr.CreateGeometryFromWkt(f'POLYGON (({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))')
def cells(r):
 a,b,c,d=r
 return {(i,j) for i in range(a,c) for j in range(b,d)}
def oracle(m):
 old=cells(m['old_region']);new=cells(m['new_region'])
 out={}
 for i,g,r in m['rows']:
  S=cells(r);stats=[len(S&old),len(S&new),len(S&(new-old)),len(S&(old-new))]
  assert stats[1]-stats[0]==stats[2]-stats[3]
  out[i]=stats
 return out
O=oracle(m);expected={i:v[1] for i,v in O.items()}
expected_set=sorted(i for i,v in expected.items() if v>=m['threshold'])
parts={i:p for i,p,_ in m['rows']}
affected=[i for i,v in O.items() if v[0]!=v[1]]
assert affected==[11,12]
def native(path,ids_to_refresh):
 old,new=map(geom,(m['old_region'],m['new_region']))
 d=ogr.GetDriverByName('GPKG').CreateDataSource(str(path))
 l=d.CreateLayer('shapes',geom_type=ogr.wkbPolygon)
 for n,t in [('partition',ogr.OFTString),('score',ogr.OFTInteger64),('epoch',ogr.OFTInteger)]:
  l.CreateField(ogr.FieldDefn(n,t))
 for id,part,rect in m['rows']:
  geom_i=geom(rect);f=ogr.Feature(l.GetLayerDefn());f.SetFID(id);f.SetGeometry(geom_i)
  overlap=geom_i.Intersection(old).GetArea()
  assert overlap==O[id][0]
  f.SetField(0,part);f.SetField(1,int(overlap));f.SetField(2,0)
  assert l.CreateFeature(f)==ogr.OGRERR_NONE
 for id in ids_to_refresh:
  f=l.GetFeature(id);overlap=f.GetGeometryRef().Intersection(new).GetArea()
  assert overlap==expected[id]
  f.SetField(1,int(overlap));f.SetField(2,1)
  assert l.SetFeature(f)==ogr.OGRERR_NONE
 l=None;d=None
 d=ogr.Open(str(path));l=d.GetLayer()
 out={}
 shape={i:r for i,_,r in m['rows']}
 for f in l:
  i=f.GetFID()
  assert i not in out and f.GetGeometryRef().SymDifference(geom(shape[i])).IsEmpty()
  out[i]=(f.GetField(0),f.GetField(1),f.GetField(2))
 assert sorted(out)==sorted(expected)
 assert all(r[0]==parts[i] for i,r in out.items())
 return out
results={}
with tempfile.TemporaryDirectory() as t:
 for label,refresh in [('old',[]),('partial',[11]),('sparse-exact',affected),('recompute',expected)]:
  obs=native(Path(t)/(label+'.gpkg'),refresh)
  bypart={}
  for i,(p,v,e) in obs.items():bypart.setdefault(p,[]).append(e)
  aggregate={p:sum(v for q,v,e in obs.values() if p==q) for p in bypart}
  results[label]={'artifact_geometry_and_ids_match':True,
   'partition_latest_epoch':{p:max(ee) for p,ee in bypart.items()},
   'partition_oldest_epoch':{p:min(ee) for p,ee in bypart.items()},
   'mismatching_score_ids':[i for i,(p,v,e) in obs.items() if v!=expected[i]],
   'result_matches':sorted(i for i,(p,v,e) in obs.items() if v>=m['threshold'])==expected_set,
   'aggregate':aggregate,'production_epoch_current':all(e==1 for p,v,e in obs.values()),
   'mixed_epoch_partitions':sorted(p for p,ee in bypart.items() if len(set(ee))>1)}
 assert results['old']['aggregate']==results['recompute']['aggregate']
 assert results['partial']['partition_latest_epoch']['north']==1 and results['partial']['mismatching_score_ids']==[12]
 assert not results['sparse-exact']['mismatching_score_ids'] and results['sparse-exact']['result_matches']
 assert not results['sparse-exact']['production_epoch_current'] and results['recompute']['production_epoch_current']
print(json.dumps({'gdal':gdal.VersionInfo(),'geos':[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()],
 'manifest_sha256':hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
 'scores_indexed_by_fid':O,'results':results},indent=2,sort_keys=True))
