import tempfile, pathlib, sqlite3, json
from osgeo import gdal, ogr
import numpy as np
gdal.UseExceptions()
rows=[(0,2),(0,4),(1,2),(1,None),(2,None),(4,None)]
d=ogr.GetDriverByName("Memory").CreateDataSource("m")
l=d.CreateLayer("src",geom_type=ogr.wkbNone)
for k in ("g","k"):l.CreateField(ogr.FieldDefn(k,ogr.OFTInteger))
for group,k in rows:
 f=ogr.Feature(l.GetLayerDefn());f.SetField(0,group)
 if k is not None:f.SetField(1,k)
 elif group==4:f.SetFieldNull(1)
 l.CreateFeature(f)
ref=sqlite3.connect(":memory:")
ref.execute("create table src(g integer,k integer)");ref.executemany("insert into src values (?,?)",rows)
out=[]
with tempfile.TemporaryDirectory() as td:
 p=str(pathlib.Path(td)/"sink.gpkg")
 dst=ogr.GetDriverByName("GPKG").CreateDataSource(p)
 layer=dst.CreateLayer("sink",geom_type=ogr.wkbNone)
 for k in ("k_default","k_plain"):
  fld=ogr.FieldDefn(k,ogr.OFTReal)
  if k=="k_default":fld.SetDefault("99")
  layer.CreateField(fld)
 for dialect in ("OGRSQL","SQLITE"):
  for group in range(5):
   selected=[k for g,k in rows if g==group]
   present=[k for k in selected if k is not None]
   theoretical=(len(selected),len(present),sum(present) if present else None,
                sum(present)/len(present) if present else None)
   for expr,expect in zip(("COUNT(*)","COUNT(k)","SUM(k)","AVG(k)"),theoretical):
    q=f"select {expr} as val from src where g={group}"
    assert ref.execute(q).fetchone()[0]==expect
    result=d.ExecuteSQL(q,dialect=dialect)
    f=result.GetNextFeature()
    assert result.GetNextFeature() is None
    value=f.GetField(0)
    is_set=f.IsFieldSet(0)
    state="NULL" if f.IsFieldNull(0) else "VALUE" if is_set else "UNSET"
    assert value==expect
    assert state==("VALUE" if expect is not None else "UNSET" if dialect=="OGRSQL" else "NULL")
    result.ResetReading()
    with result.GetArrowStreamAsNumPy() as stream:
     a=next(iter(stream))["val"]
     assert len(a)==1
     masked=bool(np.ma.getmaskarray(a)[0])
     assert masked==(expect is None)
     if not masked:assert a[0]==expect
    d.ReleaseResultSet(result)
    for mode in ("state-copy","sql-null"):
     t=ogr.Feature(layer.GetLayerDefn())
     for i in range(2):
      if state=="VALUE":t.SetField(i,value)
      elif state=="NULL" or mode=="sql-null":t.SetFieldNull(i)
     layer.CreateFeature(t)
     out.append({"fid":t.GetFID(),"dialect":dialect,"group":group,"expr":expr,
                 "state":state,"projected":value,"masked":masked,"mode":mode})
 layer=None;dst=None
 with sqlite3.connect(p) as db:
  by_id={fid:(k,c) for fid,k,c in db.execute("select fid,k_default,k_plain from sink")}
 for row in out:
  exp=row["projected"]
  defaulted=row["state"]=="UNSET" and row["mode"]=="state-copy"
  readback=by_id[row["fid"]]; assert readback==(99.0 if defaulted else exp,exp)
  row.update(readback=readback,semantic_drift=defaulted)
print(json.dumps({"gdal":gdal.VersionInfo(),"numpy":np.__version__,"sqlite":sqlite3.sqlite_version,
 "materializations":len(out),"drift":sum(r["semantic_drift"] for r in out),"cases":out},sort_keys=True,indent=2))
