import hashlib,itertools,json,math,sys
from pathlib import Path
from collections import Counter
import duckdb,pyarrow,pyarrow.parquet as pq
path=sys.argv[1]
with open(path,'rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()==Path(__file__).with_name('SOURCE.sha256').read_text().split()[0]
columns=['PULocationID','trip_distance','DOLocationID','passenger_count','payment_type']
oracle={}
c=Counter()
i=-1
for batch in pq.ParquetFile(path).iter_batches(columns=columns,batch_size=65536):
    rows=zip(*(x.to_pylist() for x in batch.columns))
    for group,score,*raw in rows:
        i+=1
        if group is None or score is None or not math.isfinite(score) or score<=0: continue
        c['eligible_rows']+=1
        payload=tuple(raw)
        if group not in oracle or score<oracle[group][0]:
            oracle[group]=(score,{i:payload})
        elif score==oracle[group][0]:
            oracle[group][1][i]=payload
c['physical_rows']=i+1
c['excluded_rows']=c['physical_rows']-c['eligible_rows']
c['groups']=len(oracle)
c['winning_source_rows']=sum(len(rows) for _,rows in oracle.values())
c['groups_with_source_row_ties']=sum(len(rows)>1 for _,rows in oracle.values())
pools={g:set(rows.values()) for g,(_,rows) in oracle.items()}
c['groups_with_payload_ties']=sum(len(ps)>1 for ps in pools.values())
c['groups_with_any_null_winning_payload']=sum(any(None in p for p in ps) for ps in pools.values())
c['max_winning_source_rows']=max(len(rows) for _,rows in oracle.values())
db=duckdb.connect(config={'threads':'1','memory_limit':'512MB','max_temp_directory_size':'0B'})
queries={}
for label,orderby in [('first',' ORDER BY file_row_number ASC'),('last',' ORDER BY file_row_number DESC'),('native','')]:
    stmt=f"""SELECT PULocationID g, MIN(trip_distance) score,
    arg_min(struct_pack(i := file_row_number, d := DOLocationID, p := passenger_count,
                        t := payment_type), trip_distance{orderby}) x
    FROM read_parquet(?, file_row_number=true)
    WHERE PULocationID IS NOT NULL AND isfinite(trip_distance) AND trip_distance > 0
    GROUP BY PULocationID ORDER BY PULocationID"""
    rows=db.execute(stmt,[path]).fetchall()
    assert len(rows)==len(oracle) and set(g for g,_,_ in rows)==set(oracle)
    candidates={}
    for g,score,x in rows:
        payload=(x['d'],x['p'],x['t'])
        expected_score,winners=oracle[g]
        assert score==expected_score and x['i'] in winners and payload==winners[x['i']]
        if label=='first': assert x['i']==min(winners)
        if label=='last': assert x['i']==max(winners)
        candidates[g]=(x['i'],payload)
    queries[label]=candidates
for label in ['last','native']:
    c[label+'_ordinal_differs_from_first']=sum(queries[label][g][0]!=queries['first'][g][0] for g in oracle)
    c[label+'_payload_differs_from_first']=sum(queries[label][g][1]!=queries['first'][g][1] for g in oracle)
def product_rows(ps):
    return list(itertools.product(*[sorted({p[j] for p in ps},key=lambda x:(x is None,x)) for j in range(3)]))
bad = {}
for g, ps in sorted(pools.items()):
    extras = set(product_rows(ps))-ps
    if extras: bad[g]=extras
c['groups_where_marginals_overaccept']=len(bad)
c['noncoherent_marginal_payloads']=sum(map(len,bad.values()))
native_bad=0
sql="""WITH eligible AS (
 SELECT * FROM read_parquet(?, file_row_number=true)
 WHERE PULocationID IS NOT NULL AND isfinite(trip_distance) AND trip_distance > 0
), winners AS (
 SELECT * FROM eligible QUALIFY trip_distance=min(trip_distance) OVER (PARTITION BY PULocationID)
)
SELECT PULocationID,min(DOLocationID),min(passenger_count),min(payment_type) FROM winners
GROUP BY PULocationID ORDER BY PULocationID"""
mixed=db.execute(sql,[path]).fetchall()
assert len(mixed)==len(oracle) and set(r[0] for r in mixed)==set(oracle)
for g,*p in mixed:
    assert tuple(p) in product_rows(pools[g])
    native_bad+=tuple(p) not in pools[g]
c['native_independent_min_false_accept_groups']=native_bad
assert c['last_payload_differs_from_first']>0 and native_bad>0
print(json.dumps(dict(counts=dict(c),duckdb=duckdb.__version__,pyarrow=pyarrow.__version__,native_legal_cases=3,
                     rank_and_membership='exact finite stored binary64 and typed tuple',timings=None),indent=2,sort_keys=True))
