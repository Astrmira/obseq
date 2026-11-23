from fractions import Fraction
from hashlib import file_digest
from pathlib import Path
import json,sqlite3,sys
import duckdb,pyarrow as pa,pyarrow.compute as pc,pyarrow.parquet as pq
import numpy as np
COL='passenger_count'
S=-32768
def metrics(c,p):
    keep=c==S; clear=c==0; write=c>0; known=p!=S
    m=lambda a:int(np.count_nonzero(a))
    return dict(rows=len(c),keep=m(keep),clear=m(clear),write=m(write),
        clear_prior_has_value=m(clear&known),keep_prior_has_value=m(keep&known),
        stock_merge_typed_mismatches=m(clear),stock_merge_scalar_mismatches=0,
        omission_coerced_typed_mismatches=m(keep|clear),
        omission_coerced_scalar_mismatches=m(keep&known),
        coalesce_typed_mismatches=m(clear&known),coalesce_scalar_mismatches=m(clear&known))
def native_duck(p):
    db=duckdb.connect(config={'threads':1,'memory_limit':'384MB'})
    db.read_parquet(str(p),file_row_number=True).create_view('source')
    names=['rows','keep','clear','write','clear_prior_has_value','keep_prior_has_value','stock_merge_typed_mismatches',
           'stock_merge_scalar_mismatches','omission_coerced_typed_mismatches','omission_coerced_scalar_mismatches',
           'coalesce_typed_mismatches','coalesce_scalar_mismatches']
    x=db.sql("""WITH x AS (
      SELECT file_row_number i, passenger_count c, lag(passenger_count) over (ORDER BY file_row_number) p FROM source
    ), y AS (
      SELECT c,p,CASE WHEN c IS NULL THEN p WHEN c=0 THEN NULL ELSE c END expected,
        json_object('passenger_count',p) base,
        CASE WHEN c IS NULL THEN '{}'::JSON ELSE json_object('passenger_count',nullif(c,0)) END patch
        FROM x WHERE i>0
    ), z AS (
      SELECT c,p,expected,json_object('passenger_count',expected) correct,
        json_merge_patch(base,patch) raw_merge,
        json_merge_patch(base,json_object('passenger_count',nullif(c,0))) coerced,
        json_object('passenger_count',coalesce(nullif(c,0),p)) coalesced FROM y
    ) SELECT count(*),
      count(*) FILTER(WHERE c IS NULL),count(*) FILTER(WHERE c=0),count(*) FILTER(WHERE c>0),
      count(*) FILTER(WHERE c=0 AND p IS NOT NULL),count(*) FILTER(WHERE c IS NULL AND p IS NOT NULL),
      count(*) FILTER(WHERE NOT json_exists(raw_merge,'$.passenger_count') OR json_extract_string(raw_merge,'$.passenger_count')::BIGINT IS DISTINCT FROM expected),
      count(*) FILTER(WHERE json_extract_string(raw_merge,'$.passenger_count')::BIGINT IS DISTINCT FROM expected),
      count(*) FILTER(WHERE NOT json_exists(coerced,'$.passenger_count') OR json_extract_string(coerced,'$.passenger_count')::BIGINT IS DISTINCT FROM expected),
      count(*) FILTER(WHERE json_extract_string(coerced,'$.passenger_count')::BIGINT IS DISTINCT FROM expected),
      count(*) FILTER(WHERE NOT json_exists(coalesced,'$.passenger_count') OR json_extract_string(coalesced,'$.passenger_count')::BIGINT IS DISTINCT FROM expected),
      count(*) FILTER(WHERE json_extract_string(coalesced,'$.passenger_count')::BIGINT IS DISTINCT FROM expected),
      count(*) FILTER(WHERE NOT json_exists(correct,'$.passenger_count') OR json_extract_string(correct,'$.passenger_count')::BIGINT IS DISTINCT FROM expected)
      FROM z""").fetchall()[0]
    assert len(x)==len(names)+1 and x[-1]==0
    return dict(zip(names,x))
def native_sqlite(prev,cur):
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE source(seq INTEGER,p INTEGER,c INTEGER)')
    v=lambda x: None if x==S else int(x)
    db.executemany('INSERT INTO source VALUES(?,?,?)',[(j,v(p),v(c)) for j,(p,c) in enumerate(zip(prev,cur))])
    fail={k:0 for k in ('stock_merge_typed_mismatches','stock_merge_scalar_mismatches',
                       'omission_coerced_typed_mismatches','omission_coerced_scalar_mismatches',
                       'coalesce_typed_mismatches','coalesce_scalar_mismatches')}
    rows=db.execute("""WITH x AS (SELECT seq,p,c, CASE WHEN c IS NULL THEN p WHEN c=0 THEN NULL ELSE c END expected,
        json_object('passenger_count',p) base,
        CASE WHEN c IS NULL THEN '{}' ELSE json_object('passenger_count',nullif(c,0)) END patch FROM source)
      SELECT seq,expected,json_object('passenger_count',expected),json_patch(base,patch),
        json_patch(base,json_object('passenger_count',nullif(c,0))),
        json_object('passenger_count',coalesce(nullif(c,0),p)) FROM x""").fetchall()
    assert len(rows)==len(cur)
    for i,exp,right,*mut in rows:
        p,c=prev[i],cur[i]
        assert exp==(v(p) if c==S else None if c==0 else v(c))
        correct={'passenger_count':exp}; assert json.loads(right)==correct
        for k,j in zip(('stock_merge','omission_coerced','coalesce'),mut):
            x=json.loads(j)
            fail[k+'_typed_mismatches']+=x!=correct
            fail[k+'_scalar_mismatches']+=x.get('passenger_count')!=exp
    return fail
def run(p):
    arr=pq.read_table(p,columns=[COL]).column(0).combine_chunks()
    assert arr.type==pa.int64() and len(arr)==4181444
    x=pc.fill_null(arr,S).to_numpy()
    assert np.all((x==S)|(x>=0))
    all_=metrics(x[1:],x[:-1]); assert native_duck(p)==all_
    n=4097
    small=metrics(x[1:n],x[:n-1]); sqlite=native_sqlite(x[:n-1],x[1:n])
    assert all(small[k]==v for k,v in sqlite.items())
    with p.open('rb') as f: sha=file_digest(f,'sha256').hexdigest()
    return dict(source_sha256=sha,versions=dict(duckdb=duckdb.__version__,sqlite=sqlite3.sqlite_version,pyarrow=pa.__version__),
                full_native_duckdb=all_,prefix_native_sqlite=small)
if __name__=='__main__': print(json.dumps(run(Path(sys.argv[1])),sort_keys=True,indent=2))
