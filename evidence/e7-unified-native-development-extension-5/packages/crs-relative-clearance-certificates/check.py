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
 v=set()
 for a,b in zip(ring,ring[1:]):
  mid=tuple((x+y)/2 for x,y in zip(exact(a),exact(b)))
  p=tuple(map(float,mid))
  if exact(p)!=mid:continue
  v.add(('midpoint',p))
  x,y=p
  for n in (1,2,4,8,16,32,64,128,256):
   for sign in (-1,1):v.add(('offset',(x,y+sign*n*math.ulp(y))))
 xx,yy=zip(*ring);a,b=min(xx),max(xx);c,d=min(yy),max(yy)
 for i in (1,2,3):
  for j in (1,2,3):v.add(('bbox-grid',(a+(b-a)*i/4,c+(d-c)*j/4)))
 return sorted(v)
from fractions import Fraction as F
Z=(F(0),F(0))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dp(a,b):return sum(x*y for x,y in zip(a,b))
def norm(q):return dp(q,q)
def distance2(a,b):
 u=sub(b,a);v=norm(u)
 if not v:return norm(a)
 lam=-dp(a,u)/v
 if lam<=0:return norm(a)
 if lam>=1:return norm(b)
 return norm(a)-dp(a,u)**2/v
def hull(points):
 z=sorted(set(points))
 if len(z)<2:return z
 def side(xs):
  h=[]
  for q in xs:
   while len(h)>=2 and o['orient'](h[-2],h[-1],q)<=0:h.pop()
   h.append(q)
  return h[:-1]
 return side(z)+side(reversed(z))
def contains_origin(P):
 if len(P)==1:return P[0]==Z
 if len(P)==2:return o['line'](*P,Z)
 return all(o['orient'](a,b,Z)>=0 for a,b in zip(P,P[1:]+P[:1]))
def cert(old,new,p,pn):
 old=[sub(v,p) for v in old];new=[sub(v,pn) for v in new]
 radius=hull_miss=True
 for a,b,c,d in zip(old,old[1:],new,new[1:]):
  radius &= distance2(a,b)>max(norm(sub(c,a)),norm(sub(d,b)))
  hull_miss &= not contains_origin(hull((a,b,c,d)))
  if not (radius or hull_miss):break
 assert not radius or hull_miss
 return radius,hull_miss
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
  names=('point-only','edge-only','both')
  observed={k:collections.Counter() for k in names}
  probe_kinds=collections.Counter();native_mismatch=0
  contrasts={};separator=collections.Counter()
  for i,(j,ring,target,og) in seen.items():
   assert records[i]==target
   stored=nr_layer.GetFeature(i);ng=stored.GetGeometryRef()
   assert [(a,b) for a,b,*_ in ng.GetGeometryRef(0).GetPoints()]==records[i]
   oldex=list(map(exact,ring));newex=list(map(exact,records[i]))
   for kind,p in support(ring):
    pn=rt(p);x=classify(oldex,p);probe_kinds[kind]+=1
    x_prev={}
    for k,g,rr,u in [('baseline',og,oldex,p),('point-only',og,oldex,pn),
                    ('edge-only',ng,newex,p),('both',ng,newex,pn)]:
     label=classify(rr,u)
     P=ogr.Geometry(ogr.wkbPoint);P.AddPoint_2D(*u)
     pr=bool(g.Contains(P)),bool(g.Intersects(P))
     native_mismatch+=pr!=(label=='interior',label!='exterior')
     if k=='baseline':assert label==x;continue
     r,h=cert(oldex,rr,exact(p),exact(u));changed=x!=label
     assert not (h and changed)
     counts=observed[k];counts['tests']+=1
     counts['category_changed']+=changed;counts['radius_certified']+=r
     counts['hull_certified']+=h;counts['uncertified_but_unchanged']+=not h and not changed
     x_prev[k]=(r,h,changed,label)
    for name in ('point-only','edge-only'):
     solo=x_prev[name];joint=x_prev['both']
     if solo[3]!=joint[3]:
      separator[name]+=1
      if name not in contrasts:
       contrasts[name]={'fid':i,'point_hex':[a.hex() for a in p],
        'original_label':x,'isolated_label':solo[3],'joint_label':joint[3]}
  assert native_mismatch==0
  print(json.dumps({'artifact_sha256':sha,'policy_sha256':hashlib.sha256(mf.read_bytes()).hexdigest(),
   'gdal':gdal.VersionInfo(),'proj':[osr.GetPROJVersionMajor(),osr.GetPROJVersionMinor(),osr.GetPROJVersionMicro()],
   'admitted_components':len(seen),'excluded':excluded,'probe_kinds':probe_kinds,
   'summary':observed,'native_mismatches':native_mismatch,'isolated_vs_joint_label_differences':separator,'contrast_witnesses':contrasts},sort_keys=True,indent=2))

if __name__=='__main__':main()
