import ctypes as ct, ctypes.util, math,json,sys,hashlib
from pathlib import Path
from osgeo import gdal,ogr
P=Path(__file__).resolve().parent
for line in (P/'ADAPTER.lock').read_text().splitlines():
 h,name=line.split()
 assert hashlib.sha256((P/name).read_bytes()).hexdigest()==h

L=ct.CDLL(ctypes.util.find_library('geos_c'))
V=ct.c_void_p; I=ct.c_int; D=ct.c_double; S=ct.c_size_t
def bind(name,ret,*ats):
 f=getattr(L,name); f.restype=ret;f.argtypes=list(ats);return f
ctx=bind('GEOS_init_r',V)()
finish=bind('GEOS_finish_r',None,V)
new=bind('GEOSWKBReader_create_r',V,V)
dreader=bind('GEOSWKBReader_destroy_r',None,V,V)
reader=new(ctx)
read=bind('GEOSWKBReader_read_r',V,V,V,V,S)
destroy=bind('GEOSGeom_destroy_r',None,V,V)
kind=bind('GEOSGeomTypeId_r',I,V,V)
empty=bind('GEOSisEmpty_r',ct.c_byte,V,V)
dim=bind('GEOSGeom_getCoordinateDimension_r',I,V,V)
getx=bind('GEOSGeomGetX_r',I,V,V,ct.POINTER(D))
gety=bind('GEOSGeomGetY_r',I,V,V,ct.POINTER(D))
native_equals=bind('GEOSEquals_r',ct.c_byte,V,V,V)
geos_version=bind('GEOSversion',ct.c_char_p)().decode()
# Native geometry classification followed by a narrow strict structural envelope.
# Geometry family and coords originate in native decoders, not Python WKB unpack.
spans={'POINT':21,'LINESTRING':9,'MULTIPOINT':9}
def strict(b,t,xy,is_empty,dimension):
 if len(b)<5 or b[0] not in (0,1):return 'invalid endian/header span'
 # Reject EWKB/ISO dimensional tags and prefix/suffix ambiguity for these shapes.
 expected_type={'POINT':1,'LINESTRING':2,'MULTIPOINT':4}.get(t)
 wire_type=int.from_bytes(b[1:5],'little' if b[0] else 'big')
 if dimension!=2 or expected_type is None or expected_type!=wire_type:return 'unsupported or inconsistent OGC 2D type'
 if len(b)!=spans[t]:return 'wrong ticket span'
 if t=='POINT' and (is_empty or xy is None or not all(map(math.isfinite,xy))):return 'finite nonempty point required'
 if t!='POINT' and not is_empty:return 'only empty collection/line forms are in scope'
 return None

def geos_dec(p,b):
 if not p:return dict(native_parse='rejected',strict_reason='native reader rejected')
 t={0:'POINT',1:'LINESTRING',4:'MULTIPOINT'}.get(kind(ctx,p),'OTHER')
 e=empty(ctx,p)==1;q=None
 if t=='POINT' and not e:
  a=D(); d=D();assert getx(ctx,p,ct.byref(a)) and gety(ctx,p,ct.byref(d))
  q=[a.value,d.value]
 return dict(native_parse='accepted',geometry=t,xy=q,empty=e,dimension=dim(ctx,p),strict_reason=strict(b,t,q,e,dim(ctx,p)))

def gdal_dec(b):
 gdal.ErrorReset()
 gdal.PushErrorHandler('CPLQuietErrorHandler')
 try:
  try:p=ogr.CreateGeometryFromWkb(b)
  except RuntimeError:p=None
  if p is None:return dict(native_parse='rejected',strict_reason='native reader rejected',native_issue=gdal.GetLastErrorMsg())
  t=p.GetGeometryName(); e=bool(p.IsEmpty());d=p.GetCoordinateDimension()
  q=[p.GetX(),p.GetY()] if t=='POINT' and not e else None
  return dict(native_parse='accepted',geometry=t,xy=q,empty=e,dimension=d,strict_reason=strict(b,t,q,e,d))
 finally:gdal.PopErrorHandler()

def same(q,r,blind=False):
 if q['strict_reason'] is not None or r['strict_reason'] is not None:return False
 return sorted(q['xy'] or [])==sorted(r['xy'] or []) if blind else (q['geometry'],q['xy'])==(r['geometry'],r['xy'])
out=[]
for r in json.loads((P/'../e7-scored/BLIND.json').read_text()):
 if r['subtype']!='equivalent WKB':continue
 a,b=map(bytes.fromhex,(r['inputs']['referenceHex'],r['candidate']['hex']))
 p,q=[read(ctx,reader,ct.create_string_buffer(x),len(x)) for x in (a,b)]
 try:
  g1,g2=geos_dec(p,a),geos_dec(q,b)
  o1,o2=gdal_dec(a),gdal_dec(b)
  equality=native_equals(ctx,p,q) if p and q else None
  out.append(dict(case_id=r['case_id'],input_bytes=[len(a),len(b)],gdal=[o1,o2],geos=[g1,g2],
                 gdal_typed=same(o1,o2),geos_typed=same(g1,g2),
                 byte_equality=a==b,gdal_typeblind_unordered=same(o1,o2,True),
                 geos_topology=bool(equality) if equality in (0,1) else None))
 finally:
  for i in (p,q):
   if i:destroy(ctx,i)
dreader(ctx,reader);finish(ctx)
assert len(out)==6
print(json.dumps(dict(engines={'gdal':gdal.VersionInfo('RELEASE_NAME'),'geos':geos_version},rows=out),indent=2))
