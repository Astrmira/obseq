from osgeo import ogr
import sys,json
ogr.UseExceptions()
db=ogr.Open(sys.argv[1]); l=db.GetLayerByName('gis_osm_buildings_a_free')
f= l.GetLayerDefn().GetFieldDefn(l.GetLayerDefn().GetFieldIndex('osm_id'))
assert f.GetType()==ogr.OFTString
for r in l: print(json.dumps([r.GetFID(),r['osm_id']]))
