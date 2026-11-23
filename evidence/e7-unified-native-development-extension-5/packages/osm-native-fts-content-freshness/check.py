import hashlib,json,re,sqlite3,sys,tempfile
from collections import Counter
from pathlib import Path
src=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/pvl-eab-submission/e4/inputs/osm/liechtenstein.gpkg')
scratch=Path(sys.argv[2]) if len(sys.argv)>2 else Path('/workspace/shared')
with src.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()=='5b0840c72e2ef9ac1bb211235cd6dd7170c0b400b72b472749490d93399c89cd'
assert sqlite3.sqlite_version=='3.53.1'
r=sqlite3.connect(src.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
data=r.execute('SELECT fid,name FROM gis_osm_roads_free ORDER BY fid').fetchall();r.close()
assert len(data)==14665 and len({k for k,_ in data})==len(data) and all(type(s)==str and '\0' not in s for _,s in data)
old=dict(data)
# FTS5 ascii tokenizer folds only ASCII and includes all non-ASCII codepoints
# among token characters; default ASCII punctuation is a separator.
fold=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')
pattern=re.compile('[0-9A-Za-z\u0080-\U0010FFFF]+')
def tok(s):return pattern.findall(s.translate(fold))
def posts(edition):return {(w,k,i) for k in edition for i,w in enumerate(tok(edition[k]))}
def ids(edition,term):return {i for i,a in edition.items() if term in tok(a)}
p0=posts(old)
df=Counter(t for t,i in {(t,i) for t,i,_ in p0})
terms=sorted((n*-1,t) for t,n in df.items()
             if 64<=n<=len(old)-64 and re.fullmatch('[0-9a-z]+',t))
term=terms[0][1]
hit0=ids(old,term)
a,b=sorted(hit0)[:64],sorted(set(old)-hit0)[:64]
assert len(a)==len(b)==64
new=old.copy()
for x,y in zip(a,b):new[x],new[y]=old[y],old[x]
changed=[k for k in new if new[k]!=old[k]];assert len(changed)==128
assert Counter(new.values())==Counter(old.values())
p1=posts(new)
assert Counter(x[0] for x in p1)==Counter(x[0] for x in p0)
hit1=ids(new,term)
assert hit1==hit0.difference(a).union(b)
def fts_check(c,scope):
    try:
        c.execute("INSERT INTO ft(ft,rank) VALUES('integrity-check',?)",[scope])
    except sqlite3.DatabaseError as e:
        assert c.in_transaction
        c.rollback()
        return e.sqlite_errorname
    c.rollback()
    return 'ok'
def observe(c,known,loaded):
    assert c.execute('SELECT rowid,name FROM ft ORDER BY rowid').fetchall()==list(known.items())
    pp=set(c.execute('SELECT term,doc,offset FROM vocab ORDER BY term,doc,offset'))
    assert pp==posts(loaded)
    assert Counter(t for t,_,_ in pp)==Counter(t for t,_,_ in posts(known))
    actual=c.execute('SELECT rowid,name FROM ft WHERE ft MATCH ? ORDER BY rowid',['"'+term+'"']).fetchall()
    assert actual==[(k,known[k]) for k in sorted(ids(loaded,term))]
    truth=ids(known,term)
    observed={k for k,_ in actual}
    return dict(generic_db_integrity=c.execute('PRAGMA integrity_check').fetchall(),
      internal_only=fts_check(c,0),content_bound=fts_check(c,1),match_rows=len(actual),
      wrong_inclusions=len(observed-truth),missing=len(truth-observed),
      projected_labels_without_term=sum(term not in tok(s) for _,s in actual),
      all_row_projection_current=True,global_token_occurrences_preserved=True,
      wrong_index_postings=len(pp-posts(known)),missing_index_postings=len(posts(known)-pp))
def open_db(p):
    c=sqlite3.connect(p)
    assert c.execute('PRAGMA integrity_check').fetchone()==('ok',)
    return c
with tempfile.TemporaryDirectory(dir=scratch,prefix='fts-f4-') as d:
    p=Path(d)/'index.sqlite'
    c=open_db(p)
    c.executescript("""CREATE TABLE content(fid INTEGER PRIMARY KEY,name TEXT NOT NULL);
                    CREATE VIRTUAL TABLE ft USING fts5(name,content='content',content_rowid='fid',tokenize='ascii');
                    CREATE VIRTUAL TABLE vocab USING fts5vocab(ft, 'instance');""")
    c.executemany('INSERT INTO content VALUES(?,?)',data)
    c.execute("INSERT INTO ft(ft) VALUES('rebuild')")
    c.commit();c.close()
    c=open_db(p)
    base=observe(c,old,old)
    assert base['content_bound']=='ok'
    c.executemany('UPDATE content SET name=? WHERE fid=?',[(new[k],k) for k in changed])
    c.commit();c.close()
    c=sqlite3.connect(p)
    stale=observe(c,new,old)
    assert stale['internal_only']=='ok' and stale['content_bound']=='SQLITE_CORRUPT_VTAB'
    assert stale['wrong_inclusions']==stale['missing']==64
    c.executescript("""CREATE TRIGGER maintain_name AFTER UPDATE OF name ON content BEGIN
                    INSERT INTO ft(ft,rowid,name) VALUES('delete',old.fid,old.name);
                    INSERT INTO ft(rowid,name) VALUES(new.fid,new.name);
                    END;""")
    c.commit()
    late=observe(c,new,old)
    assert late==stale
    c.execute('BEGIN')
    c.executemany("INSERT INTO ft(ft,rowid,name) VALUES('delete',?,?)",[(k,old[k]) for k in changed])
    c.executemany("INSERT INTO ft(rowid,name) VALUES(?,?)",[(k,new[k]) for k in changed])
    c.commit();c.close()
    c=open_db(p)
    repaired=observe(c,new,new)
    assert repaired['content_bound']=='ok' and repaired['wrong_inclusions']==repaired['missing']==0
    c.executemany('UPDATE content SET name=? WHERE fid=?',[(old[k],k) for k in changed])
    c.commit();c.close()
    c=open_db(p)
    reversed_maintained=observe(c,old,old)
    assert reversed_maintained==base
    c.close()
print(json.dumps(dict(native_sqlite=sqlite3.sqlite_version,rows=len(data),changed_bound_fids=len(changed),
    total_literal_postings=len(p0),nonempty_names=sum(bool(x) for x in old.values()),phases=dict(baseline=base,only_content_changed=stale,late_triggers=late,
    bounded_repair=repaired,trigger_maintained_reverse=reversed_maintained)),indent=2,sort_keys=True))
