from collections import Counter,defaultdict
from itertools import islice
from pathlib import Path
import csv,hashlib,json,sys
import duckdb
import pandas as pd
import datacompy

p=Path(sys.argv[1])
with p.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()=='29205553b85cee0eb36a52b0d16ed1a8067ba066ac28d7c2a995a5db371f7061'
def intn(x):return int(x) if x else None
with p.open(newline='') as f:
    r=csv.reader(f)
    assert next(r)==['id1','id2','id3','id4','id5','id6','v1']
    panel=tuple(islice(((int(a),intn(b),intn(c)) for a,b,c,*_ in r if a),2048))
assert len(panel)==2048
groups=defaultdict(list)
for x in panel:groups[x[0]].append(x)
assert 2<=len(groups)<2048
grp=next(g for g,v in groups.items() if len(v)>4)
block=groups[grp]
a,b=next((x,y) for x in block for y in block if x[1]!=y[1] and x[2]!=y[2])
swap=list(panel)
swap[panel.index(a)]=(a[0],a[1],b[2])
swap[panel.index(b)]=(b[0],b[1],a[2])
dupe=panel+(a,b)
controls=[
 ('unchanged',panel,panel),
 ('global_reverse',panel,panel[::-1]),
 ('per_group_rotate',panel,tuple(x for xs in groups.values() for x in (xs[1:]+xs[:1]))),
 ('duplicate_bag_reorder',dupe,dupe[::-1]),
 ('same_key_payload_association',panel,tuple(swap)),
 ('replace_duplicate_same_count',dupe,panel+(a,a)),
 ('missing_one_duplicate',dupe,panel+(a,)),
]
assert Counter((g,y) for g,x,y in panel)==Counter((g,y) for g,x,y in swap)
db=duckdb.connect(config={'threads':1})
def exact_native(l,r):
    for name,x in [('l',l),('r',r)]:
        db.execute(f'CREATE OR REPLACE TABLE {name}(g BIGINT,a BIGINT,b BIGINT)')
        db.executemany(f'insert into {name} values (?,?,?)',x)
    diff=[db.execute(f'select count(*) from (select * from {x} except all select * from {y})').fetchone()[0]
          for x,y in [('l','r'),('r','l')]]
    return diff
def frame(rows):
    f=pd.DataFrame(rows,columns=['g','a','b'])
    d={k:pd.array([r[i] for r in rows],dtype='Int64') for i,k in enumerate(['g','a','b'])}
    return pd.DataFrame(d)
def comp(a,b,canon=False):
    aa,bb=frame(a),frame(b)
    if canon:
        aa,bb=(z.sort_values(['g','a','b'],kind='stable',na_position='first',ignore_index=True) for z in (aa,bb))
    ob=datacompy.Compare(aa,bb,join_columns=['g'])
    return bool(ob.matches())
out={}
for name,l,r in controls:
    ca,cb=Counter(l),Counter(r)
    oracle=ca==cb
    n=exact_native(l,r)
    assert n==[sum((ca-cb).values()),sum((cb-ca).values())]
    out[name]=dict(exact_bag=oracle,stock=comp(l,r),canonicalized=comp(l,r,True),exact_native_except_all=n)
assert len(out)==7
assert all(v['canonicalized']==v['exact_bag'] for v in out.values())
assert all(out[k]['exact_bag'] and not out[k]['stock'] for k in
           ('global_reverse','per_group_rotate','duplicate_bag_reorder'))
print(json.dumps(dict(controls=out,panel_rows=len(panel),groups=len(groups),
    source_sha256="29205553b85cee0eb36a52b0d16ed1a8067ba066ac28d7c2a995a5db371f7061",
    pandas=pd.__version__,datacompy=datacompy.__version__,duckdb=duckdb.__version__),sort_keys=True,indent=2))
