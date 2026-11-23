from os import environ
import json,pathlib,hashlib,sqlite3,math,runpy,tempfile,collections
from osgeo import gdal,ogr,osr
gdal.UseExceptions();osr.UseExceptions()
root=pathlib.Path(__file__).resolve().parent
wkb=runpy.run_path(str(root/'raw.py'))['wkb'];o=runpy.run_path(str(root/'oracle.py'))
exact=o['exact'];scoped=o['scoped'];classify=o['classify']
mf=root/'policy.json';policy=json.loads(mf.read_text())
def srs(n):
 s=osr.SpatialReference();s.ImportFromEPSG(n);s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
 return s
def polygon(ring):
 r=ogr.Geometry(ogr.wkbLinearRing)
 for x,y in ring:r.AddPoint_2D(x,y)
 g=ogr.Geometry(ogr.wkbPolygon);g.AddGeometry(r)
 return g
def support(ring):
 v=[('vertex',q) for q in ring[:-1]]
 for a,b in zip(ring,ring[1:]):
  mid=tuple((x+y)/2 for x,y in zip(exact(a),exact(b)))
  xy=tuple(map(float,mid))
  if exact(xy)==mid:
   v.append(('exact-midpoint',xy))
   for z in (-math.inf,math.inf):
    v.append(('one-ulp-midpoint',(xy[0],math.nextafter(xy[1],z))))
 return sorted(set(v))
def main():
 src=pathlib.Path(environ['OBSEQ_QGIS_WORLD_MAP']);sha=hashlib.sha256(src.read_bytes()).hexdigest();assert sha==policy['sha256']
 q=srs(4326);m=srs(3857);ab=osr.CoordinateTransformation(q,m);ba=osr.CoordinateTransformation(m,q)
 def rt(xy):
  x,y,_=ab.TransformPoint(*xy)
  x,y,_=ba.TransformPoint(x,y)
  assert math.isfinite(x) and math.isfinite(y)
  return x,y
 r=sqlite3.connect(src.as_uri()+'?mode=ro',uri=True)
 blob=r.execute('select fid,geom from countries where fid in (1,2,3,4,9,10) order by fid').fetchall();r.close()
 assert [i for i,_ in blob]==[1,2,3,4,9,10]
 ds=gdal.OpenEx(str(src),gdal.OF_VECTOR|gdal.OF_READONLY);layer=ds.GetLayerByName('countries')
 with tempfile.TemporaryDirectory() as tmp:
  fp=pathlib.Path(tmp)/'roundtrip.gpkg'
  dst=ogr.GetDriverByName('GPKG').CreateDataSource(str(fp));l=dst.CreateLayer('r',srs=q,geom_type=ogr.wkbPolygon)
  seen={};excluded=[]
  for i,b in blob:
   if b[:2]!=b'GP':
    excluded.append([i,'unqualified-wrapper']);continue
   raw=wkb(b)
   fit=next(((j,p[0]) for j,p in enumerate(raw)
           if scoped(p) and all(-180<x<180 and -80<=y<=80 for x,y in p[0])),None)
   if fit is None:excluded.append([i,'unqualified-component']);continue
   j,ring=fit
   f=layer.GetFeature(i);og=f.GetGeometryRef().GetGeometryRef(j).Clone()
   assert [(a,b) for a,b,*_ in og.GetGeometryRef(0).GetPoints()]==ring
   nr=list(map(rt,ring))
   if not scoped([nr]):excluded.append([i,'roundtrip-not-simple']);continue
   w=ogr.Feature(l.GetLayerDefn());w.SetFID(i);w.SetGeometry(polygon(nr))
   assert l.CreateFeature(w)==ogr.OGRERR_NONE
   seen[i]=(j,ring,nr,og)
  l=None;dst=None
  with sqlite3.connect(fp.as_uri()+'?mode=ro',uri=True) as raw:
   records={i:wkb(g)[0][0] for i,g in raw.execute('select fid,geom from r order by fid')}
  nd=ogr.Open(str(fp));assert nd.GetLayer().GetSpatialRef().GetAuthorityCode(None)=='4326'
  nr_layer=nd.GetLayer()
  assert set(records)==set(seen)
  transitions=collections.Counter();native_disagreements=collections.Counter();witnesses={};changed_coordinates=0;tests=0
  for i,(j,ring,target,og) in seen.items():
   assert records[i]==target
   stored=nr_layer.GetFeature(i);ng=stored.GetGeometryRef()
   assert [(a,b) for a,b,*_ in ng.GetGeometryRef(0).GetPoints()]==records[i]
   oldex=list(map(exact,ring));newex=list(map(exact,records[i]))
   changed_coordinates+=sum(a!=b for a,b in zip(ring[:-1],target[:-1]))
   for kind,p in support(ring):
    pn=rt(p)
    x=classify(oldex,p);y=classify(newex,pn)
    for rep,g,pt,w in [('original',og,p,x),('roundtrip',ng,pn,y)]:
     P=ogr.Geometry(ogr.wkbPoint);P.AddPoint_2D(*pt)
     C,I=bool(g.Contains(P)),bool(g.Intersects(P))
     if (C,I)!=(w=='interior',w!='exterior'):native_disagreements[rep]+=1
    key=f'{kind}:{x}->{y}';transitions[key]+=1;tests+=1
    if x!=y and key not in witnesses:witnesses[key]={'fid':i,'component':j,
      'original_hex':[v.hex() for v in p],'roundtrip_hex':[v.hex() for v in pn]}
    if kind=='exact-midpoint' and x!=y and 'source_edge_hex' not in witnesses[key]:
     a=next(k for k in range(len(oldex)-1) if o['line'](oldex[k],oldex[k+1],exact(p)))
     determinant=o['orient'](newex[a],newex[a+1],exact(pn))
     assert determinant
     witnesses[key].update(source_edge_hex=[[v.hex() for v in ring[k]] for k in (a,a+1)],
       roundtrip_edge_hex=[[v.hex() for v in target[k]] for k in (a,a+1)],
       roundtrip_edge_orientation=str(determinant))
  assert all(k.endswith('boundary->boundary') for k in transitions if k.startswith('vertex:'))
  assert sum(v for k,v in transitions.items() if k.startswith('exact-midpoint:boundary->') and not k.endswith('->boundary'))>0
  print(json.dumps({'artifact_sha256':sha,'policy_sha256':hashlib.sha256(mf.read_bytes()).hexdigest(),
   'gdal':gdal.VersionInfo(),'proj':[osr.GetPROJVersionMajor(),osr.GetPROJVersionMinor(),osr.GetPROJVersionMicro()],
   'admitted':{i:[j,len(ring)-1] for i,(j,ring,nr,_) in seen.items()},'excluded':excluded,
   'changed_vertices':changed_coordinates,'probes':tests,'cross_representation_categories':transitions,
   'predicate_mismatches_per_representation':native_disagreements,'example_transitions':witnesses},sort_keys=True,indent=2))
if __name__=='__main__':main()
