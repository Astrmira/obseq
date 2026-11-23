"""Run unchanged stock dbt unit/relationship tests and authored coupled data tests."""
from pathlib import Path
from importlib.metadata import version
from collections import defaultdict
import json,os,subprocess,sys,tempfile

deps,scratch=map(Path,sys.argv[1:])
deps=deps.resolve()
sys.path.insert(0,str(deps))
import duckdb
SRC=[(1,101,5,1,9),(1,102,5,2,2),(1,103,6,0,0),(2,201,7,3,4),(2,202,9,4,3)]
cols=['g','ord','s','a','b']
names=('legal_asc','legal_desc','invalid_mixed')
def put(p,s):p.write_text(s)
def pairs(p,x):put(p,json.dumps(x,indent=2))
def independent(rs):
    expected={}
    for g,o,s,a,b in SRC:
        if g not in expected or s<expected[g][0]:expected[g]=(s,{(a,b)})
        elif s==expected[g][0]:expected[g][1].add((a,b))
    return len(rs)==len(expected) and len({r[0] for r in rs})==len(expected) and all(
        g in expected and (a,b) in expected[g][1] for g,a,b in rs)
def script(name):
    if name=='invalid_mixed':
        return """WITH w AS (select * from {{ ref('src_candidates') }}
          QUALIFY s=min(s) OVER(PARTITION BY g))
          SELECT g,min(a) a,min(b) b FROM w GROUP BY g"""
    order='ASC' if name=='legal_asc' else 'DESC'
    return "SELECT g,a,b FROM {{ ref('src_candidates') }} QUALIFY row_number() OVER(PARTITION BY g ORDER BY s,ord "+order+")==1"
env=dict(os.environ, PYTHONPATH=str(deps),DBT_SEND_ANONYMOUS_USAGE_STATS='false',
         OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
with tempfile.TemporaryDirectory(prefix='native-dbt-verify-',dir=scratch) as t:
    root=Path(t);m=root/'models';tt=root/'tests';m.mkdir();tt.mkdir()
    dbpath=root/'input.duckdb'
    pairs(root/'dbt_project.yml',dict(name='audit',version='1.0.0',profile='audit',
        **{'model-paths':['models'],'test-paths':['tests']},models={'audit':{'+materialized':'table'}}))
    pairs(root/'profiles.yml',{'audit':dict(target='local',outputs={'local':dict(type='duckdb',path=str(dbpath),threads=1)})})
    values=','.join('('+','.join(map(str,r))+')' for r in SRC)
    put(m/'src_candidates.sql',f"SELECT * FROM (VALUES {values}) AS v(g,ord,s,a,b)")
    for field in ['a','b']:
        put(m/f'allowed_{field}.sql',f"""WITH w AS (select * from {{{{ ref('src_candidates') }}}}
            QUALIFY s=min(s) over(partition by g))
            SELECT DISTINCT cast(g as varchar)||':'||cast({field} as varchar) AS projected FROM w""")
    def attrs(name):
        return dict(name=name,columns=[dict(name='g',data_tests=['unique','not_null'])])
    # A separate keyed marginal surface makes each native generic relationship test
    # compare genuine (group,value) pairs, not just unrelated values across groups.
    generic=[attrs(n) for n in names]
    for n in names:
        put(m/f'{n}.sql',script(n))
        put(m/f'{n}_projection.sql',f"""select g,
             cast(g as varchar)||':'||cast(a as varchar) AS scope_a,
             cast(g as varchar)||':'||cast(b as varchar) AS scope_b
             from {{{{ ref('{n}') }}}}""")
        generic.append(dict(name=n+'_projection',columns=[
            dict(name=f'scope_{k}',data_tests=[{'relationships':dict(arguments=dict(to=f"ref('allowed_{k}')",field='projected'))}])
            for k in ('a','b')]))
        put(tt/f'intended_coupled_{n}.sql',f"""select c.* from {{{{ ref('{n}') }}}} c
           where not exists (select 1 from {{{{ ref('src_candidates') }}}} s
             where s.g=c.g and s.a is not distinct from c.a and s.b is not distinct from c.b
             and s.s=(select min(z.s) from {{{{ ref('src_candidates') }}}} z where z.g=c.g))""")
    gold=[dict(g=1,a=1,b=9),dict(g=2,a=3,b=4)]
    fixtures=dict(version=2,models=generic,unit_tests=[
        dict(name='fixed_same_golden_'+n,model=n,
             given=[dict(input="ref('src_candidates')",rows=[dict(zip(cols,r)) for r in SRC])],
             expect=dict(rows=gold)) for n in names])
    pairs(m/'tests.yml',fixtures)
    env['DBT_PROJECT_DIR']=str(root);env['DBT_PROFILES_DIR']=str(root)
    def run(*args):
        cmd=[sys.executable,str(deps/'bin/dbt'),*args,'--no-partial-parse','--no-send-anonymous-usage-stats']
        r=subprocess.run(cmd,cwd=root,env=env,text=True,capture_output=True,timeout=32)
        rf=root/'target'/'run_results.json'
        if not rf.exists():
            (Path(__file__).parent/'LAST-LOCAL-ERROR.txt').write_text(r.stdout+r.stderr)
            raise ValueError(r.returncode)
        d=json.loads(rf.read_text())
        out=[dict(id=x['unique_id'],status=x['status'],failures=x.get('failures')) for x in d['results']]
        return r.returncode,out
    rc, build=run('run')
    assert rc==0 and all(n['status']=='success' for n in build),build
    db=duckdb.connect(str(dbpath),read_only=True)
    truth={n:independent(db.execute(f'select g,a,b from "{n}"').fetchall()) for n in names}
    db.close()
    assert truth==dict(legal_asc=True,legal_desc=True,invalid_mixed=False)
    uc,unit=run('test','--select','test_type:unit')
    st={n['id'].split('.')[-1]:n['status'] for n in unit}
    assert uc==1 and st=={f'fixed_same_golden_{n}':('pass' if n=='legal_asc' else 'fail') for n in names},(uc,unit)
    dc,data=run('test','--select','test_type:data')
    assert dc==1,(dc,data)
    summary=defaultdict(list); check={}
    for p in data:
        n=p['id'].split('.')[2]
        if n.startswith('intended_coupled_'):check[n.removeprefix('intended_coupled_')]=p['status']
        else:summary[n.split('_')[0]].append(p['status'])
    assert check=={n:'pass' if truth[n] else 'fail' for n in names} and set(summary)=={'unique','not','relationships'},summary
    assert all(s==['pass']*(6 if k=='relationships' else 3) for k,s in summary.items()),summary
    print(json.dumps(dict(versions={x:version(x) for x in ['dbt-core','dbt-duckdb','duckdb']},
                independent=truth,fixed_unit=st,coupled_data=check,generic_status=summary,
                unit_code=uc,data_code=dc,total_stock_generic=12),sort_keys=True,indent=2))
