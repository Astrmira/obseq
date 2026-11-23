import sqlite3,tempfile,pathlib,shutil,json,hashlib
manifest=json.load(open('manifest.json'))
SOURCE=[tuple(r) for r in manifest['golden_rows']]
assert manifest['profiles']['old']=={'operation':'multiply','coefficient':2}
assert manifest['profiles']['new']=={'operation':'multiply','coefficient':3}
def attach(path,mult):
 d=sqlite3.connect(path)
 d.create_function('score',1,lambda x:mult*x,deterministic=True)
 return d
def receipt(d):
 return d.execute('select id,x,cached,current,score(x) from t order by id').fetchall()
def expect(cache,now):
 return [(i,v,cache*v,now*v,now*v) for i,v in SOURCE]
with tempfile.TemporaryDirectory() as tmp:
 root=pathlib.Path(tmp);p=root/'base.sqlite';q=root/'moved.sqlite'
 old=attach(p,2)
 old.execute('create table t(id integer primary key,x integer,cached integer generated always as (score(x)) stored,current integer generated always as (score(x)) virtual)')
 old.executemany('insert into t(id,x) values(?,?)',SOURCE)
 old.execute('create index ix on t(cached,id)')
 old.commit()
 assert receipt(old)==expect(2,2)
 old.close();shutil.copyfile(p,q)
 base=hashlib.sha256(q.read_bytes()).digest()
 d=attach(q,3)
 after=receipt(d);assert after==expect(2,3)
 assert hashlib.sha256(q.read_bytes()).digest()==base
 integrity=d.execute('pragma integrity_check').fetchall()
 d.execute('reindex ix');d.commit()
 after_reindex=receipt(d);assert after_reindex==after
 d.execute('update t set x=x');d.commit();d.close()
 d=attach(q,3)
 recomputed=receipt(d);assert recomputed==expect(3,3)
 assert d.execute('pragma integrity_check').fetchall()==[('ok',)];d.close()
 print(json.dumps({'sqlite':sqlite3.sqlite_version,'changed_registration':after,'after_reindex':after_reindex,'after_recompute':recomputed,
                   'pre_repair_integrity_ok':integrity==[('ok',)],'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'split_fields':['id','source','stored','virtual','ad_hoc']},sort_keys=True,indent=2))
