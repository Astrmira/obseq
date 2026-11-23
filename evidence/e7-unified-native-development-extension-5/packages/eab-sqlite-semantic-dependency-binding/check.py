import sqlite3,tempfile,pathlib,shutil,json,hashlib
rows=[(11,'a'),(12,'A'),(13,'é'),(14,'e\u0301'),(15,'ß'),(16,'a'),(17,'')]
name='CANONICAL_ORDER'
def cmp(a,b):return (a>b)-(a<b)
def connect(p,reverse):
 d=sqlite3.connect(p)
 d.create_collation(name,lambda a,b:(-1 if reverse else 1)*cmp(a,b))
 return d
def observed(d,use_index):
 term='indexed by ix' if use_index else 'not indexed'
 sql=f'select id from t {term} order by k collate {name},id'
 plan=[r[3] for r in d.execute('explain query plan '+sql)]
 assert ('TEMP B-TREE' in ' '.join(plan)) != use_index
 return [i for i, in d.execute(sql)]
def oracle(reverse):
 # Stable ID resolves exact duplicate keys. Reverse applies only to codepoint text order.
 by={k:[] for _,k in rows}
 for i,k in rows:by[k].append(i)
 return [i for k in sorted(by,reverse=reverse) for i in sorted(by[k])]
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp)/'original.sqlite'
 d=connect(p,False);d.execute('create table t(id integer primary key,k text not null)')
 d.executemany('insert into t values(?,?)',rows)
 d.execute(f'create index ix on t(k collate {name},id)')
 d.commit();assert observed(d,True)==observed(d,False)==oracle(False);d.close()
 q=p.with_name('relocated.sqlite');shutil.copyfile(p,q)
 original_hash=hashlib.sha256(p.read_bytes()).digest()
 assert hashlib.sha256(q.read_bytes()).digest()==original_hash
 d=connect(q,True)
 indexed=observed(d,True);full_sort=observed(d,False)
 assert sorted(d.execute('select id,k from t not indexed').fetchall())==rows
 assert indexed==oracle(False) and indexed!=full_sort==oracle(True)
 assert hashlib.sha256(q.read_bytes()).digest()==original_hash
 bad=[s for s, in d.execute('pragma integrity_check')]
 assert bad!=['ok']
 d.execute('reindex ix');d.commit();d.close()
 d=connect(q,True)
 verified=observed(d,True)
 assert verified==full_sort==oracle(True) and d.execute('pragma integrity_check').fetchall()==[('ok',)]
 assert hashlib.sha256(q.read_bytes()).digest()!=original_hash
 d.close()
 print(json.dumps({'sqlite':sqlite3.sqlite_version,'old_index_new_runtime':indexed,'new_runtime_full_sort':full_sort,
  'new_runtime_reindexed':verified,'old_hash_stable_without_reindex':True,'integrity_check_before_reindex_ok':False},sort_keys=True,indent=2))
