import sys,json
from osgeo import gdal
import numpy as np
gdal.UseExceptions();gdal.PushErrorHandler('CPLQuietErrorHandler')
p,v=sys.argv[1:]
d=gdal.Open(f'NETCDF:{p}:{v}');b=d.GetRasterBand(1)
x=b.ReadAsArray()
support=b.GetMaskBand().ReadAsArray()!=0
m=b.GetMetadata()
fill=int(b.GetNoDataValue())
assert int(m['_FillValue'])==fill and np.array_equal(support,x!=fill)
assert b.GetMaskFlags()==gdal.GMF_NODATA
if 'valid_range' in m:l,h=map(int,m['valid_range'][1:-1].split(','))
else:l,h=int(m['valid_min']),int(m['valid_max'])
assert l<=h and not l<=fill<=h
u=(x.dtype.kind,x.dtype.itemsize)
assert u==(('u',1) if v=='BCM' else ('i',2))
print(json.dumps(dict(shape=x.shape,n=x.size,missing=int((~support).sum()),fill=fill,lo=l,hi=h,
             observed_range_invalid=int((support&((x<l)|(x>h))).sum()),
             native=gdal.VersionInfo('--version'),decoded_dtype=str(x.dtype))),flush=True)
sys.stdout.buffer.write(x.astype('<i2',copy=False).tobytes(order='C'))
