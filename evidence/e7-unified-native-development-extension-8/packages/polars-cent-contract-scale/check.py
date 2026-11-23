import hashlib,json,sys
from collections import Counter
from decimal import Decimal
import duckdb,polars as p
from polars.testing import assert_frame_equal
dbpath=sys.argv[1]
d=duckdb.connect(dbpath,read_only=True)
assert duckdb.__version__=='1.4.3' and p.__version__=='2.1.0'
rows=d.execute('SELECT s_suppkey,s_acctbal FROM supplier ORDER BY s_suppkey').fetchall()
assert len(rows)==100000
assert d.execute("SELECT typeof(s_acctbal) FROM supplier LIMIT 1").fetchone()==('DECIMAL(15,2)',)
cent=Decimal('.01')
c=Counter()
r={}
digest=hashlib.sha256()
def frame(v,dtype=p.Float64):
    return p.DataFrame({'amount':[v]},schema={'amount':dtype})
def accepted(a,b,**kw):
    try: assert_frame_equal(a,b,**kw)
    except AssertionError: return False
    return True
for k,a in rows:
    b=a+cent
    ai=int(a*100); bi=int(b*100)
    assert (a*100,b*100)==(ai,bi) and bi==ai+1
    digest.update(f'{k}:{ai}\n'.encode())
    x,y=float(a),float(b)
    assert x!=y and round(x*100)==ai and round(y*100)==bi
    sign='negative' if ai<0 else 'nonnegative'
    c[sign+'_rows']+=1
    c['rows']+=1
    fa,fb=frame(x),frame(y)
    u,v=frame(a,p.Decimal(15,2)),frame(b,p.Decimal(15,2))
    assert u.item()==a and v.item()==b
    fwd,rev,exact,de=accepted(fa,fb),accepted(fb,fa),accepted(fa,fb,check_exact=True),accepted(u,v)
    assert not exact and not de
    for name,decision in [('default_forward',fwd),('default_reverse',rev),('exact_float',exact),('decimal_default',de)]:
        c[name+'_accepts']+=decision
        c[sign+'_'+name+'_accepts']+=decision
        if name.startswith('default_'):
            lk=name+'_'+sign+'_'+('accept' if decision else 'reject')
            r[lk]=[min(r.get(lk,[ai])[0],ai),max(r.get(lk,[ai,ai])[1],ai)]
    c['orientation_disagrees']+=fwd!=rev
    if k%997==0:
        assert accepted(fa,fa.clone()) and accepted(fa,fa.clone(),check_exact=True) and accepted(u,u.clone())
        c['unchanged_controls']+=1
# This validates native configured approximate equality is a relation, not
# a partition/equivalence suitable for exact money-valued hash keys.
assert digest.hexdigest()=="95d47618429bba7a8fff1e39a33d72543f89391f0ae8e27692f6eed9e61c4cb1"
a,b,h=map(frame,(1500.00,1500.01,1500.02))
assert accepted(a,b) and accepted(b,h) and not accepted(a,h)
print(json.dumps(dict(counts=dict(c),source_key_cents_sha256=digest.hexdigest(),
                     source_ranges_signed_cents=r,duckdb=duckdb.__version__,polars=p.__version__,
                     known_positive_nontransitivity=True,timings=None),indent=2,sort_keys=True))
