"""Native GPKG replay; independently derive preservation projection before effects."""
from osgeo import ogr,gdal
from pathlib import Path
import json,tempfile,sqlite3,hashlib,itertools
gdal.UseExceptions()
base=[(11,41,101),(12,42,102),(13,43,103)]
patch={11:('WRITE',0),12:('CLEAR',None),13:('KEEP',None)}
def remain(rows):
 return [(i,k if patch[i][0]=='KEEP' else '<overwritten>',c) for i,k,c in rows]
def hash(x): return hashlib.sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest()
def oracle(rows):
 return [(i,k if patch[i][0]=='KEEP' else patch[i][1],c) for i,k,c in rows]
def run(path,rows):
 ds=ogr.GetDriverByName('GPKG').CreateDataSource(str(path))
 layer=ds.CreateLayer('result',geom_type=ogr.wkbNone)
 for field in ('k','c'):layer.CreateField(ogr.FieldDefn(field,ogr.OFTInteger64))
 for i,k,c in rows:
  f=ogr.Feature(layer.GetLayerDefn());f.SetFID(i)
  if k is None:f.SetFieldNull(0)
  else:f.SetField(0,k)
  f.SetField(1,c);assert layer.CreateFeature(f)==ogr.OGRERR_NONE
 for i,(op,v) in patch.items():
  if op=='KEEP':continue
  f=layer.GetFeature(i)
  if op=='CLEAR':f.SetFieldNull(0)
  else:f.SetField(0,v)
  assert layer.SetFeature(f)==ogr.OGRERR_NONE
 layer=None;ds=None
 with sqlite3.connect(path) as db:return db.execute('select fid,k,c from result order by fid').fetchall()
variants={'baseline':base,'overwritten-only':[(11,None,101),(12,999,102),base[2]],
          'preserved-value':[base[0],base[1],(13,9,103)],
          'protected-control':[(11,41,801),*base[1:]]}
theorem_controls=0
# Verify the projection by an independently written coordinatewise patch oracle.
for intents in itertools.product(('WRITE','KEEP','CLEAR'),repeat=3):
 for vals in itertools.product((None,0,9),repeat=3):
  source=[(i,k,c) for (i,_,c),k in zip(base,vals)]
  def model(rows):
   return [(i, k if op=='KEEP' else 0 if op=='WRITE' else None, c)
           for (i,k,c),op in zip(rows,intents)]
  for target in [base,*variants.values()]:
   keep_equal=all((b==a if op=='KEEP' else b[0]==a[0] and b[2]==a[2])
                  for b,a,op in zip(source,target,intents))
   assert (model(source)==model(target))==keep_equal
   theorem_controls+=1
out={}
with tempfile.TemporaryDirectory() as t:
 for name,dst in variants.items():
  actual=run(Path(t)/(name+'.gpkg'),dst)
  assert oracle(dst)==actual
  observed=oracle(base)==actual
  projected=hash(remain(dst))==hash(remain(base))
  full=hash(dst)==hash(base)
  assert projected==observed
  out[name]={'same_final':observed,'safe_scoped_reuse':projected,'whole_state_accepts':full,'rows':actual}
print(json.dumps({'gdal':gdal.VersionInfo(),'sqlite':sqlite3.sqlite_version,'cases':out,'exact_projection_controls':theorem_controls},sort_keys=True,indent=2))
