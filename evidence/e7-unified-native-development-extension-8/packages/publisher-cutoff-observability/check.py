from pathlib import Path
from collections import Counter
import csv, hashlib, json, sys
import duckdb

p,hits=map(Path,sys.argv[1:])
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
con=duckdb.connect(config={"threads":1,"memory_limit":"512MB"})
con.read_csv(str(p),columns={"id1":"VARCHAR","id2":"VARCHAR","id3":"VARCHAR","id4":"BIGINT","id5":"BIGINT","id6":"BIGINT","v1":"BIGINT","v2":"BIGINT","v3":"DOUBLE"},header=True).create_view("x")
stock=con.sql("SELECT id6, unnest(max(v3, 2)) largest2_v3 FROM x WHERE v3 IS NOT NULL GROUP BY id6").fetchall()
assert con.sql('select count(*) from x').fetchall()[0]==(10_000_000,)
groups={}
with p.open(newline='') as f:
    for a in csv.reader(f):
        if not a[8] or a[8]=='v3': continue
        i=int(a[5]) if a[5] else None
        v=float(a[8])
        state=groups.get(i)
        if state is None: groups[i]=[v,1,None,0,1]
        else:
            state[4]+=1
            hi,hc,lo,lc,_=state
            if v>hi: state[:4]=[v,1,hi,hc]
            elif v==hi: state[1]+=1
            elif lo is None or v>lo: state[2:4]=[v,1]
            elif v==lo: state[3]+=1
expected=Counter()
cutoff=Counter()
cross=Counter()
for i,(hi,hc,lo,lc,n) in groups.items():
    expected[i,hi]+=1
    if n==1: continue
    t,s=(hc,2) if hc>=2 else (lc,1)
    expected[i,hi if hc>=2 else lo]+=1
    cutoff[t]+=1
    if t>s: cross[t]+=1
assert expected==Counter(stock)
con.read_parquet(str(hits),file_row_number=True).create_view('hits')
assert con.sql('select count(*) from hits').fetchall()[0]==(1_000_000,)
click={}
for q,key in [(24,'EventTime'),(25,'SearchPhrase'),(26,'EventTime, SearchPhrase')]:
    expr=f"row({key})" if "," in key else key
    stock=con.sql(f"SELECT SearchPhrase FROM hits WHERE SearchPhrase <> '' ORDER BY {key} LIMIT 10").fetchall()
    result={}
    for order in ('ASC','DESC'):
        rows=con.sql(f"SELECT {expr}, SearchPhrase, file_row_number FROM hits WHERE SearchPhrase <> '' ORDER BY {key}, file_row_number {order} LIMIT 10").fetchall()
        result[order]=rows
    t=result['ASC'][-1][0]
    assert result['DESC'][-1][0]==t
    source=con.sql(f"SELECT {expr}, SearchPhrase, file_row_number FROM hits WHERE SearchPhrase <> ''").fetchall()
    assert all(r[0] is not None and (not isinstance(r[0],tuple) or None not in r[0]) for r in source)
    strict=[r for r in source if r[0]<t]
    peers=[r for r in source if r[0]==t]
    s=10-len(strict)
    assert 1<=s<=len(peers)
    assert set(strict)<=set(result['ASC']) and set(strict)<=set(result['DESC'])
    assert all(len(set(rs))==10 for rs in result.values())
    # Observable validity needs a multiset injection into admissible source rows.
    left=Counter(stock)-Counter((r[1],) for r in strict)
    peer=Counter((r[1],) for r in peers)
    assert sum(left.values())==s and not left-peer
    click[q]={"key":key,"eligible":len(source),
      "strict":len(strict),"cutoff_slots":s,"cutoff_class":len(peers),"cutoff_distinct_projected_values":len(peer),
      "legal_refinements_select_different_physical_ids":set(result['ASC'])!=set(result['DESC']),
      "legal_refinements_select_different_projected_multisets":Counter(r[1] for r in result['ASC'])!=Counter(r[1] for r in result['DESC']),
      "stock_projection_is_admissible":True}
print(json.dumps({"duckdb":duckdb.__version__, "inputs":{p.name:sha(p),hits.name:sha(hits)},
     "h2o_q8":{"groups":len(groups), "with_two_eligible_rows":sum(cutoff.values()),"stock_projected_rows":sum(expected.values()),
        "cutoff_multiplicities":dict(sorted(cutoff.items())),"straddling_class_multiplicities":dict(sorted(cross.items())),
        "observable_projection_changes":0},"clickbench":click},sort_keys=True,indent=2))
