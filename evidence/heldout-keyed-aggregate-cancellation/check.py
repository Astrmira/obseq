"""E7 independent F7 observers using native SQL bags; no label input."""
import argparse, hashlib, json, sqlite3
from pathlib import Path
import duckdb

def delta(c,keys):
    cols=', '.join(keys)
    return c.execute(f"""WITH unioned AS (SELECT 1 delta,x.* FROM a x UNION ALL SELECT -1 delta,x.* FROM b x)
              SELECT NOT EXISTS (SELECT 1 FROM unioned GROUP BY {cols} HAVING sum(delta)<>0)""").fetchall()[0][0]

def native(case,db):
    c=sqlite3.connect(':memory:') if db=='SQLite' else duckdb.connect(':memory:')
    try:
        for tbl,k in (('a','source'),('b','candidate')):
            c.execute('CREATE TABLE '+tbl+' (id BIGINT, g VARCHAR, v BIGINT)')
            if case[k]: c.executemany('INSERT INTO '+tbl+' VALUES (?,?,?)',case[k])
        def pair(s,tail=''):
            return c.execute('SELECT '+s+' FROM a'+tail).fetchall()==c.execute('SELECT '+s+' FROM b'+tail).fetchall()
        return {
          'shape_count_and_distinct_keys':pair('count(*),count(DISTINCT id)'),
          'per_group_sum_and_counts':pair('g,count(*),count(v),sum(v)',' GROUP BY g ORDER BY g'),
          'per_group_moments_extrema':pair('g,count(*),count(v),sum(v),sum(v*v),min(v),max(v)',' GROUP BY g ORDER BY g'),
          'per_group_value_bag':bool(delta(c,('g','v'))),
          'exact_keyed_bag':bool(delta(c,('id','g','v')))}
    finally: c.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('fixtures',type=Path)
    args=p.parse_args()
    raw=args.fixtures.read_bytes(); arr=json.loads(raw)
    assert len(arr)==24 and len({x['id'] for x in arr})==24
    result={}
    for case in arr:
        s=case['source']; assert len({x[0] for x in s})==len(s)
        for b in (s,case['candidate']):
            assert len(b)<=15
            assert all(type(k) is int and isinstance(g,str) and g.isascii() and g and (v is None or (type(v) is int and abs(v)<=10000)) for k,g,v in b)
        got={db:native(case,db) for db in ('SQLite','DuckDB')}
        assert got['SQLite']==got['DuckDB']
        assert got['SQLite']['exact_keyed_bag']==(sorted(s,key=str)==sorted(case['candidate'],key=str))
        result[case['id']]=got
    print(json.dumps(dict(case_sha256=hashlib.sha256(raw).hexdigest(),
        versions={'SQLite':sqlite3.sqlite_version,'DuckDB':duckdb.__version__},cases=result),
        sort_keys=True,indent=2))
if __name__=='__main__': main()
