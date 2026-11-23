import os,json,sys,tempfile,subprocess,datetime,shutil
from pathlib import Path
from collections import Counter
from importlib.metadata import version
H=Path(__file__).parent
sys.path.insert(0,str(H/'deps'))
import duckdb
from datetime import timedelta,timezone
C={
 'current_both_histogram': [('A',-2),('A',-240),('B',-2),('B',-240)],
 'B_stalled_same_histogram': [('A',-2),('A',-2),('B',-240),('B',-240)],
 'B_absent_same_histogram': [('A',-2),('A',-2),('A',-240),('A',-240)],
 'unknown_C_old_but_out_of_scope': [('A',-2),('B',-2),('A',-240),('C',-240)],
 'both_aged': [('A',-240),('A',-360),('B',-240),('B',-360)]
}
G=['A','B'];F={'warn_after':{'count':30,'period':'minute'},'error_after':{'count':60,'period':'minute'}}
def reference(V):
 req={s:max([a for q,a in V if q==s],default=None) for s in G}
 return req,all(x is not None and x>=-60 for x in req.values())
def source():
 obs="(SELECT shard, max(loaded_at) AS m FROM {{ this }} WHERE shard IN ('A','B') GROUP BY shard)"
 Q={
 'global_max':dict(loaded_at_field='loaded_at',freshness=F),
 'filtered_a':dict(loaded_at_field='loaded_at',freshness=dict(F,filter="shard='A'")),
 'filtered_b':dict(loaded_at_field='loaded_at',freshness=dict(F,filter="shard='B'")),
 'naive_min_observed':dict(loaded_at_query=f'SELECT min(m) FROM {obs} s',freshness=F),
 'scope_complete_min':dict(loaded_at_query=f"SELECT CASE WHEN count(*)=2 THEN min(m) ELSE TIMESTAMP '1970-01-01' END FROM {obs} s",freshness=F)}
 return dict(version=2,sources=[dict(name='beats',schema='main',tables=[dict(name=k,identifier='incoming',config=v) for k,v in Q.items()])])
def j(path,obj):
 path.write_text(json.dumps(obj,indent=2))
def main():
 out={};raw={};now=datetime.datetime.now(timezone.utc).replace(tzinfo=None,microsecond=0)
 for k,V in C.items():
  with tempfile.TemporaryDirectory(dir='/tmp') as t:
   P=Path(t);(P/'models').mkdir()
   j(P/'dbt_project.yml',dict(name='audit',version='1.0.0',profile='audit',**{'model-paths':['models']}))
   j(P/'profiles.yml',{'audit':dict(target='local',outputs={'local':dict(type='duckdb',path=str(P/'audit.duckdb'),threads=1)})})
   j(P/'models'/'sources.yml',source())
   D=duckdb.connect(str(P/'audit.duckdb'));D.execute('CREATE TABLE incoming(shard VARCHAR NOT NULL, loaded_at TIMESTAMP NOT NULL)')
   D.executemany('INSERT INTO incoming VALUES (?,?)',[(s,now+timedelta(minutes=a)) for s,a in V]);D.close()
   e=dict(os.environ,PYTHONPATH=str(H/'deps'),DBT_SEND_ANONYMOUS_USAGE_STATS='false',DBT_PROFILES_DIR=t,DBT_PROJECT_DIR=t)
   cmd=[sys.executable,str(H/'deps/bin/dbt'),'source','freshness','--no-partial-parse','--no-send-anonymous-usage-stats']
   r=subprocess.run(cmd,cwd=t,env=e,text=True,capture_output=True,timeout=30)
   A=P/'target'/'sources.json'
   if not A.exists():
    (H/'failed.txt').write_text(r.stdout+'\n'+r.stderr);raise AssertionError('No native artifact')
   Z=json.loads(A.read_text())
   raw[k]=dict(artifact=Z,returncode=r.returncode)
   st={row['unique_id'].split('.')[-1]:row['status'] for row in Z['results']}
   assert set(st)=={'global_max','filtered_a','filtered_b','naive_min_observed','scope_complete_min'}
   ms,ref=reference(V)
   assert (st['scope_complete_min']=='pass')==ref
   assert all(((st['filtered_'+s.lower()]=='pass')==(ms[s] is not None and ms[s]>=-60)) for s in G)
   out[k]=dict(status=st,reference=ref,frontiers=ms,global_row_count=len(V),global_time_histogram=dict(sorted(Counter(a for _,a in V).items())))
 first,stalled,missing=list(out.values())[:3]
 assert first['global_time_histogram']==stalled['global_time_histogram']==missing['global_time_histogram']
 assert first['status']['global_max']==stalled['status']['global_max']==missing['status']['global_max']=='pass'
 assert missing['status']['naive_min_observed']=='pass'
 if '--raw' in sys.argv:j(H/'native-artifacts.json',raw)
 print(json.dumps(dict(versions={x:version(x) for x in ['dbt-core','dbt-duckdb','duckdb']},fixtures=out),sort_keys=True,indent=2))
if __name__=='__main__':main()
