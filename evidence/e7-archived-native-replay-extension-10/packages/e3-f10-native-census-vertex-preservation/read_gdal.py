from osgeo import ogr,gdal
import json,sys
p='/vsizip/'+sys.argv[1]+'/cb_2024_us_state_20m.shp'
d=ogr.Open(p); assert d
l=d.GetLayer()
print(json.dumps(dict(gdal=gdal.VersionInfo('RELEASE_NAME'),srs=l.GetSpatialRef().GetAuthorityCode(None),count=l.GetFeatureCount(),wkbs=[bytes(f.GetGeometryRef().ExportToWkb()).hex() for f in l])))
