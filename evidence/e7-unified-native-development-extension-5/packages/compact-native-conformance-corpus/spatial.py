from osgeo import gdal,ogr
import tempfile,pathlib,json,sys
gdal.UseExceptions()
def geom(r):
 a,b,c,d=r
 return ogr.CreateGeometryFromWkt(f'POLYGON (({a} {b},{c} {b},{c} {d},{a} {d},{a} {b}))')
case,mode=json.load(sys.stdin)
with tempfile.TemporaryDirectory() as t:
 p=str(pathlib.Path(t)/'test.gpkg')
 d=ogr.GetDriverByName('GPKG').CreateDataSource(p)
 l=d.CreateLayer('src',geom_type=ogr.wkbPolygon)
 l.CreateField(ogr.FieldDefn('score',ogr.OFTInteger64))
 region=geom(case['region'] if mode=='correct' else case['old'])
 for i,r in case['inputs']:
  g=geom(r);f=ogr.Feature(l.GetLayerDefn());f.SetFID(i);f.SetGeometry(g)
  v=g.Intersection(region).GetArea();assert int(v)==v
  f.SetField(0,int(v));assert l.CreateFeature(f)==0
 l=None;d=None
 d=ogr.Open(p);l=d.GetLayer()
 inputs=[];scores=[]
 for f in l:
  g=f.GetGeometryRef()
  a,c,b,e=g.GetEnvelope();r=list(map(int,(a,b,c,e)))
  assert [a,b,c,e]==r and g.SymDifference(geom(r)).IsEmpty()
  i=f.GetFID();inputs.append([i,r]);scores.append([i,f.GetField(0)])
 print(json.dumps(dict(input=sorted(inputs),scores=sorted(scores),
  ids=sorted(i for i,v in scores if v>=case['threshold']),
  versions={'gdal':gdal.VersionInfo(),'geos':[ogr.GetGEOSVersionMajor(),ogr.GetGEOSVersionMinor(),ogr.GetGEOSVersionMicro()]}),sort_keys=True))
