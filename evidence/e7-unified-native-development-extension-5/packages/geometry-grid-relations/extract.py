from osgeo import ogr,gdal
import json,sys
ogr.UseExceptions()
p,s=sys.argv[1:]
d=ogr.Open(p); assert d
l=d.GetLayerByName(s); assert l
ref=l.GetSpatialRef()
assert ref.IsGeographic() and ref.GetAuthorityCode(None)in ('4326','CRS84')
assert ref.GetDataAxisToSRSAxisMapping() == ([2,1] if ref.GetAuthorityCode(None)=='4326' else [1,2])
for f in l:
    g=f.GetGeometryRef()
    assert g is not None and g.GetCoordinateDimension()==2
    print(json.dumps([f.GetFID(),bytes(g.ExportToWkb()).hex()]))
