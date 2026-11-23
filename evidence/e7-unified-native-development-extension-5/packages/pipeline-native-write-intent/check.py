from itertools import product
from osgeo import ogr,gdal
import json,tempfile,pathlib,sqlite3
gdal.UseExceptions()
out=[]
def put(f,i,v):
 if v is None:f.SetFieldNull(i)
 else:f.SetField(i,v)
with tempfile.TemporaryDirectory() as t:
 for order,(driver,path) in product(['alternate','grouped','complete-only'],[('Memory','scratch'),('GPKG',str(pathlib.Path(t)/'trace.gpkg')),('SQLite',str(pathlib.Path(t)/'trace.sqlite'))]):
  name=path if driver=='Memory' else str(pathlib.Path(path).with_stem(pathlib.Path(path).stem+'-'+order))
  d=ogr.GetDriverByName(driver).CreateDataSource(name)
  l=d.CreateLayer('test',geom_type=ogr.wkbNone)
  for field in ('k','control'):
   f=ogr.FieldDefn(field,ogr.OFTInteger);f.SetDefault('99');l.CreateField(f)
  first=len(out)
  cases=list(product([42,None,0],['keep','clear','zero'],['sparse','complete']))
  if order=='grouped':cases.sort(key=lambda x:x[2]=='complete')
  if order=='complete-only':cases=[x for x in cases if x[2]=='complete']
  for prior,intent,mode in cases:
   old=ogr.Feature(l.GetLayerDefn());put(old,0,prior);old.SetField(1,17);l.CreateFeature(old)
   fid=old.GetFID()
   if mode=='complete':new=l.GetFeature(fid)
   else:
    new=ogr.Feature(l.GetLayerDefn());new.SetFID(fid)
   if intent!='keep':put(new,0,None if intent=='clear' else 0)
   error=None
   try:l.SetFeature(new)
   except RuntimeError as e:error=str(e)
   read=l.GetFeature(fid);values=[read.GetField(i) for i in range(2)]
   states=['null' if read.IsFieldNull(i) else 'value' if read.IsFieldSet(i) else 'unset' for i in range(2)]
   expect=[prior if intent=='keep' else None if intent=='clear' else 0,17]
   out.append(dict(driver=driver,prior=prior,intent=intent,mode=mode,values=values,states=states,
                   fid=fid,order=order,drift=values!=expect,error=error))
  l=None;d=None
  if driver!='Memory':
   with sqlite3.connect(name) as db:
    external={i:[a,b] for i,a,b in db.execute('select rowid,k,control from test')}
   assert external=={r['fid']:r['values'] for r in out[first:]}
assert len(out)==135
assert all(not r['drift'] and r['error'] is None for r in out if r['order']=='complete-only' or r['driver']=='SQLite')
assert sum(bool(r['error']) for r in out if r['driver']=='GPKG')==19
assert sum(r['drift'] for r in out if r['driver']=='Memory')==18
print(json.dumps({'gdal':gdal.VersionInfo(),'sqlite_oracle':sqlite3.sqlite_version,'drift':sum(r['drift'] for r in out),'cases':out},indent=2,sort_keys=True))
