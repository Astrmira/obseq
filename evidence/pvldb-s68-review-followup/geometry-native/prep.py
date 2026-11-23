"""Native GDAL extraction of stable consecutive ring wedges; no coordinate rewrites."""
import hashlib, math, struct, sys, json
from pathlib import Path
from osgeo import gdal

base,target=map(Path,sys.argv[1:])
pins={'osm/liechtenstein.gpkg':'5b0840c72e2ef9ac1bb211235cd6dd7170c0b400b72b472749490d93399c89cd',
      'ne/ne_110m_admin_0_countries.shp':'08e341606e8391e458c3f08deb312de664b56bfae376064c5aa0aee6681a5f55',
      'ne/ne_110m_admin_0_countries.shx':'8b0be2ad97dd484aee5c2ebc98697d5372e832b8ae58a35a661aeef6b985668d',
      'ne/ne_110m_admin_0_countries.dbf':'1fee677cd4e03b367876e03861eb10197e4022a846bf92060e0313432863785b'}
def digest(x):
    with x.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for p,v in pins.items():assert digest(base/p)==v
gdal.UseExceptions()
layers={'ne/ne_110m_admin_0_countries.shp':['ne_110m_admin_0_countries'],
        'osm/liechtenstein.gpkg':['gis_osm_buildings_a_free','gis_osm_landuse_a_free','gis_osm_natural_a_free','gis_osm_water_a_free']}
def rings(g):
    kind=g.GetGeometryName()
    if kind=='LINEARRING':
        yield g
    elif kind in ('POLYGON','MULTIPOLYGON'):
        for k in range(g.GetGeometryCount()):
            yield from rings(g.GetGeometryRef(k))
    else: raise ValueError(kind)
rows={};maxden=1
with target.open('wb') as f:
    for path,names in layers.items():
        ds=gdal.OpenEx(str(base/path),gdal.OF_VECTOR)
        for name in names:
            n=0
            for feature in ds.GetLayerByName(name):
                geom=feature.GetGeometryRef()
                if geom is None or geom.IsEmpty():continue
                for ring in rings(geom):
                    pts=[p[:2] for p in ring.GetPoints()]
                    assert len(pts)>=4 and pts[0]==pts[-1]
                    pts.pop()
                    for coord in (q for p in pts for q in p):
                        assert math.isfinite(coord) and abs(coord)<=1e8
                        maxden=max(maxden,coord.as_integer_ratio()[1])
                    for i in range(len(pts)):
                        a,b,c=pts[i-1],pts[i],pts[(i+1)%len(pts)]
                        f.write(struct.pack('<6d',*a,*b,*c))
                        n+=1
            rows[name]=n
assert maxden<=2**200
print(json.dumps(dict(gdal=gdal.VersionInfo('RELEASE_NAME'),source_sha256=pins,
                    wedges_by_layer=rows,max_coordinate_denominator=maxden,
                    native_wedges_sha256=digest(target)),sort_keys=True,indent=2))
