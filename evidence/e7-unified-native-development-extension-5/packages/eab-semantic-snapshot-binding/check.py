from osgeo import gdal,ogr
import numpy as np
import json,sys,sqlite3,hashlib,tempfile,pathlib
gdal.UseExceptions()
src=json.load(sys.stdin)
def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest()
def arrow(snap):
 d=ogr.GetDriverByName('Memory').CreateDataSource('batch')
 l=d.CreateLayer('updates',geom_type=ogr.wkbNone)
 l.CreateField(ogr.FieldDefn('k',ogr.OFTInteger64))
 for fid,op,v in snap['patch']:
  f=ogr.Feature(l.GetLayerDefn());f.SetFID(fid)
  if op=='CLEAR':f.SetFieldNull(0)
  elif op=='WRITE':f.SetField(0,v)
  l.CreateFeature(f)
 with l.GetArrowStreamAsNumPy() as it:
  b=next(iter(it));q=b['k'];assert q.dtype==np.int64
  return sorted((int(i),None if m else int(v)) for i,v,m in zip(b['OGC_FID'],q,np.ma.getmaskarray(q)))
def write(p,payload,patch):
 d=ogr.GetDriverByName('GPKG').CreateDataSource(str(p));l=d.CreateLayer('output',geom_type=ogr.wkbNone)
 l.CreateField(ogr.FieldDefn('k',ogr.OFTInteger64))
 for fid,old in ((11,41),(12,42),(13,43)):
  f=ogr.Feature(l.GetLayerDefn());f.SetFID(fid);f.SetField(0,old);l.CreateFeature(f)
 op={i:action for i,action,_ in patch}
 for fid,k in payload:
  if op[fid]=='KEEP':continue
  f=l.GetFeature(fid)
  if op[fid]=='CLEAR':f.SetFieldNull(0)
  else:f.SetField(0,k)
  assert l.SetFeature(f)==ogr.OGRERR_NONE
 l=None;d=None
 with sqlite3.connect(p) as db:return dict(db.execute('select fid,k from output'))
S=src['snapshots']; payloads={k:arrow(v) for k,v in S.items()}
A,B,C='A','B','B-repacked'
assert payloads[A]==payloads[B]==payloads[C]
assert all(s['semantic']==digest(['typed-patch/v1',sorted(s['patch'])]) for s in S.values())
cases={}
with tempfile.TemporaryDirectory() as t:
 for snapshot,side in ((A,A),(B,A),(B,B),(C,B)):
  p=payloads[snapshot]
  physical_binding=(digest(p)==digest(payloads[side]))
  semantic_binding=(S[snapshot]['semantic']==S[side]['semantic'])
  actual=write(pathlib.Path(t)/(snapshot+'-'+side+'.gpkg'),p,S[side]['patch'])
  expected={11:0,12:None,13:43} if snapshot==A else {11:0,12:42,13:None}
  drift=sorted(i for i in expected if actual[i]!=expected[i])
  assert physical_binding and bool(drift)==(not semantic_binding)
  assert drift==([12,13] if (snapshot,side)==(B,A) else [])
  cases[snapshot+'/'+side]=dict(payload_match=physical_binding,semantic_match=semantic_binding,drift=drift)
print(json.dumps({'openpyxl':src['version'],'gdal':gdal.VersionInfo(),'sqlite':sqlite3.sqlite_version,'results':cases},sort_keys=True,indent=2))
