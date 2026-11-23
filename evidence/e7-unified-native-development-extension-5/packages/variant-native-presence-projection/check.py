#!/usr/bin/env python3
"""Pinned native VARIANT round trip, narrow typed carrier, and cross-reader oracle."""
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile

EXPECTED = [
    (0, 'NO_PATCH', None, None),
    (1, 'KEEP', None, None),
    (2, 'DELETE', None, None),
    (3, 'SET_I32', 0, None),
    (4, 'SET_TEXT', None, '0'),
    (5, 'OUT_OF_SCOPE', None, None),
    (6, 'KEEP', None, None),
]
TARGETS = [{}, {'k': None, 'b': 1}, {'k': 19, 'b': 2}]
SOURCE_ACTIONS = [{}, {'k': None}, {'k': 0}, {'k': '0'}]
NESTED = 'v.typed_value.k.'
EVERY = ('id', NESTED+'value', NESTED+'typed_value')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quoted(path):
    return "'" + str(path).replace("'", "''") + "'"


def hexify(value):
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [hexify(x) for x in value]
    if isinstance(value, dict):
        return {k: hexify(x) for k, x in value.items()}
    return value


def arrow_worker(site, shredded, bare, fallback):
    sys.path.insert(0, str(site))
    import pyarrow as pa
    import pyarrow.parquet as pq
    v = pa.__version__
    assert v in ('19.0.1', '22.0.0', '26.0.1')
    out = {'pyarrow': v, 'arrow_cpp': pa.cpp_version}
    if v == '19.0.1':
        for mode,path in (('shredded',shredded),('unshredded',bare)):
            keyword = 'arrow_extensions_enabled' in inspect.signature(pq.ParquetFile).parameters
            for options in (({'arrow_extensions_enabled':True},{'arrow_extensions_enabled':False}) if keyword else ({},)):
                try: pq.ParquetFile(path,**options)
                except OSError as ex:
                    assert str(ex)=='Metadata contains Thrift LogicalType that is not recognized'
                    out[mode]=str(ex)
                else: raise AssertionError('test was pinned to a clean compatibility rejection')
        return out
    S=pq.ParquetFile(shredded)
    U=pq.ParquetFile(bare)
    F=pq.ParquetFile(fallback)
    for p in (S,U,F):
        typ=p.schema_arrow.field('v').type
        assert pa.types.is_struct(typ)
        assert 'v (Variant(1))' in str(p.schema)
    assert S.schema.names==['id','metadata','value','value','typed_value']
    assert U.schema.names==['id','metadata','value']
    assert U.schema_arrow.field('v').type.field('value').nullable is False
    assert S.schema_arrow.field('v').type.field('typed_value').type.field('k').type.field('typed_value').type==pa.int32()
    raw=S.read(columns=EVERY,use_threads=False).to_pylist()
    assert [r['id'] for r in raw]==list(range(len(EXPECTED)))
    plans=[]
    for row in raw:
        i,root=row['id'],row['v']
        if root is None: p=(i,'NO_PATCH',None,None)
        elif root['typed_value'] is None: p=(i,'OUT_OF_SCOPE',None,None)
        else:
            pair=root['typed_value']['k']
            attr,typed=pair['value'],pair['typed_value']
            # Validated only the authored literals, not a general Variant decoder.
            if attr is None and typed is None: p=(i,'KEEP',None,None)
            elif attr==b'\x00' and typed is None: p=(i,'DELETE',None,None)
            elif attr is None and type(typed) is int: p=(i,'SET_I32',typed,None)
            elif attr==b'\x05\x30' and typed is None: p=(i,'SET_TEXT',None,'0')
            else: raise AssertionError(pair)
        plans.append(p)
    assert plans==EXPECTED
    full=S.read(use_threads=False).to_pylist()
    assert full[6]['v']['value'] and full[6]['v']['typed_value']['k']=={'value':None,'typed_value':None}
    assert full[5]['v']['value'] and full[5]['v']['typed_value'] is None
    narrow=S.read(columns=('id',NESTED+'typed_value'),use_threads=False).to_pylist()
    f=lambda i:narrow[i]['v']['typed_value']['k']['typed_value']
    assert f(1) is None and f(2) is None and f(3)==0 and f(4) is None
    upright=U.read(use_threads=False).to_pylist()
    assert [r['id'] for r in upright]==list(range(len(EXPECTED)))
    assert upright[0]['v'] is None
    raw_values=[r['v']['value'].hex() for r in upright[1:5]]
    assert raw_values==['020000','020100000100','02010000051400000000','02010000020530']
    alt=F.read(columns=EVERY,use_threads=False).to_pylist()
    assert [(r['id'],r['v']['typed_value']['k']) for r in alt]==[(3,{'value':None,'typed_value':0}),
                                        (7,{'value':b'\x18'+b'\x00'*8,'typed_value':None})]
    return dict(out,typed_struct=str(S.schema_arrow.field('v').type),binary_struct=str(U.schema_arrow.field('v').type),
                projected_raw=hexify(raw),carrier=plans,unshredded_value_hex=raw_values,
                same_json_zero_two_wire_lanes=hexify(alt),sibling_retained_in_omitted_residual=True)


def authored_effect(target, action):
    out=target.copy()
    if 'k' in action:
        if action['k'] is None:out.pop('k',None)
        else:out['k']=action['k']
    return out


def fingerprint(obj):
    if 'k' not in obj: return ('ABSENT',None,obj.get('b'))
    v=obj['k']
    return ('NULL' if v is None else 'I32' if type(v) is int else 'TEXT', v, obj.get('b'))


def apply(D, relation):
    # Nonobjects and OUT_OF_SCOPE do not enter this object-only protocol.
    sql=f"""SELECT p.id,t.tid,
       CASE WHEN p.kind='NO_PATCH' THEN t.doc
            ELSE json_merge_patch(t.doc,CASE p.kind
                 WHEN 'KEEP' THEN '{{}}'::JSON
                 WHEN 'DELETE' THEN json_object('k',NULL)
                 WHEN 'SET_I32' THEN json_object('k',p.i32)
                 WHEN 'SET_TEXT' THEN json_object('k',p.strval)
                 ELSE error('nonobject patch rejected by object carrier')::JSON
            END) END::VARCHAR
        FROM {relation} p, targets t WHERE p.id<=4 ORDER BY p.id,t.tid"""
    A=[(i,j,fingerprint(json.loads(z))) for i,j,z in D.sql(sql).fetchall()]
    B=[(i,j,fingerprint(authored_effect(t,{} if i==0 else SOURCE_ACTIONS[i-1])))
       for i in range(5) for j,t in enumerate(TARGETS)]
    assert A==B
    return A


def driver(ducksite, sites, scratch):
    sys.path.insert(0,str(ducksite))
    import duckdb
    assert duckdb.__version__=='2.0.1'
    D=duckdb.connect(config={'threads':1,'enable_external_access':True,
                            'autoinstall_known_extensions':False,'autoload_known_extensions':False})
    assert D.sql('PRAGMA version').fetchall()==[('v2.0.1','8d78114e90','Cyanoptera')]
    D.execute("""CREATE TABLE src AS
          SELECT 0 id, NULL::VARIANT v UNION ALL SELECT 1, '{}'::JSON::VARIANT
          UNION ALL SELECT 2, '{"k":null}'::JSON::VARIANT
          UNION ALL SELECT 3, {'k':0::INT32}::VARIANT
          UNION ALL SELECT 4, {'k':'0'::VARCHAR}::VARIANT
          UNION ALL SELECT 5, 23::INT32::VARIANT
          UNION ALL SELECT 6, '{"b":17}'::JSON::VARIANT""")
    D.execute("CREATE TABLE targets(tid INTEGER, doc JSON)")
    D.executemany("INSERT INTO targets VALUES (?,?)",[(i,json.dumps(t)) for i,t in enumerate(TARGETS)])
    shredded,bare,fallback=[scratch/(n+'.parquet') for n in ('shred_i32','unshred','same_numeric_value')]
    D.execute(f"COPY (SELECT * FROM src ORDER BY id) TO {quoted(shredded)} (FORMAT parquet, SHREDDING {{'v':'STRUCT(k INTEGER)'}})")
    D.execute(f"COPY (SELECT * FROM src ORDER BY id) TO {quoted(bare)} (FORMAT parquet, SHREDDING {{'v':'VARIANT'}})")
    D.execute(f"""COPY (SELECT id,v FROM src WHERE id=3
                  UNION ALL SELECT 7, '{{"k":0}}'::JSON::VARIANT ORDER BY id)
                  TO {quoted(fallback)} (FORMAT parquet, SHREDDING {{'v':'STRUCT(k INTEGER)'}})""")
    provenance=D.sql("""SELECT id,variant_type(v,'k'),v::JSON::VARCHAR
                       FROM (SELECT id,v FROM src WHERE id=3
                         UNION ALL SELECT 7, '{"k":0}'::JSON::VARIANT) t ORDER BY id""").fetchall()
    assert provenance==[(3,'INT32','{"k":0}'),(7,'UINT64','{"k":0}')]
    decoded=D.sql(f"""SELECT id,variant_type(v,'k'),try_cast(variant_extract(v,'k') AS INTEGER)
                  FROM read_parquet({quoted(fallback)}) ORDER BY id""").fetchall()
    assert decoded==[(3,'INT32',0),(7,'INT64',0)]
    results={}
    for file in (shredded,bare):
        mode=file.stem
        source='read_parquet('+quoted(file)+')'
        native=f"""SELECT id,v IS NULL,variant_typeof(v),variant_exists(v,'k'),
                  variant_type(v,'k'),variant_extract(v,'k') IS NULL,
                  variant_typeof(variant_extract(v,'k')),try_cast(variant_extract(v,'k') AS INTEGER)
                  FROM {source} ORDER BY id"""
        projection=f"""WITH paths AS (
           SELECT id,v IS NULL outer_null,variant_typeof(v) root_type,variant_exists(v,'k') present,
                  variant_type(v,'k') child_type,variant_extract(v,'k') child FROM {source}),
         tagged AS (
          SELECT *,
            CASE WHEN outer_null THEN 'NO_PATCH'
                 WHEN NOT starts_with(root_type,'OBJECT(') THEN 'OUT_OF_SCOPE'
                 WHEN NOT present THEN 'KEEP' WHEN child_type='VARIANT_NULL' THEN 'DELETE'
                 WHEN child_type='INT32' THEN 'SET_I32' WHEN child_type='VARCHAR' THEN 'SET_TEXT'
                 ELSE 'OUT_OF_SCOPE' END kind FROM paths)
         SELECT id,kind,CASE WHEN kind='SET_I32' THEN child::INTEGER END i32,
                        CASE WHEN kind='SET_TEXT' THEN child::VARCHAR END strval
         FROM tagged ORDER BY id"""
        obs=D.sql(native).fetchall()
        assert obs[0][1] and obs[0][3] is None
        assert obs[1][3:]==(False,None,True,'VARIANT_NULL',None)
        assert obs[2][3:]==(True,'VARIANT_NULL',True,'VARIANT_NULL',None)
        assert obs[3][3:]==(True,'INT32',False,'INT32',0)
        assert obs[4][3:]==(True,'VARCHAR',False,'VARCHAR',0)
        assert D.sql(projection).fetchall()==EXPECTED
        D.execute('PRAGMA disable_optimizer')
        assert D.sql(native).fetchall()==obs and D.sql(projection).fetchall()==EXPECTED
        D.execute('PRAGMA enable_optimizer')
        path=scratch/(mode+'-typed-carrier.parquet')
        D.execute(f"COPY ({projection}) TO {quoted(path)} (FORMAT parquet)")
        reread='read_parquet('+quoted(path)+')'
        assert D.sql('SELECT * FROM '+reread+' ORDER BY id').fetchall()==EXPECTED
        schema=D.sql('DESCRIBE SELECT * FROM '+reread).fetchall()
        assert [r[:2] for r in schema]==[('id','INTEGER'),('kind','VARCHAR'),('i32','INTEGER'),('strval','VARCHAR')]
        effects=apply(D,reread)
        rejects=D.sql(f"SELECT count(*) FROM {reread} WHERE kind='OUT_OF_SCOPE'").fetchall()
        assert rejects==[(1,)]
        lossy={}
        for behavior in ('omit','delete'):
            fallback_json="'{}'::JSON" if behavior=='omit' else "json_object('k',NULL)"
            q=f"""SELECT p.id,t.tid,json_merge_patch(t.doc,CASE WHEN p.scalar IS NULL THEN {fallback_json}
                    ELSE json_object('k',p.scalar) END)::VARCHAR FROM
                    (SELECT id,try_cast(variant_extract(v,'k') AS INTEGER) scalar FROM {source}
                     WHERE id BETWEEN 1 AND 4) p,targets t ORDER BY p.id,t.tid"""
            truth={(i,j):x for i,j,x in effects if i}
            actual={(i,j):fingerprint(json.loads(z)) for i,j,z in D.sql(q).fetchall()}
            err=sorted((i,j) for i,j in truth if truth[i,j]!=actual[i,j])
            assert len(err)==5
            lossy[behavior]={'correct':12-len(err),'wrong_pairs':err}
        assert lossy['omit']['wrong_pairs']!=lossy['delete']['wrong_pairs']
        results[mode]=dict(file_sha=digest(file),carrier=EXPECTED,native_observations=obs,
             exact_effect_trials=len(effects),exact_object_patch_trials=12,outer_no_patch_trials=3,
             effects=effects,lossy_typed_scalar=lossy)
    C=[]
    for x in sites:
        child=[sys.executable,'-IB',str(Path(__file__).resolve()),'--worker',str(x),
               str(shredded),str(bare),str(fallback)]
        p=subprocess.run(child,capture_output=True,text=True,timeout=30)
        assert p.returncode==0,p.stderr
        C.append(json.loads(p.stdout))
    assert [c['pyarrow'] for c in C]==['19.0.1','22.0.0','26.0.1']
    assert C[1]['carrier']==C[2]['carrier']==[list(i) for i in EXPECTED]
    assert C[1]['projected_raw']==C[2]['projected_raw']
    D.execute('CREATE TABLE raw_carrier(id INTEGER, kind VARCHAR, i32 INTEGER, strval VARCHAR)')
    D.executemany('INSERT INTO raw_carrier VALUES (?,?,?,?)',C[2]['carrier'])
    E=apply(D,'raw_carrier')
    return dict(duckdb_version='2.0.1',duckdb_source='8d78114e90',native=results,
                independent_arrow_readers=C,raw_leaf_carrier_effect_trials=len(E),
                same_numeric_provenance=dict(before_parquet=provenance,duckdb_read=decoded))


if __name__=='__main__':
    if sys.argv[1]=='--worker':
        print(json.dumps(arrow_worker(*map(Path,sys.argv[2:])),sort_keys=True))
    else:
        assert len(sys.argv)==6, 'DUCKDB_SITE ARROW19_SITE ARROW22_SITE ARROW26_SITE WRITABLE_SCRATCH'
        duck,*pa_sites,base=map(Path,sys.argv[1:])
        assert all(x.is_dir() for x in (duck,*pa_sites,base))
        with tempfile.TemporaryDirectory(dir=base) as t:
            print(json.dumps(driver(duck,pa_sites,Path(t)),indent=2,sort_keys=True))
