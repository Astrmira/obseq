#!/usr/bin/env python3
import hashlib,itertools,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import duckdb

ROOT=Path(sys.argv[2]); assert ROOT.is_dir()
assert duckdb.__version__=='2.0.1'
def sqlpath(p):return "'" + str(p).replace("'","''") + "'"
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(dir):
    D=duckdb.connect()
    D.execute("SET threads=1")
    D.execute('CREATE TABLE raw(id INT, s JSON)')
    patterns={}
    for version,clear in enumerate(itertools.combinations(range(1,7),3)):
        rows=[(j,json.dumps({'k':None} if j in clear else {})) for j in range(1,7)]
        rows += [(7,'{"k":"null"}'),(8,'{"k":0}'),(9,'{"k":"0"}')]
        D.execute('DELETE FROM raw')
        D.executemany('INSERT INTO raw VALUES (?,?)',rows)
        cases={}
        source=D.sql("SELECT id,json_exists(s,'$.k'),json_type(s,'$.k'),json_extract(s,'$.k')::VARCHAR FROM raw ORDER BY id").fetchall()
        expected=[(i, i in clear, 'NULL' if i in clear else None, 'null' if i in clear else None) for i in range(1,7)]
        expected += [(7,True,'VARCHAR','"null"'),(8,True,'UBIGINT','0'),(9,True,'VARCHAR','"0"')]
        assert source==expected
        D.execute("CREATE OR REPLACE TEMP VIEW inmem AS SELECT id, s::VARIANT v FROM raw ORDER BY id")
        expected=[(i,has,t,val) for i,has,t,val in expected]
        assert D.sql("SELECT id,json_exists(v::JSON,'$.k'),json_type(v::JSON,'$.k'),json_extract(v::JSON,'$.k')::VARCHAR FROM inmem ORDER BY id").fetchall()==expected
        for option in ('default','integer','varchar'):
            fname=dir/f'{version}-{option}.parquet'; dst=sqlpath(fname)
            shred='' if option=='default' else ", SHREDDING {'v': 'STRUCT(k "+ {'integer':'INTEGER','varchar':'VARCHAR'}[option]+")'}"
            D.execute(f"COPY (SELECT * FROM inmem) TO {dst} (FORMAT parquet{shred})")
            D.execute(f"CREATE OR REPLACE TEMP VIEW p AS SELECT * FROM read_parquet({dst})")
            schema=D.sql(f"SELECT name,type,duckdb_type FROM parquet_schema({dst})").fetchall()
            assert ('v',None,'VARIANT') in schema
            if option!='default':
                assert any(a=='typed_value' and b=={'integer':'INT32','varchar':'BYTE_ARRAY'}[option] for a,b,_ in schema)
                assert any(a=='k' and b is None for a,b,_ in schema) and sum(a=='value' for a,b,_ in schema)>=2
            for optimizer in ('default','disabled'):
                D.execute('PRAGMA enable_optimizer' if optimizer=='default' else 'PRAGMA disable_optimizer')
                full=D.sql("SELECT id,json_exists(v::JSON,'$.k'),json_type(v::JSON,'$.k'),json_extract(v::JSON,'$.k')::VARCHAR FROM p ORDER BY id").fetchall()
                assert full==expected
                child=D.sql("SELECT id,v.k IS NULL, variant_typeof(v.k),v.k::JSON::VARCHAR FROM p ORDER BY id").fetchall()
                assert all((nil,ty,val)==(True,'VARIANT_NULL',None) for i,nil,ty,val in child[:6])
                assert [r[3] for r in child[6:]]==['"null"','0','"0"']
                D.execute("CREATE OR REPLACE TEMP TABLE tgt AS SELECT i::INT id, '41'::JSON result FROM range(1,10) t(i)")
                # Stored object existence and exact operation policy are separate from scalar projection.
                D.execute("""
                 MERGE INTO tgt t USING
                  (SELECT id,json_exists(v::JSON,'$.k') present,
                   CASE WHEN json_type(v::JSON,'$.k')='NULL' THEN NULL ELSE json_extract(v::JSON,'$.k') END val FROM p) s
                 ON t.id=s.id WHEN MATCHED AND s.present THEN UPDATE SET result=s.val
                """)
                observed=[v for (v,) in D.sql('SELECT result::VARCHAR FROM tgt ORDER BY id').fetchall()]
                expect=[None if i in clear else '41' for i in range(1,7)]+['"null"','0','"0"']
                assert observed==expect
            D.execute('PRAGMA enable_optimizer')
            flat=dir/f'{version}-{option}-flat.parquet'; f=sqlpath(flat)
            D.execute(f"COPY (SELECT id,v.k::JSON::VARCHAR val FROM p ORDER BY id) TO {f} (FORMAT parquet)")
            D.execute("CREATE OR REPLACE TEMP TABLE tgt AS SELECT i::INT id, '41'::JSON result FROM range(1,10) t(i)")
            D.execute(f"""MERGE INTO tgt t USING read_parquet({f}) s ON t.id=s.id
                          WHEN MATCHED AND s.val IS NOT NULL THEN UPDATE SET result=s.val::JSON""")
            skipped=[v for (v,) in D.sql('SELECT result::VARCHAR FROM tgt ORDER BY id').fetchall()]
            assert sum(x!=y for x,y in zip(skipped,expect))==3
            cases[option]=dict(raw=digest(fname),flat=digest(flat),native_subtype_for_json_zero=child[7][2],
                    full_merge=observed,skip_null_wrong=3,schema=schema)
        patterns[str(version)]=cases
    for key in ('default','integer','varchar'):
        assert len({c[key]['raw'] for c in patterns.values()})==20
        assert len({c[key]['flat'] for c in patterns.values()})==1
    # RFC 7396 is a different effect contract, observed in native DuckDB.
    obj='{"k":7}'
    fx=D.execute("SELECT json_merge_patch(?::JSON,?::JSON)::VARCHAR,json_merge_patch(?::JSON,?::JSON)::VARCHAR",[obj,'{}',obj,'{"k":null}']).fetchone()
    assert list(map(json.loads,fx))==[{'k':7},{}]
    return dict(duckdb=duckdb.__version__,rfc7396_native_effects=list(map(json.loads,fx)),patterns=patterns)
with tempfile.TemporaryDirectory(dir=ROOT) as t:
    print(json.dumps(run(Path(t)),sort_keys=True,indent=2))
