"""Called by check.py with a bounded original workbook and coordinates on stdin."""
import sys,json
from osgeo import gdal
gdal.UseExceptions(); gdal.PushErrorHandler('CPLQuietErrorHandler')
gdal.SetConfigOption('GDAL_DISABLE_READDIR_ON_OPEN','EMPTY_DIR')
d=gdal.OpenEx(sys.argv[1],gdal.OF_VECTOR|gdal.OF_READONLY,allowed_drivers=['XLSX'],open_options=['HEADERS=DISABLE','FIELD_TYPES=AUTO'])
out=[]
for sheet,row,col in json.load(sys.stdin):
 layer=d.GetLayerByName(sheet); feat=layer.GetFeature(row) if layer else None
 if not feat or col>feat.GetFieldCount() or not feat.IsFieldSetAndNotNull(col-1): out.append(['absent',None]);continue
 ix=col-1; field=feat.GetFieldDefnRef(ix); kind=field.GetTypeName()
 val=feat.GetFieldAsDateTime(ix) if kind in ('Date','DateTime') else None
 out.append([kind,('%04d-%02d-%02d'%tuple(val[:3])) if val else None])
print(json.dumps([gdal.VersionInfo('RELEASE_NAME'),out]))
