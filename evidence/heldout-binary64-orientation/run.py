from pathlib import Path
import ctypes, hashlib, json, math, sys
from decimal import Decimal
from fractions import Fraction
source=Path(sys.argv[1])
lib=ctypes.CDLL('libgeos_c.so.1')
lib.GEOS_init_r.restype=ctypes.c_void_p
lib.GEOS_finish_r.argtypes=[ctypes.c_void_p]
lib.GEOSversion.restype=ctypes.c_char_p
ctx=lib.GEOS_init_r()
assert ctx
go=lib.GEOSOrientationIndex_r
go.argtypes=[ctypes.c_void_p]+[ctypes.c_double]*6
go.restype=ctypes.c_int

def s(x):return (x>0)-(x<0)
def determinant(vals):
    a,b,c,d,e,f=vals
    return (a-e)*(d-f)-(b-f)*(c-e)
def align(x):
    ratios=[y.as_integer_ratio() for y in x]
    X=max(ratios[j][1] for j in (0,2,4))
    Y=max(ratios[j][1] for j in (1,3,5))
    return [p*((Y if j&1 else X)//q) for j,(p,q) in enumerate(ratios)]
def adaptive(x):
    a,b,c,d,e,f=x
    left=(a-e)*(d-f);right=(b-f)*(c-e)
    u=2.0**-53
    z=left-right
    if abs(z)>(3.0+16.0*u)*u*(abs(left)+abs(right)):
        return s(z),False
    return s(determinant(align(x))),True
R=[]
for c in json.loads(source.read_text(encoding='utf8')):
    raw=c['coords']
    assert len(raw)==6 and all(type(a) is str for a in raw)
    x=tuple(float(v) for v in raw)
    assert all(math.isfinite(v) and abs(v)<=1e8 and v.as_integer_ratio()[1]<=2**200 for v in x)
    y=go(ctx,*x)
    assert y in (-1,0,1)
    q,f=adaptive(x)
    R.append(dict(id=c['id'],stock_geos=y,plain_float=s(determinant(x)),certified=q,fallback=f,
                 decimal_contract=s(determinant(tuple(Fraction(Decimal(v)) for v in raw)))))
lib.GEOS_finish_r(ctx)
assert len(R)==len({r['id'] for r in R})==24
print(json.dumps(dict(geos=lib.GEOSversion().decode(),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),predictions=R),sort_keys=True,indent=2))
