"""Candidate evaluator: no label or author-oracle reference anywhere in this file."""
from itertools import combinations,groupby,product
from pathlib import Path
from hashlib import sha256
import json
import duckdb

R=Path(__file__).resolve().parent
assert sha256((R/'inputs.json').read_bytes()).hexdigest()=='843cf87577e3ddf6d88ae9dfab2dd0949f3f5197b4ad1d83a1682fc10374700c'
assert duckdb.__version__=="2.0.1"
def B(rows):return tuple(sorted(map(tuple,rows),key=lambda x:json.dumps(x,separators=(',',':'))))
def A(choices):return sorted(set(choices),key=lambda x:json.dumps(x,separators=(',',':')))
D=duckdb.connect()
D.execute("CREATE TABLE src(a VARCHAR,b VARCHAR,v BIGINT)")
G="SELECT a,b,sum(v) AS s, 2*GROUPING(a)+GROUPING(b) AS mask FROM src GROUP BY GROUPING SETS ((a,b),(a),())"
out=[]
for c in json.loads((R/'inputs.json').read_text()):
    if c['family']=='group':
        D.execute('DELETE FROM src')
        D.executemany("INSERT INTO src VALUES (?,?,?)",c['rows'])
        k=c['k']; off=c['offset']; sel=c['selection']
        if sel=='limit':
            exact_family=[]; seen=0
            base=D.execute(G+" ORDER BY s DESC").fetchall()
            for score,arr in groupby(base,lambda r:r[2]):
                arr=list(arr)
                take=max(0,min(seen+len(arr),off+k)-max(seen,off))
                exact_family.append(list(combinations(arr,take)))
                seen+=len(arr)
            bags=A(B(r for seq in combos for r in seq) for combos in product(*exact_family))
            witness=D.execute(G+' ORDER BY s DESC LIMIT ? OFFSET ?',[k,off]).fetchall()
        else:
            assert sel in ('rank','dense_rank')
            witness=D.execute(f"SELECT * FROM ({G}) d QUALIFY {sel}() OVER (ORDER BY s DESC)<=? ORDER BY s DESC",[k]).fetchall()
            bags=[B(witness)]
        assert B(witness) in bags
        project=A(B(r[:3] for r in bag) for bag in bags)
        wrong=A(B((*r[:3],2*int(r[0] is None)+int(r[1] is None)) for r in bag) for bag in bags)
        out.append(dict(id=c['id'],family=c['family'],full=bags,projected=project,
                        rendered_null_mask_full=wrong))
    else:
        t,b,a,s,e,m=(c[n] for n in ('transition_utc','offset_before','offset_after',
                                    'start_local','end_local','observed_duration'))
        q="""WITH src(name,l) AS (VALUES ('s',?::BIGINT),('e',?::BIGINT)),
            offsets(o,side) AS (VALUES (?::BIGINT,0),(?::BIGINT,1)),
            candidates AS (SELECT name,l-o AS u FROM src CROSS JOIN offsets
               WHERE ((l-o < ?::BIGINT) = (side=0))) """
        raw=D.execute(q+"SELECT name,u FROM candidates ORDER BY name,u",[s,e,b,a,t]).fetchall()
        start=sorted({v for k,v in raw if k=='s'});end=sorted({v for k,v in raw if k=='e'})
        joint=D.execute(q+"""SELECT x.u,y.u,y.u-x.u FROM candidates x CROSS JOIN candidates y
               WHERE x.name='s' AND y.name='e' AND y.u>=x.u ORDER BY 1,2,3""",[s,e,b,a,t]).fetchall()
        if start and end and end[0]>=start[0]:
            earliest=[(start[0],end[0],end[0]-start[0])]
        else:
            earliest=[]
        out.append(dict(id=c['id'],family=c['family'],start=start,end=end,joint=joint,
                        durations=sorted({r[2] for r in joint}), observed_matches=[r for r in joint if r[2]==m],
                        earliest_only=earliest))
print(json.dumps(out,indent=2,sort_keys=True))
