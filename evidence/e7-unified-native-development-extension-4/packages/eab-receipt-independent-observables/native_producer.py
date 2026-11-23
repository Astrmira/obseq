import json,sqlite3, tempfile, pathlib
from osgeo import gdal,ogr
gdal.UseExceptions()
s=json.load(open('manifest.json'))
wire=s
s=dict(wire, rows=[[int(i), None if k is None else int(k), int(c)] for i,k,c in wire["rows"]],
            patch=[[int(i), op, None if k is None else int(k)] for i,op,k in wire["patch"]],
            right=[[int(i), None if k is None else int(k)] for i,k in wire["right"]])
with tempfile.TemporaryDirectory() as d:
 out={}
 for mode in ('complete','sparse','normalize-all'):
  p=str(pathlib.Path(d)/(mode+'.gpkg'))
  ds=ogr.GetDriverByName('GPKG').CreateDataSource(p)
  l=ds.CreateLayer('t',geom_type=ogr.wkbNone)
  for k in ('k','c'):l.CreateField(ogr.FieldDefn(k,ogr.OFTInteger64))
  def put(f,i,v):
   if v is None:f.SetFieldNull(i)
   else:f.SetField(i,v)
  for fid,k,c in s['rows']:
   f=ogr.Feature(l.GetLayerDefn());f.SetFID(fid);put(f,0,k);put(f,1,c);l.CreateFeature(f)
  statuses=[]
  for fid,action,v in s['patch']:
   f=l.GetFeature(fid) if mode!='sparse' else ogr.Feature(l.GetLayerDefn())
   f.SetFID(fid)
   if action!='KEEP' or mode=='normalize-all':put(f,0,v)
   try:status=l.SetFeature(f)
   except RuntimeError as e:status=str(e)
   statuses.append([fid,status])
  l=None;ds=None
  with sqlite3.connect(p) as db:out[mode]={'rows':db.execute('select fid,k,c from t order by 1').fetchall(),'statuses':statuses}
 print(json.dumps({'gdal':gdal.VersionInfo(),'sqlite_writer_oracle':sqlite3.sqlite_version,'writes':out},sort_keys=True))
