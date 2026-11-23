import ctypes as C,importlib.util,json,hashlib,sys
from pathlib import Path
p=Path(sys.argv[1])
P={'BLIND.json':'8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831','check.py':'f005d93a52f8a4b69f772ef5c81a1cdc469df4c93a695f2f8ac24b57292b1cb6'}
assert all(hashlib.sha256((p/k).read_bytes()).hexdigest()==h for k,h in P.items())
sp=importlib.util.spec_from_file_location('o',p/'check.py');o=importlib.util.module_from_spec(sp);sp.loader.exec_module(o)
D=C.CDLL('libgeos_c.so.1');V=C.c_void_p
def fn(name,ret,*types):
 f=getattr(D,name);f.argtypes=list(types);f.restype=ret;return f
ctx=fn('GEOS_init_r',V)();assert ctx
reader=fn('GEOSWKTReader_create_r',V,V)(ctx)
parse=fn('GEOSWKTReader_read_r',V,V,V,C.c_char_p)
owned=[]
def geom(w):
 z=parse(ctx,reader,w.encode('ascii'));assert z
 owned.append(z);return z
def pred(n,a,b):
 r=fn('GEOS'+n+'_r',C.c_byte,V,V,V)(ctx,a,b);assert r in (0,1)
 return bool(r)
def xy(p):assert len(p)==2 and all(type(x)is int for x in p);return ' '.join(map(str,p))
def seq(p):return ','.join(map(xy,p))
def line(p):return geom('LINESTRING('+seq(p)+')')
def point(p):return geom('POINT('+xy(p)+')')
def poly(*rings):return geom('POLYGON('+','.join('('+seq(r)+')' for r in rings)+')')
def rect(v):
 a,b,c,d=v;return poly([(a,b),(c,b),(c,d),(a,d),(a,b)])
out={}
try:
 for r in json.loads((p/'BLIND.json').read_text()):
  if r['class']!='F10':continue
  x=r['inputs'];i=int(r['case_id'][-2:]);k,v=next(iter(r['candidate'].items()))
  if i==1:
   a,b=poly(x['shell']),point(x['pt'])
   correct=pred('Contains',a,b); wrong=pred('Covers',a,b); m='contains_vs_covers'
  elif i==2:
   a,b=map(line,(x['a'],x['b']))
   correct=pred('Intersects',a,b); wrong=pred('Crosses',a,b); m='closed_intersection_vs_proper_crossing'
  elif i==3:
   a,b=map(rect,(x['a'],x['b']))
   intr=fn('GEOSIntersection_r',V,V,V,V)(ctx,a,b);assert intr;owned.append(intr)
   area=C.c_double();assert fn('GEOSArea_r',C.c_int,V,V,C.POINTER(C.c_double))(ctx,intr,C.byref(area))==1
   correct=area.value>0;wrong=pred('Intersects',a,b);m='positive_area_vs_touching'
  elif i==4:
   pnt=point(x['pt'])
   correct=pred('Covers',poly(x['shell'],x['hole']),pnt);wrong=pred('Covers',poly(x['shell']),pnt);m='hole_vs_shell_only'
  elif i==5:
   a,b=map(point,(x['p'],x['q']))
   dist=C.c_double();assert fn('GEOSDistance_r',C.c_int,V,V,V,C.POINTER(C.c_double))(ctx,a,b,C.byref(dist))==1
   correct=dist.value<=5;wrong=dist.value<5;m='inclusive_vs_exclusive_metric'
  elif i==6:
   a,b=map(line,(x['a'],x['b']))
   correct=pred('Intersects',a,b); env=[fn('GEOSEnvelope_r',V,V,V)(ctx,z) for z in (a,b)];assert all(env);owned.extend(env)
   wrong=pred('Intersects',*env);m='segments_vs_envelopes'
  else:raise AssertionError()
  yes=o.legal(dict(r,candidate={k:True}));no=o.legal(dict(r,candidate={k:False}))
  assert yes!=no and correct==yes and correct!=wrong,(i,yes,correct,wrong)
  orig=o.legal(r);assert orig==(correct==v)
  out[r['case_id']]=dict(native_contract=correct,native_counterfactual=wrong,independent_rational=bool(yes),candidate_admissible=orig,contrast=m)
finally:
 for g in reversed(owned):fn('GEOSGeom_destroy_r',None,V,V)(ctx,g)
 fn('GEOSWKTReader_destroy_r',None,V,V)(ctx,reader)
 fn('GEOS_finish_r',None,V)(ctx)
assert len(out)==6
print(json.dumps(dict(geos=fn('GEOSversion',C.c_char_p)().decode(),pins=P,results=out),indent=2,sort_keys=True))
