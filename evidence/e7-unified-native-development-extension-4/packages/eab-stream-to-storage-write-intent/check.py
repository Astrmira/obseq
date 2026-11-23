from osgeo import gdal,ogr
import sqlite3,json,tempfile,pathlib,sys
gdal.UseExceptions()
receipt=json.load(sys.stdin)
initial={11:41,12:42,13:43,14:44}
expected_intent={11:"WRITE",12:"CLEAR",13:"UNCACHED",14:"WRITE"}
expected_value={11:4,12:None,13:43,14:0}
out={}
with tempfile.TemporaryDirectory() as tmp:
 for arm,rows in receipt['source'].items():
  name=str(pathlib.Path(tmp)/(arm+'.gpkg'))
  ds=ogr.GetDriverByName('GPKG').CreateDataSource(name)
  l=ds.CreateLayer('result',geom_type=ogr.wkbNone)
  for k in ('value','control'):l.CreateField(ogr.FieldDefn(k,ogr.OFTInteger64))
  for i,k in initial.items():
   f=ogr.Feature(l.GetLayerDefn());f.SetFID(i);f.SetField(0,k);f.SetField(1,i+100);l.CreateFeature(f)
  status={}
  for fid,op,value in rows:
   i=int(fid);assert i not in status
   if op=='UNCACHED':status[i]=[op,'needs-value'];continue
   f=l.GetFeature(i)
   if op=='CLEAR':f.SetFieldNull(0)
   else:assert op=='WRITE';f.SetField(0,int(value))
   assert l.SetFeature(f)==ogr.OGRERR_NONE
   status[i]=[op,'success']
  l=None;ds=None
  with sqlite3.connect(name) as d:r={i:(value,ctl) for i,value,ctl in d.execute('select fid,value,control from result')}
  assert set(r)==set(initial) and all(ctl==i+100 for i,(_,ctl) in r.items())
  value_drift=[i for i,(v,_) in r.items() if v!=expected_value[i]]
  intent_drift=[i for i in initial if status.get(i,[None])[0]!=expected_intent[i]]
  oracle={'default':[13,14],'reset_only':[13],'contract':[]}[arm]
  assert value_drift==intent_drift==oracle
  out[arm]={'value_drift':value_drift,'intent_drift':intent_drift,'status':status,'persisted':r}
print(json.dumps({'openpyxl':receipt['openpyxl'],'gdal':gdal.VersionInfo(),'sqlite':sqlite3.sqlite_version,'results':out},sort_keys=True,indent=2))
