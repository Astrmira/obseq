import hashlib,json,sqlite3,subprocess,sys,tempfile,re
from pathlib import Path
import duckdb,pyarrow as pa
base=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/pvl-eab-submission/e4/inputs/osm/liechtenstein.gpkg')
scratch=Path(sys.argv[2]) if len(sys.argv)>2 else Path('/workspace/shared')
assert sqlite3.sqlite_version=='3.53.1' and duckdb.__version__=='1.4.3'
with base.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()=='5b0840c72e2ef9ac1bb211235cd6dd7170c0b400b72b472749490d93399c89cd'
original=sqlite3.connect(base.as_uri()+'?mode=ro&immutable=1',uri=True)
rows=original.execute('SELECT fid,osm_id FROM gis_osm_buildings_a_free ORDER BY fid').fetchall()
ogr=sorted(map(tuple,map(json.loads,subprocess.check_output(['/usr/bin/python3','-IB',
    str(Path(__file__).with_name('extract.py')),str(base)]).splitlines())))
assert rows==ogr and len(rows)==17914 and len(set(x[1] for x in rows))==len(rows)
assert all(re.fullmatch('[1-9][0-9]*',s) and int(s)<2**53 and str(int(s))==s for _,s in rows)
original.close()
with tempfile.TemporaryDirectory(dir=scratch,prefix='eab-osm-f9-') as d:
    d=Path(d)
    for key,extra in [('ordinary',''),('strict',' STRICT')]:
        p=d/(key+'.sqlite')
        c=sqlite3.connect(p)
        c.execute('CREATE TABLE mapped(fid INTEGER PRIMARY KEY, osm_id ANY NOT NULL)'+extra)
        c.executemany('INSERT INTO mapped VALUES(?,?)',rows)
        c.commit();c.close()
    a=sqlite3.connect((d/'ordinary.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
    a.execute('ATTACH ? AS s',[(d/'strict.sqlite').as_uri()+'?mode=ro&immutable=1'])
    schema={}
    G={}
    for label,namespace,keyname in [('ordinary','main','integer'),('strict','s','text')]:
        assert a.execute('PRAGMA '+namespace+'.integrity_check').fetchone()==('ok',)
        assert [x[-1] for x in a.execute('PRAGMA '+namespace+'.table_list').fetchall() if x[1]=='mapped']==[int(label=='strict')]
        schema[label]=a.execute('PRAGMA '+namespace+'.table_info(mapped)').fetchall()
        counts=a.execute(f'''SELECT typeof(osm_id),json_type(json_object('osm_id',osm_id),'$.osm_id'),count(*)
            FROM {namespace}.mapped GROUP BY 1,2''').fetchall()
        assert counts==[(keyname,keyname,len(rows))]
        group_count,sum_ids=a.execute(f'SELECT count(*),sum(cast(osm_id as integer)) FROM {namespace}.mapped').fetchone()
        assert group_count==len(rows) and sum_ids==sum(int(s) for _,s in rows)
        vals=a.execute(f"SELECT fid,json_object('osm_id',osm_id) FROM {namespace}.mapped ORDER BY fid").fetchall()
        expect=[(i,int(s) if keyname=='integer' else s) for i,s in rows]
        assert [(i,json.loads(z)['osm_id']) for i,z in vals]==expect
        G[label]=[z for _,z in vals]
    assert schema['ordinary']==schema['strict']
    T=lambda name: f"json_extract(json_object('osm_id',{name}.osm_id),'$.osm_id')"
    # Exact numeric adapter vs typed expression with no column affinity.
    same_fid_join='FROM mapped a JOIN s.mapped b ON a.fid=b.fid'
    sql=f'SELECT count(*) {same_fid_join} WHERE {T("a")}={T("b")}'
    assert a.execute(sql).fetchone()==(0,)
    assert a.execute(f'SELECT count(*) {same_fid_join} WHERE CAST({T("a")} AS INTEGER)=CAST({T("b")} AS INTEGER)').fetchone()==(len(rows),)
    recovered=a.execute("SELECT fid,json_extract(json_object('osm_id',CAST(osm_id AS TEXT)),'$.osm_id') FROM mapped ORDER BY fid").fetchall()
    assert recovered==rows
    a.close()
    ddb=duckdb.connect(config={'threads':'1'})
    ddb.register('editions',pa.table(G))
    downstream={}
    for version,tag in [('ordinary','UBIGINT'),('strict','VARCHAR')]:
        s=ddb.execute(f"SELECT json_type({version}::JSON,'$.osm_id'),count(*) FROM editions GROUP BY 1").fetchall()
        assert s==[(tag,len(rows))]
        downstream[version]=dict(s)
print(json.dumps(dict(source_rows=len(rows),typed_fid_attribute_declarations_equal=True,
    sqlite_type_counts={'ordinary':{'integer':len(rows)},'strict':{'text':len(rows)}},
    exact_cast_integer_comparisons_agree=len(rows),json_uncoerced_key_comparisons_agree=0,
    explicit_text_serialization_recovers=len(rows),native_readback_json_types_duckdb=downstream,
    strictness_flag_differs=True,sqlite=sqlite3.sqlite_version,duckdb=duckdb.__version__,
    construct='private persisted staged copies with source strings unchanged'),sort_keys=True,indent=2))
