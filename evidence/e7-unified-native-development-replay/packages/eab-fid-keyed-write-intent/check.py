from osgeo import gdal,ogr
import numpy as np
import json,sqlite3,tempfile,pathlib
gdal.UseExceptions()
m=json.load(open('manifest.json')); initial={int(i):x for i,x in m['initial'].items()}
meta={int(i):x for i,x in m['fid_to_kind'].items()}; expected={int(i):x for i,x in m['expected'].items()}
assert m['version']=='int64-lineage/v1'
def read(order,limit):
 d=ogr.GetDriverByName('Memory').CreateDataSource('d')
 l=d.CreateLayer('src',geom_type=ogr.wkbNone)
 l.CreateField(ogr.FieldDefn('k',ogr.OFTInteger64))
 vals={11:9007199254740993,12:0,13:None,14:None,15:None}
 for i in order:
  f=ogr.Feature(l.GetLayerDefn());f.SetFID(i)
  if vals[i] is not None:f.SetField(0,vals[i])
  elif i==14:f.SetFieldNull(0)
  l.CreateFeature(f)
 out=[]; sizes=[]
 with l.GetArrowStreamAsNumPy(options=['MAX_FEATURES_IN_BATCH='+str(limit)]) as stream:
  for b in stream:
   a=b['k']; assert a.dtype==np.int64
   ids=b['OGC_FID']; sizes.append(len(ids))
   out.extend((int(i),None if masked else int(x)) for i,x,masked in zip(ids,a,np.ma.getmaskarray(a)))
 return out,sizes
def mutate(p,vals,mode,trust=True):
 assert set(dict(vals))==set(initial) and len(vals)==len(initial)
 kinds=list(meta.values())
 ds=ogr.GetDriverByName('GPKG').CreateDataSource(str(p))
 l=ds.CreateLayer('t',geom_type=ogr.wkbNone)
 l.CreateField(ogr.FieldDefn('k',ogr.OFTInteger64))
 for i,k in initial.items():
  f=ogr.Feature(l.GetLayerDefn());f.SetFID(i);f.SetField(0,k);l.CreateFeature(f)
 issues={}
 for ix,(fid,value) in enumerate(vals):
  f=l.GetFeature(fid)
  kind=meta[fid] if mode=='fid' else kinds[ix] if mode=='position' else ('clear' if value is None else 'literal')
  if kind in ('cached','literal') and value is None:
   issues[fid]='unavailable';continue
  if kind in ('await-cache','keep'):
   issues[fid]='needs-value' if kind=='await-cache' else 'kept';continue
  if kind=='clear':f.SetFieldNull(0)
  else:
   if kind=='cached' and (not trust or fid not in m['authoritative_cache_fids']):
    issues[fid]='untrusted-cache';continue
   f.SetField(0,value)
  assert l.SetFeature(f)==ogr.OGRERR_NONE
  issues[fid]='written'
 l=None;ds=None
 with sqlite3.connect(p) as db:res=dict(db.execute('select fid,k from t'))
 return dict(values=res,status=issues,drift=sorted(i for i in expected if res[i]!=expected[i]))
def main():
 out={}
 with tempfile.TemporaryDirectory() as p:
  for label,reverse,limit in [('sorted-five',False,5),('reversed-two',True,2)]:
   vals,sizes=read(sorted(meta,reverse=reverse),limit)
   # Native Memory Arrow sorts by FID here. Native consumer receives batches in reversed
   # delivery order by an explicit relay; data within each batch remains unchanged.
   if reverse:
    batches=[];j=0
    for size in sizes:batches.append(vals[j:j+size]);j+=size
    vals=[row for batch in reversed(batches) for row in batch]
   result={mode:mutate(pathlib.Path(p)/(label+'-'+mode+'.gpkg'),vals,mode) for mode in ('fid','position','payload')}
   assert not result['fid']['drift'] and result['fid']['status'][13]=='needs-value'
   result['untrusted-cache']=mutate(pathlib.Path(p)/(label+'-untrusted.gpkg'),vals,'fid',False)
   assert result['untrusted-cache']['drift']==[11] and result['untrusted-cache']['status'][11]=='untrusted-cache'
   assert result['payload']['drift']==[13,15]
   assert bool(result['position']['drift'])==reverse
   out[label]={'order':[i for i,_ in vals],'batch_sizes':sizes,'results':result}
 print(json.dumps({'versions':[gdal.VersionInfo(),np.__version__,sqlite3.sqlite_version],'replay':out},indent=2,sort_keys=True))
if __name__=='__main__':main()
