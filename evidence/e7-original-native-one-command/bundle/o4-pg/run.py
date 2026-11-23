import hashlib,importlib.util,json,pathlib,re,subprocess,sys,tempfile
src,bin,store=map(pathlib.Path,sys.argv[1:])
pins={'BLIND.json':'8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831','check.py':'f005d93a52f8a4b69f772ef5c81a1cdc469df4c93a695f2f8ac24b57292b1cb6'}
for f,d in pins.items():assert hashlib.sha256((src/f).read_bytes()).hexdigest()==d
sp=importlib.util.spec_from_file_location('oracle',src/'check.py'); oracle=importlib.util.module_from_spec(sp);sp.loader.exec_module(oracle)
rows=[x for x in json.loads((src/'BLIND.json').read_text()) if 'E7H-O4-' in x['case_id']]
assert len(rows)==24
result={}; sql=[]; index=[]
def lit(v):return "'"+str(v).replace("'","''")+"'"
num=r'^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$'
for r in rows:
 k=r['case_id'];a,b=r['inputs'],r['candidate']
 result[k]={'independent':oracle.legal(r)}
 if '-numtext-' in k:
  x,y=lit(a['reference']),lit(b['text'])
  q=f"CASE WHEN {x} ~ {lit(num)} AND {y} ~ {lit(num)} THEN CASE WHEN (CASE WHEN {x} ~ {lit(num)} THEN {x} END)::numeric=(CASE WHEN {y} ~ {lit(num)} THEN {y} END)::numeric THEN 'equal' ELSE 'unequal' END ELSE 'invalid' END"
 elif '-dateserial-' in k:
  ser=lit(b['serial'])
  if 'referenceDate' in a:
   s=a.get('system')
   dt=f"{lit(a['referenceDate'])}::date"
   epoch=lit('1899-12-31' if s=='1900-compat' else '1904-01-01' if s=='1904' else a['epoch'])
   calc=f"({dt}-{epoch}::date)"+(f"+CASE WHEN {dt}>=DATE '1900-03-01' THEN 1 ELSE 0 END" if s=='1900-compat' else '')
   eq=f"({calc})={ser}::numeric"
  else:
   eq=f"EXTRACT(EPOCH FROM ({lit(a['reference'])}::timestamptz-{lit(a['epoch'])}::timestamptz))={ser}::numeric*86400"
  q=f"CASE WHEN {eq} THEN 'equal' ELSE 'unequal' END"
 else:
  result[k]['native']='NA: geometry/pointset outside PostgreSQL non-spatial type lane';continue
 sql.append(f"SELECT ({q}) AS eab_{len(index)};");index.append(k)
with tempfile.TemporaryDirectory(dir=store) as work:
 p=pathlib.Path(work)/'pg'
 version=subprocess.check_output([str(bin/'postgres'),'--version'],text=True).strip()
 assert version.startswith('postgres (PostgreSQL) 17.12')
 a=subprocess.run([str(bin/'initdb'),'--no-sync','--locale=C.UTF-8','--encoding=UTF8','--auth-local=peer','--auth-host=scram-sha-256','-D',str(p)],capture_output=True,text=True,timeout=35,check=True)
 a=subprocess.run([str(bin/'postgres'),'--single','-c','timezone=UTC','-c','shared_buffers=16MB','-c','jit=off','-D',str(p),'postgres'],input='\n'.join(sql)+'\n',capture_output=True,text=True,timeout=35,check=True)
 assert not any(x in a.stderr for x in ('ERROR:','FATAL:','PANIC:')),a.stderr
 vals=dict(re.findall(r'\beab_([0-9]+) = "(equal|unequal|invalid)"',a.stdout))
 assert len(vals)==len(index)==12
for i,k in enumerate(index):
 v=vals[str(i)];assert (v=='equal')==result[k]['independent'],k
 result[k]['native']=v
print(json.dumps({'postgres':version,'pins':pins,'cells':result},sort_keys=True,indent=2))
