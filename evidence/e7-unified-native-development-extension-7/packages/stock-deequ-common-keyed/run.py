import json,os,sys,tempfile,subprocess,shutil,zipfile
from pathlib import Path
p=Path(__file__).parent
base=Path(sys.argv[1]).resolve()
spark=base/'pyspark-4.0.1'/'deps'
deequ=base/'deequ.jar'
java=shutil.which('java')
cpath=f"{spark/'jars'}/*:{deequ}"
cases=json.loads((p/'CASES.json').read_text())
labels={x['id']:x['legal'] for x in json.loads((p/'SEALED_LABELS.json').read_text())}
def encode(x):return {f'_{i+1}':y for i,y in enumerate(x)}
with tempfile.TemporaryDirectory(dir=sys.argv[2]) as t:
 t=Path(t); w=t/'classes';w.mkdir()
 j=t/'input.jsonl'; j.write_text(''.join(json.dumps(dict(id=x['id'],gold=list(map(encode,x['source'])),candidate=list(map(encode,x['candidate']))))+'\n' for x in cases))
 e=dict(os.environ,SPARK_LOCAL_IP='127.0.0.1',SPARK_LOCAL_HOSTNAME='localhost',SPARK_LOCAL_DIRS=str(t),SPARK_HOME=str(spark),HOME=str(t))
 subprocess.run([java,'-Xmx768m','-Dscala.usejavacp=true','-cp',cpath,'scala.tools.nsc.Main','-d',str(w),str(p/'DeequControl.scala')],env=e,check=True)
 a=t/'control.jar'
 with zipfile.ZipFile(a,'w') as z:
  for f in sorted(w.rglob('*.class')):z.write(f,str(f.relative_to(w)))
 cmd=[str(spark/'bin'/'spark-submit'),'--master','local[2]','--driver-memory','768m','--conf','spark.ui.enabled=false','--conf','spark.sql.shuffle.partitions=2','--conf','spark.driver.host=127.0.0.1','--conf','spark.driver.bindAddress=127.0.0.1','--jars',str(deequ),'--class','DeequControl',str(a),str(j)]
 r=subprocess.run(cmd,env=e,cwd=t,text=True,capture_output=True,timeout=150)
 if r.returncode:
  print(r.stderr,file=sys.stderr);r.check_returncode()
 out=dict(deequ='2.0.15-spark-4.0',decisions={},suggestions=[])
 for line in r.stdout.splitlines():
  if line.startswith('EAB_SUGGEST\t'):out['suggestions'].append(line.split('\t',1)[1])
  if line.startswith('EAB_DECISION\t'):
   _,k,*v=line.split('\t');out['decisions'][k]=dict(zip(('keys','keys_count','suggested'),[x=='true' for x in v]))
  if line.startswith("EAB_FIT_RULE\t"):
   _,s,c=line.split("\t");out.setdefault("suggestion_fit_rules",{})[c]=s
  if line.startswith("EAB_FIT\t"):
   _,k,v=line.split("\t");out["suggestion_fit"]={"reference_id":k,"pass":v=="true"}
  if line.startswith('EAB_SPARK\t'):out['spark']=line.split('\t')[1]
 assert out['suggestions'] and set(out['decisions'])==set(labels) and out['spark']=='4.0.1'
 out['scores']={config:{'false_admit':sum(not y and out['decisions'][k][config] for k,y in labels.items()),'false_reject':sum(y and not out['decisions'][k][config] for k,y in labels.items())} for config in ('keys','keys_count','suggested')}
 print(json.dumps(out,sort_keys=True,indent=2))
