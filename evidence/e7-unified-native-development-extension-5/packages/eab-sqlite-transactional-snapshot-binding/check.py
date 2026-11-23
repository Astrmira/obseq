import sqlite3,tempfile,pathlib,hashlib,json
def blob(path):
 return pathlib.Path(path).read_bytes()
def sha(b):return hashlib.sha256(b).hexdigest()
def rows(db):return db.execute('select id,k from t order by id').fetchall()
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp)/'state.sqlite';side=p.with_name(p.name+'-wal')
 writer=sqlite3.connect(p)
 assert writer.execute('pragma journal_mode=WAL').fetchone()==('wal',)
 writer.execute('pragma wal_autocheckpoint=0')
 writer.execute('create table t(id integer primary key,k integer)')
 writer.execute('insert into t values(1,17)')
 writer.commit()
 assert writer.execute('pragma wal_checkpoint(TRUNCATE)').fetchone()==(0,0,0)
 before=blob(p)
 pinned=sqlite3.connect(p);pinned.execute('begin')
 assert rows(pinned)==[(1,17)]
 writer.execute('update t set k=21 where id=1')
 writer.execute('insert into t values(2,0)');writer.commit()
 fresh=sqlite3.connect(p)
 expect=[(1,21),(2,0)]
 assert rows(fresh)==expect and rows(pinned)==[(1,17)] and blob(p)==before and side.stat().st_size>0
 # Materialize logically requested state through the open SQLite source, not by copying its main file.
 pinned_before=pathlib.Path(tmp)/'pinned.sqlite'; live_file=pathlib.Path(tmp)/'current.sqlite'
 for src,dest,exp in [(pinned,pinned_before,[(1,17)]),(fresh,live_file,expect)]:
  backup=sqlite3.connect(dest);src.backup(backup);backup.close()
  b=sqlite3.connect(dest);assert rows(b)==exp;b.close()
 copied=pathlib.Path(tmp)/'main-only.sqlite';copied.write_bytes(before)
 b=sqlite3.connect(copied);assert rows(b)==[(1,17)];b.close()
 held_checkpoint=writer.execute('pragma wal_checkpoint(PASSIVE)').fetchone()
 assert held_checkpoint[1]>held_checkpoint[2]
 pinned.close();fresh.close()
 assert writer.execute('pragma wal_checkpoint(TRUNCATE)').fetchone()==(0,0,0)
 assert rows(writer)==expect and blob(p)!=before
 physical={'same_main_hash_before_checkpoint':True,'changed_hash_after_checkpoint':sha(blob(p))!=sha(before)}
 writer.close()
 print(json.dumps({'sqlite':sqlite3.sqlite_version,'physical':physical,'wal_frames_during_reader':held_checkpoint[1],
  'checkpointed_during_reader':held_checkpoint[2],'main_artifact_readback':[(1,17)],'fresh_logical_readback':expect,
  'pinned_logical_readback':[(1,17)]},sort_keys=True,indent=2))
