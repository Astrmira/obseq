"""Audit the stock projected relation, not source-occurrence IDs."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
import csv, hashlib, json, re, sys
import duckdb

root, stock=map(Path,sys.argv[1:])
L,R='J1_1e7_NA_5_0.csv','J1_1e7_1e4_5_0.csv'
pins={L:'29205553b85cee0eb36a52b0d16ed1a8067ba066ac28d7c2a995a5db371f7061',
      R:'f2e8ce2fd70647d1930a6401b3ca4786f361f85b7456ff7ddcee90a5e721fce1',
      'J1_1e7_1e1_5_0.csv':'035dd56bbe5a599248fa069566887d92d6998ed7c1f9a2a8822e8773edadcd82',
      'J1_1e7_1e7_5_0.csv':'6ee50b2d93e75ee813e03b33d05aca75395a2d708abd4530ab3d285bdcd95fef'}
sql=stock.read_text()
assert hashlib.sha256(sql.encode()).hexdigest()=='ac6b9d4ebe184bc699899a26564ac70871b1c719bf1338232a86b36232c4a66f'
bodies=re.findall(r'CREATE %s TABLE ans AS (SELECT [^"\n]+)',sql)
assert len(bodies)==10 and bodies[4]==bodies[5] and 'LEFT JOIN' in bodies[4]
Q=bodies[4]
for f,h in pins.items():
    with (root/f).open('rb') as fobj: assert hashlib.file_digest(fobj,'sha256').hexdigest()==h

P=2**89-1
ll=4
for _ in range(87): ll=(ll*ll-2)%P
assert ll==0  # Lucas-Lehmer, prime exponent 89
a,b,c,d=13,11_002,11_000_002,100_000_002
assert a*b*c*d<P and a*b*d<P and a*a*b*b*c*d*d<2**127
def num(v,n):
    if not v: return 0
    x=int(v)+1
    assert 1<=x<n
    return x
def mic(v):
    if not v: return 0
    if 'e' in v.lower():
        exact=Decimal(v)*1_000_000
        assert exact==int(exact) and 0<=exact<d-1
        return int(exact)+1
    i,_,f=v.partition('.')
    assert len(f)<=6
    x=1+int(i)*1_000_000+int(f.ljust(6,'0'))
    assert 1<=x<d
    return x
def same(key,render):
    assert render==('id'+key if key else '')
right={}
with (root/R).open(newline='') as f:
    it=csv.reader(f); assert next(it)==['id1','id2','id4','id5','v2']
    for i,k,s,t,v in it:
        assert k and k not in right
        same(i,s);same(k,t)
        right[k]=((num(i,a)*b+num(k,b))*d+mic(v), mic(v)-1 if v else None)
assert len(right)==10_000
left=defaultdict(int)
w=[]
with (root/L).open(newline='') as f:
    it=csv.reader(f); assert next(it)==['id1','id2','id3','id4','id5','id6','v1']
    for count,(i,k,j,s,t,u,v) in enumerate(it,1):
        same(i,s);same(k,t);same(j,u)
        lc=((num(i,a)*b+num(k,b))*c+num(j,c))*d+mic(v)
        left[k]+=lc
        if k in right and not j and len(w)<2 and right[k][1] is not None and all(m!=right[k][1] for _,_,m in w):
            w.append((lc,right[k][0],right[k][1]))
assert count==10_000_000 and len(w)==2
(u,ru,mu),(v,rv,mv)=w
expected=sum(value*right.get(k,(0,None))[0] for k,value in left.items())%P
cross_expected=(u-v)*(rv-ru)%P
payload_expected=(u-v)*(mv-mu)%P
assert cross_expected and payload_expected

con=duckdb.connect(config={'threads':1,'memory_limit':'950MB','max_temp_directory_size':'0B'})
def quote(t): return "'"+str(t).replace("'","''")+"'"
ls="{'id1':'BIGINT','id2':'BIGINT','id3':'BIGINT','id4':'VARCHAR','id5':'VARCHAR','id6':'VARCHAR','v1':'DOUBLE'}"
rs="{'id1':'BIGINT','id2':'BIGINT','id4':'VARCHAR','id5':'VARCHAR','v2':'DOUBLE'}"
ss="{'id1':'BIGINT','id4':'VARCHAR','v2':'DOUBLE'}"
for name,fn,sc in [('x',L,ls),('medium',R,rs),('small','J1_1e7_1e1_5_0.csv',ss),('big','J1_1e7_1e7_5_0.csv',ls.replace('v1','v2'))]:
    con.execute(f"CREATE VIEW {name}_csv AS SELECT * FROM read_csv({quote(root/fn)}, header=true, columns={sc})")
for key,expr in re.findall(r'(id[45])_enum_statement = "([^"]+)"',sql):
    con.execute(f'CREATE TYPE {key}ENUM AS ENUM ({expr})')
for name,cols in [('x','id1 id2 id3 id4 id5 id6 v1'),('medium','id1 id2 id4 id5 v2')]:
    projection=','.join(f'{x}::{x}ENUM AS {x}' if x in ('id4','id5') else x for x in cols.split())
    con.execute(f'CREATE VIEW {name} AS SELECT {projection} FROM {name}_csv')
names=[r[0] for r in con.execute('DESCRIBE '+Q).fetchall()]
assert names==['id1','id2','id3','id4','id5','id6','v1','medium_id1','medium_id4','medium_id5','v2']
def I(col):return f'coalesce({col}::HUGEINT+1,0)'
def D(col):return f'coalesce(({col}::DECIMAL(18,6)*1000000)::HUGEINT+1,0)'
bits=[
 'id1 IS NULL OR id1 BETWEEN 0 AND 11','id2 IS NULL OR id2 BETWEEN 0 AND 11000',
 'id3 IS NULL OR id3 BETWEEN 0 AND 11000000','medium_id1 IS NULL OR medium_id1 BETWEEN 0 AND 11',
 "CAST(id4 AS VARCHAR) IS NOT DISTINCT FROM 'id'||CAST(id1 AS VARCHAR)",
 "CAST(id5 AS VARCHAR) IS NOT DISTINCT FROM 'id'||CAST(id2 AS VARCHAR)",
 "CAST(id6 AS VARCHAR) IS NOT DISTINCT FROM 'id'||CAST(id3 AS VARCHAR)",
 "CAST(medium_id4 AS VARCHAR) IS NOT DISTINCT FROM 'id'||CAST(medium_id1 AS VARCHAR)",
 "medium_id5 IS NULL OR CAST(medium_id5 AS VARCHAR)='id'||CAST(substr(CAST(medium_id5 AS VARCHAR),3)::BIGINT AS VARCHAR)",
 "medium_id5 IS NULL OR substr(CAST(medium_id5 AS VARCHAR),3)::BIGINT BETWEEN 0 AND 11000",
 *[f'({k} IS NULL OR (isfinite({k}) AND {k} BETWEEN 0 AND 100 AND {k}={k}::DECIMAL(18,6)::DOUBLE))' for k in ('v1','v2')]
]
predicate=' AND '.join(f'({x})' for x in bits)
lcode=f'(({I("id1")}*{b}+{I("id2")})*{c}+{I("id3")})*{d}+{D("v1")}'
rcode=f'({I("medium_id1")}*{b}+{I("substr(CAST(medium_id5 AS VARCHAR),3)")})*{d}+{D("v2")}'
row=con.execute(f'''
WITH stock AS ({Q}), typed AS (
 SELECT ({lcode}) lc, ({rcode}) rc, {I("id3")} sc, {D("v1")} v1id,{D("v2")} v2id,
   ({predicate}) AS admissible FROM stock
), candidates AS (
 SELECT *, CASE WHEN lc={u} THEN {rv} WHEN lc={v} THEN {ru} ELSE rc END swapped,
           CASE WHEN lc={u} THEN rc+({mv-mu}) WHEN lc={v} THEN rc+({mu-mv}) ELSE rc END swapped_v,
           CASE WHEN lc={u} THEN {mv+1} WHEN lc={v} THEN {mu+1} ELSE v2id END swapped_v2id
 FROM typed
)
SELECT count(*),count_if(admissible IS DISTINCT FROM true),count_if(lc={u}),count_if(lc={v}),
       sum((lc*rc)%{P})%{P},sum((lc*swapped)%{P})%{P},sum((lc*swapped_v)%{P})%{P},
       sum((sc*rc)%{P})%{P},sum((sc*swapped)%{P})%{P},sum(v2id),sum(swapped_v2id),
       max(rc) FILTER(WHERE lc={u}), max(rc) FILTER(WHERE lc={v}),
       max(v2id) FILTER(WHERE lc={u}), max(v2id) FILTER(WHERE lc={v}) FROM candidates
''').fetchone()
assert row[:4]==(10_000_000,0,1,1)
assert row[4]==expected and (row[5]-row[4])%P==cross_expected and (row[6]-row[4])%P==payload_expected
assert row[7]==row[8] and row[9]==row[10] and row[11:]==(ru,rv,mu+1,mv+1)
# Larger faults are not covered: in a 3x3 grid, row/column marginals and all
# mixed first moments can stay fixed. In one scalar channel use an arithmetic
# sequence of left codes and a (1,-2,1) contrast against two right codes.
delta=[[a*b for b in (1,-1)] for a in (1,-2,1)]
assert any(any(r) for r in delta) and all(sum(r)==0 for r in delta)
assert all(sum(col)==0 for col in zip(*delta))
assert sum(i*j*delta[i-1][j-1] for i in (1,2,3) for j in (1,2))==0
print(json.dumps(dict(duckdb=duckdb.__version__,stock_projection_fields=names,rows=row[0],
    admitted_rows=row[0]-row[1],left_groups=len(left),sha256=pins,modulus=P,
    reference_mixed_moment=expected, clean_mixed_moment=row[4],
    whole_right_swap_mixed_moment=row[5],payload_only_swap_mixed_moment=row[6],
    whole_right_swap_delta=cross_expected,payload_swap_delta=payload_expected,
    weak_id3_only_unchanged=row[7]==row[8],payload_only_exact_sum_unchanged=row[9]==row[10],
    no_hidden_row_ordinal=True),sort_keys=True,indent=2))
