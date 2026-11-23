from osgeo import ogr,gdal
import tempfile,pathlib,json,itertools,random
gdal.UseExceptions()
def square(i,j):
 return ogr.CreateGeometryFromWkt(f'POLYGON (({i} {j}, {i+1} {j}, {i+1} {j+1}, {i} {j+1}, {i} {j}))')
def make(cells,reverse):
 pts=sorted(cells,reverse=reverse)
 geom=square(*pts[0])
 for ij in pts[1:]:geom=geom.Union(square(*ij))
 assert geom.GetArea()==len(cells)
 return geom
rng=random.Random(110)
universe=list(itertools.product(range(4),repeat=2))
sets=[{(0,0),(1,0),(1,1),(2,1)}, {(0,1),(1,1),(1,0),(2,0)}]
sets += [set(rng.sample(universe,rng.randint(1,len(universe)))) for _ in range(30)]
summary={'n_equal':0,'n_equal_wkb':0,'n_equal_structural':0,'n_diff_same_envelope_and_area':0,'pairs':0}
with tempfile.TemporaryDirectory() as t:
 p=str(pathlib.Path(t)/'geom.gpkg')
 d=ogr.GetDriverByName('GPKG').CreateDataSource(p)
 l=d.CreateLayer('t',geom_type=ogr.wkbUnknown)
 labels={}
 for cells,reverse in itertools.product(sets,(False,True)):
  f=ogr.Feature(l.GetLayerDefn())
  f.SetGeometry(make(cells,reverse));assert l.CreateFeature(f)==ogr.OGRERR_NONE
  labels[f.GetFID()]=cells
 l=None;d=None
 d=ogr.Open(p);l=d.GetLayer(0)
 shapes={}
 for f in l:shapes[f.GetFID()]=f.GetGeometryRef().Clone()
 assert shapes.keys()==labels.keys()
 for i,j in itertools.combinations(shapes,2):
  a,b=shapes[i],shapes[j]
  equal=labels[i]==labels[j]
  native=a.SymDifference(b).IsEmpty()
  assert native==equal
  # Envelope/area are cheap candidate signatures, not a final oracle.
  coarse=(a.GetEnvelope(),a.GetArea())==(b.GetEnvelope(),b.GetArea())
  wkb=bytes(a.ExportToWkb())==bytes(b.ExportToWkb())
  struct=a.Equals(b)
  assert (not equal or coarse) and (not wkb or equal) and (not struct or equal)
  summary['n_equal']+=equal;summary['n_equal_wkb']+=equal and wkb
  summary['n_equal_structural']+=equal and struct
  summary['n_diff_same_envelope_and_area']+=not equal and coarse
  summary['pairs']+=1
 assert summary['n_equal_wkb']<summary['n_equal'] and summary['n_diff_same_envelope_and_area']>0
line1=ogr.CreateGeometryFromWkt("LINESTRING (0 0, 1 0)")
line2=ogr.CreateGeometryFromWkt("LINESTRING (0 1, 1 1)")
sd=line1.SymDifference(line2)
assert sd.GetArea()==0 and not sd.IsEmpty()
print(json.dumps({'gdal':gdal.VersionInfo(),'geos':[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()],**summary},sort_keys=True,indent=2))
