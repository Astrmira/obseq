import json,sqlite3,polars as pl
vals=['A','a','a','B']; qs={
 'target':'SELECT MIN(v),COUNT(*) FROM q GROUP BY LOWER(v)',
 'aggregate_alias':'SELECT MIN(v) AS lo, COUNT(*) AS n FROM q GROUP BY LOWER(v)',
 'min_alias_only':'SELECT MIN(v) AS lo, COUNT(*) FROM q GROUP BY LOWER(v)',
 'count_alias_only':'SELECT MIN(v), COUNT(*) AS n FROM q GROUP BY LOWER(v)',
 'named_key':'SELECT LOWER(v) AS k,MIN(v) AS lo,COUNT(*) AS n FROM q GROUP BY k',
 'named_subquery':'SELECT MIN(v) AS lo,COUNT(*) AS n FROM (SELECT v,LOWER(v) AS k FROM q) s GROUP BY k',
 'grouping_base_control':'SELECT MIN(v),COUNT(*) FROM q GROUP BY v',
}
def execute(f):
 try:return sorted(f())
 except Exception as e:return {'error':type(e).__name__,'message':str(e)}
cx=pl.SQLContext(q=pl.DataFrame({'v':vals}),eager=True)
s=sqlite3.connect(':memory:');s.execute('create table q(v text collate binary)');s.executemany('insert into q values (?)',[(v,) for v in vals])
r={k:{'sql':q,'polars':execute(lambda:cx.execute(q).rows()),'sqlite':execute(lambda:s.execute(q).fetchall())} for k,q in qs.items()}
def plan(q):
 try: return pl.SQLContext(q=pl.DataFrame({'v':vals})).execute(q,eager=False).explain(optimized=False)
 except Exception as e: return type(e).__name__+': '+str(e)
for k in ('target','min_alias_only','count_alias_only'): r[k]['polars_plan']=plan(qs[k])
print(json.dumps(dict(polars=pl.__version__,sqlite=sqlite3.sqlite_version,results=r),indent=2))
