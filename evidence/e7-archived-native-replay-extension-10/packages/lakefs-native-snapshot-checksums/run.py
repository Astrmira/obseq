import csv,io,json,os,re,socket,sqlite3,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
h=Path(__file__).parent
b=Path(sys.argv[1]).resolve()
cases=json.loads((h/'CASES.json').read_text())
with tempfile.TemporaryDirectory(dir=sys.argv[2]) as z:
 p=Path(z)
 with socket.socket() as s:
  s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 endpoint=f'http://127.0.0.1:{port}'
 ak='EABLOCALDEMO00000001';sk='synthetic-local-unusable-key-not-remote'
 cfg=dict(listen_address=f'127.0.0.1:{port}',database=dict(type='local',local=dict(path=str(p/'meta'))),blockstore=dict(type='local',local=dict(path=str(p/'blocks'))),stats=dict(enabled=False),installation=dict(user_name='eab-local',access_key_id=ak,secret_access_key=sk),auth=dict(encrypt=dict(secret_key='synthetic-local-encryption-key')),actions=dict(enabled=False),security=dict(check_latest_version=False,audit_check_interval='0s',audit_check_url=endpoint+'/no-external-audit'),email_subscription=dict(enabled=False),logging=dict(level='WARN'),committed=dict(local_cache=dict(size_bytes=16000000),sstable=dict(memory=dict(cache_size_bytes=16000000))))
 (p/'server.json').write_text(json.dumps(cfg));(p/'home').mkdir()
 env=dict(PATH='/usr/bin:/bin',HOME=str(p/'home'),GOMAXPROCS='2',LAKECTL_SERVER_ENDPOINT_URL=endpoint,LAKECTL_CREDENTIALS_ACCESS_KEY_ID=ak,LAKECTL_CREDENTIALS_SECRET_ACCESS_KEY=sk)
 def ctl(*a,input=None):
  rr=subprocess.run([str(b/'lakectl'),*a],input=input,cwd=p,env=env,capture_output=True,timeout=15)
  if rr.returncode:raise RuntimeError(rr.stdout+rr.stderr)
  return rr.stdout
 def upload(uri,contents):
  ctl('fs','upload',uri,'--source','-','--no-progress','--pre-sign=false',input=contents)
  s=ctl('fs','stat',uri,'--pre-sign=false')
  checksum=re.search(rb'^Checksum:\s*([a-f0-9]+)',s,re.M).group(1).decode()
  assert ctl('fs','cat',uri,'--pre-sign=false')==contents
  return checksum
 def csvbytes(rows):
  f=io.StringIO();w=csv.writer(f,lineterminator='\n');w.writerow(('id','value'));w.writerows(rows);return f.getvalue().encode()
 with (p/'server.log').open('wb') as log:
  server=subprocess.Popen([str(b/'lakefs'),'--config',str(p/'server.json'),'run'],stdout=log,stderr=subprocess.STDOUT,cwd=p,env=env)
  try:
   for _ in range(100):
    try:
     assert server.poll() is None
     if urllib.request.build_opener(urllib.request.ProxyHandler({})).open(endpoint+'/_health',timeout=.4).status==200:break
    except OSError:time.sleep(.04)
   else:raise RuntimeError('failed to start')
   base='lakefs://eab-native'
   ctl('repo','create',base,'local://objects')
   decisions=[]
   for c in cases:
    tag=c['case']+'-'+str(c['arm']);a=c['gold_observation'];v=c['observation'];assert a!=v
    if c['case']=='F7':
     assert sum(x[1] for x in a)==sum(x[1] for x in v)
     src,dst=csvbytes(a),csvbytes(v)
    else:
     q=p/(tag+'.db')
     con=sqlite3.connect(q)
     try:
      assert con.execute('pragma journal_mode=wal').fetchone()[0]=='wal'
      con.execute('pragma wal_autocheckpoint=0')
      con.execute('CREATE TABLE vals(k INTEGER, v INTEGER)');con.executemany('INSERT INTO vals VALUES (?,?)',v);con.commit()
      con.execute('pragma wal_checkpoint(truncate)')
      dst=q.read_bytes()
      con.execute('UPDATE vals SET v=?',(a[0][1],));con.commit()
      src=q.read_bytes()
      assert len(Path(str(q)+'-wal').read_bytes())>32
      assert [list(t) for t in con.execute('select * from vals')]==a
      tmp=p/(tag+'-main-only.db');tmp.write_bytes(src)
      with sqlite3.connect(tmp) as st: assert [list(t) for t in st.execute('select * from vals')]==v
     finally:con.close()
    u=base+'/main/'+tag
    aa=upload(u+'-gold',src);bb=upload(u+'-candidate',dst)
    ctl('commit',base+'/main','-m',tag)
    assert ctl('fs','cat',u+'-gold','--pre-sign=false')==src
    assert ctl('fs','cat',u+'-candidate','--pre-sign=false')==dst
    assert (aa==bb)==(src==dst)==(c['case']=='F3')
    decisions.append(dict(case=c['case'],arm=c['arm'],bytes_equal=src==dst,checksum_equal=aa==bb,typed_answers_equal=False))
   a=[[1,10],[2,20]]
   aa=upload(base+'/main/legal-a',csvbytes(a));bb=upload(base+'/main/legal-b',csvbytes(a[::-1]))
   assert aa!=bb
   decisions.append(dict(case='legal-reorder-control',arm=0,bytes_equal=False,checksum_equal=False,typed_answers_equal=True))
   print(json.dumps(dict(version=subprocess.check_output([str(b/'lakefs'),'--version'],env=env,text=True).strip(),sqlite=sqlite3.sqlite_version,decisions=decisions),sort_keys=True,indent=2))
  finally:
   server.terminate()
   try:server.wait(timeout=8)
   except subprocess.TimeoutExpired:server.kill();server.wait(timeout=4)
