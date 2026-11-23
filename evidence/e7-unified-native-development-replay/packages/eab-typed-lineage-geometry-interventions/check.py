from osgeo import ogr,gdal
from pathlib import Path
import json,tempfile,hashlib
gdal.UseExceptions()
m=json.load(open('manifest.json'))
assert m['version']=='lineage-geometry-replay/v1'
assert len({r['id'] for r in m['rows']})==len(m['rows'])
assert all((r['intent']=='replace')==(r['authority']=='authoritative') for r in m['rows'])
def square(i,j):
 return ogr.CreateGeometryFromWkt(f'POLYGON (({i} {j}, {i+1} {j}, {i+1} {j+1}, {i} {j+1}, {i} {j}))')
def assembly(cells,reverse):
 pts=sorted(map(tuple,cells),reverse=reverse)
 g=square(*pts[0])
 for p in pts[1:]:g=g.Union(square(*p))
 assert g.IsValid() and g.GetArea()==len(cells)
 return g
def grid_observe(g):
 # Domain guard for this fixture. Centers distinguish any authored output candidates;
 # native canonical overlay also checks that the reconstructed grid union covers exactly g.
 pts={(i,j) for i in range(-1,4) for j in range(-1,4)
      if g.Contains(ogr.CreateGeometryFromWkt(f'POINT ({i+.5} {j+.5})'))}
 assert pts and g.SymDifference(assembly(pts,False)).IsEmpty()
 return pts
def sig(g):return g.GetEnvelope(),g.GetArea()
def run(path,bad_lineage,bad_set):
 d=ogr.GetDriverByName('GPKG').CreateDataSource(str(path))
 l=d.CreateLayer('assets',geom_type=ogr.wkbUnknown)
 for spec in m['rows']:
  f=ogr.Feature(l.GetLayerDefn());f.SetFID(spec['id'])
  f.SetGeometry(assembly(spec['before'],False));assert l.CreateFeature(f)==0
 observed_ops={}
 for spec in m['rows']:
  i=spec['id'];op=spec['intent'];chosen_authority=spec['authority'] if op=='replace' else None
  if bad_lineage and i==11:op='replace';chosen_authority='draft'
  if op=='replace':
   f=l.GetFeature(i)
   chosen=spec['proposal'] if not (bad_set and i==12) else m['rows'][2]['proposal']
   if bad_set and i==12:assert sig(assembly(chosen,True))==sig(assembly(spec['proposal'],False))
   f.SetGeometry(assembly(chosen,True));assert l.SetFeature(f)==0
  observed_ops[i]=(op,chosen_authority)
 l=None;d=None
 d=ogr.Open(str(path));l=d.GetLayer()
 snapshots={f.GetFID():f.GetGeometryRef().Clone() for f in l}
 expected_ids={s['id'] for s in m['rows']};assert set(snapshots)==expected_ids
 result=dict(intent=[],geometry=[],bytes_diag=[])
 for s in m['rows']:
  i=s['id'];e=s['proposal'] if s['intent']=='replace' else s['before']
  expected_set=set(map(tuple,e));g=snapshots[i]
  if observed_ops[i]!=(s['intent'],s['authority'] if s['intent']=='replace' else None):
   result['intent'].append(i)
  if grid_observe(g)!=expected_set:result['geometry'].append(i)
  if bytes(g.ExportToWkb())!=bytes(assembly(e,False).ExportToWkb()):result['bytes_diag'].append(i)
 return result
cases={}
with tempfile.TemporaryDirectory() as t:
 for arm,b,c in [('pass',False,False),('authority-only',True,False),('geometry-only',False,True),('both',True,True)]:
  r=run(Path(t)/(arm+'.gpkg'),b,c)
  assert r['intent']==([11] if b else []) and r['geometry']==([12] if c else [])
  assert r['bytes_diag']
  cases[arm]=r
print(json.dumps({'gdal':gdal.VersionInfo(),'geos':[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()],
 'manifest_sha256':hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
 'cases':cases},sort_keys=True,indent=2))
