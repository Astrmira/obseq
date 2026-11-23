from osgeo import ogr,gdal
from pathlib import Path
import hashlib,tempfile,sqlite3,sys,json
ogr.UseExceptions()
p=Path(sys.argv[1]);pin='5b0840c72e2ef9ac1bb211235cd6dd7170c0b400b72b472749490d93399c89cd'
with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==pin
s=ogr.Open(str(p),0);layer=s.GetLayerByName('gis_osm_roads_free')
gdef=layer.GetLayerDefn()
features=[]
for f in layer:
 n,r,v=(f.GetField(k) for k in ('name','ref','maxspeed'))
 if type(n) is str and n and type(r) is str and r and type(v) is int and v>0:
  features.append(f.Clone())
features.sort(key=lambda f:f.GetFID());features=features[:16]
assert len(features)==16 and len({f.GetFID() for f in features})==16
others=[f.GetName() for f in layer.schema if f.GetName() not in {'name','ref','maxspeed'}]
def snapshot(path):
 d=ogr.Open(str(path),0);l=d.GetLayerByName('roads')
 rows={f.GetFID():dict(a=tuple(f.GetField(x) for x in ('name','ref','maxspeed')),b=tuple(f.GetField(x) for x in others),geometry=bytes(f.GetGeometryRef().ExportToWkb())) for f in l}
 d=None;return rows
with tempfile.TemporaryDirectory() as td:
 b=Path(td);out={}
 for initial in ('nonempty','blank'):
  artifacts={}
  for arm in ('keep','mutant_clear'):
   file=b/(initial+'-'+arm+'.gpkg');d=ogr.GetDriverByName('GPKG').CreateDataSource(str(file))
   l=d.CreateLayer('roads',srs=layer.GetSpatialRef(),geom_type=layer.GetGeomType())
   for k in range(gdef.GetFieldCount()):assert l.CreateField(gdef.GetFieldDefn(k))==0
   defn=l.GetLayerDefn()
   assert l.StartTransaction()==0
   for old in features:
    f=ogr.Feature(defn);assert f.SetFrom(old)==0
    f.SetFID(old.GetFID())
    if initial=='blank':f.SetFieldNull(f.GetFieldIndex('name'))
    assert l.CreateFeature(f)==0
   assert l.CommitTransaction()==0
   mask=[defn.GetFieldIndex(x) for x in ('ref','maxspeed')]+([defn.GetFieldIndex('name')] if arm=='mutant_clear' else [])
   assert l.StartTransaction()==0
   for old in features:
    f=ogr.Feature(defn);f.SetFID(old.GetFID());f.SetFieldNull(mask[0]);f.SetField(mask[1],0)
    n=f.GetFieldIndex('name')
    if arm=='mutant_clear':f.SetFieldNull(n)
    assert f.IsFieldSet(n)==(arm=='mutant_clear')
    assert f.IsFieldNull(n)==(arm=='mutant_clear')
    assert l.UpdateFeature(f,mask,[],False)==0
   assert l.CommitTransaction()==0
   d=None
   artifacts[arm]=(file,snapshot(file),mask)
  a,ref,am=artifacts['keep'];c,mut,cm=artifacts['mutant_clear']
  assert set(ref)==set(mut)=={f.GetFID() for f in features}
  for orig in features:
   id=orig.GetFID();rv=ref[id];cv=mut[id]
   assert rv['a']==(orig.GetField('name') if initial=='nonempty' else None,None,0)
   assert cv['a']==(None,None,0)
   assert rv['geometry']==cv['geometry']==bytes(orig.GetGeometryRef().ExportToWkb())
   assert rv['b']==cv['b']==tuple(orig.GetField(x) for x in others)
  with sqlite3.connect(a) as db:
   db.execute('ATTACH DATABASE ? AS candidate',[str(c)])
   rows=db.execute("""SELECT count(*), count(l.name)=count(r.name),
              sum(NOT(l.name IS r.name AND l.ref IS r.ref AND l.maxspeed IS r.maxspeed)),
              sum(NOT(l.geom IS r.geom))
              FROM main.roads l JOIN candidate.roads r USING(fid)""").fetchone()
   verify=[db.execute(f'pragma {s}.integrity_check').fetchone()[0] for s in ('main','candidate')]
   self_count=[db.execute(f'select count(*) from {s}.roads').fetchone()[0] for s in ('main','candidate')]
   assert all(x=='ok' for x in verify)
   assert rows[0]==16 and self_count==[16,16] and rows[3]==0
   assert rows[2]==sum(ref[k]['a']!=mut[k]['a'] for k in ref)
   assert rows[2]==(16 if initial=='nonempty' else 0)
  out[initial]=dict(assign_mask_diff=am!=cm,matched_typed_value_differences=rows[2],native_geometry_blob_diff=rows[3],
        physical_integrity_all_pass=True,row_count_equal=True,nonnull_name_count_equal=bool(rows[1]),n=16)
print(json.dumps(dict(gdal=gdal.VersionInfo('--version'),sqlite=sqlite3.sqlite_version,source_sha256=pin,arms=out),indent=2,sort_keys=True))
