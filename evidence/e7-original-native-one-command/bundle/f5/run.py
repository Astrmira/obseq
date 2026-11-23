import hashlib,importlib.util,json,pathlib,sqlite3,sys,re,tempfile,subprocess
p,pg=map(pathlib.Path,sys.argv[1:]); pins={'BLIND.json':'8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831','check.py':'f005d93a52f8a4b69f772ef5c81a1cdc469df4c93a695f2f8ac24b57292b1cb6'}
assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in pins.items())
s=importlib.util.spec_from_file_location('frozen',p/'check.py');o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
cases=[x for x in json.loads((p/'BLIND.json').read_text()) if x['class']=='F5'];assert len(cases)==6
def j(x):return json.dumps(x,separators=(',',':'),sort_keys=True)
def sqlstr(x):return "'"+str(x).replace("'","''")+"'"
def patches(case):
 x=case['inputs']; return x['old'],x['patches'] if 'patches'in x else [x['patch']]
def sqlite_run(old,pat,wrong):
 with sqlite3.connect(':memory:') as c:
  c.execute('CREATE TABLE state(doc TEXT NOT NULL CHECK(json_valid(doc)))')
  c.execute('INSERT INTO state VALUES(json(?))',[j(old)])
  paths=[]
  for z in pat:
   if wrong=='rfc_merge':
    c.execute('UPDATE state SET doc=json_patch(doc,json(?))',[j(z)])
   else:
    for k,v in z.items():
     assert re.fullmatch(r'[a-z]+',k)
     if wrong=='truthiness' and (not v or v=='null'):continue
     c.execute('UPDATE state SET doc=json_set(doc,?,json(?))',['$.'+k,j(v)])
   paths.append(json.loads(c.execute('SELECT doc FROM state').fetchone()[0]))
  return paths
sql=[];pgkey={}
for i,r in enumerate(cases):
 old,pat=patches(r); tbl=f'x{i}'
 sql.append(f'CREATE TABLE {tbl}(doc JSONB NOT NULL);')
 sql.append(f'INSERT INTO {tbl} VALUES({sqlstr(j(old))}::jsonb);')
 sql.append('BEGIN;')
 for s,step in enumerate(pat):
  sql.append(f'UPDATE {tbl} SET doc=doc||{sqlstr(j(step))}::jsonb;')
  tag=f'eab_{i}_{s}';pgkey[tag]=(i,s)
  sql.append(f"SELECT encode(convert_to(doc::TEXT,'UTF8'),'hex') AS {tag} FROM {tbl};")
 sql.append('COMMIT;')
with tempfile.TemporaryDirectory() as t:
 b=pathlib.Path(t)/'db'; exe=pg/'postgres'
 version=subprocess.check_output([str(exe),'--version'],text=True).strip();assert version.startswith('postgres (PostgreSQL) 17.12')
 subprocess.run([str(pg/'initdb'),'--no-sync','--locale=C.UTF-8','--encoding=UTF8','--auth-local=peer','--auth-host=scram-sha-256','-D',str(b)],text=True,capture_output=True,timeout=35,check=True)
 r=subprocess.run([str(exe),'--single','-c','shared_buffers=16MB','-D',str(b),'postgres'],input='\n'.join(sql)+'\n',text=True,capture_output=True,check=True,timeout=35)
 assert not any(e in r.stderr for e in ('ERROR:','FATAL:','PANIC:')),r.stderr
 rx=dict(re.findall(r'\b(eab_\d+_\d+) = "([a-f0-9]+)"',r.stdout))
 assert set(rx)==set(pgkey)
 got={pgkey[k]:json.loads(bytes.fromhex(v)) for k,v in rx.items()}
out={}
for i,r in enumerate(cases):
 old,pat=patches(r);native=sqlite_run(old,pat,None)
 assert all(j(z)==j(got[(i,s)]) for s,z in enumerate(native))
 verdict=o.legal(r)
 assert o.legal(dict(r,candidate=native[-1])) and (j(native[-1])==j(r['candidate']))==verdict
 ctr={}
 for k in ('rfc_merge','truthiness'):
  z=sqlite_run(old,pat,k)
  ctr[k]=dict(steps=z,contract_pass=o.legal(dict(r,candidate=z[-1])))
 out[r['case_id']]=dict(native_SQLite_PostgreSQL_steps=native,original_admissible=verdict,exact_matches_frozen_oracle=True,controls=ctr)
assert sum(not v['controls']['rfc_merge']['contract_pass'] for v in out.values())==2
assert all(not v['controls']['truthiness']['contract_pass'] for v in out.values())
print(json.dumps(dict(postgres=version,sqlite=sqlite3.sqlite_version,pins=pins,cases=out),indent=2,sort_keys=True))
