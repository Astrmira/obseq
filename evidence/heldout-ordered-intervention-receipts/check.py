"""Native replay and deterministic observer; does not read sealed labels."""
import hashlib, json, sqlite3, sys
from pathlib import Path
from collections import Counter
import duckdb

def expected(case):
    state=dict(case['initial'])
    events=[]
    for a in case['intent']:
        if a['op']=='keep' or a['id'] not in state: continue
        new=None if a['op']=='clear' else a['value']
        state[a['id']]=new
        events.append([a['op'],a['id'],new])
    return [[k,v] for k,v in sorted(state.items())],events

def native(case,engine):
    sqlite=engine=='SQLite'
    db=sqlite3.connect(':memory:',isolation_level=None) if sqlite else duckdb.connect(':memory:')
    try:
        db.execute('CREATE TABLE x(k BIGINT PRIMARY KEY,v BIGINT)')
        db.execute("CREATE TABLE receipt(i INTEGER PRIMARY KEY,kind VARCHAR,k BIGINT,v BIGINT)")
        if sqlite:
            db.execute("""CREATE TRIGGER real_update AFTER UPDATE ON x BEGIN
            INSERT INTO receipt (kind,k,v)
            VALUES (CASE WHEN NEW.v IS NULL THEN 'clear' ELSE 'write' END,NEW.k,NEW.v); END""")
        for row in case['initial']: db.execute('INSERT INTO x VALUES (?,?)',row)
        db.execute('BEGIN TRANSACTION')
        for i,a in enumerate(case['attempt'],1):
            if a['op']=='keep': continue
            new=None if a['op']=='clear' else a['value']
            if sqlite:
                db.execute('UPDATE x SET v=? WHERE k=?',[new,a['id']])
            else:
                matched=db.execute('UPDATE x SET v=? WHERE k=? RETURNING k,v',[new,a['id']]).fetchall()
                assert len(matched)<=1
                for k,v in matched:
                    assert k==a['id'] and v==new
                    db.execute('INSERT INTO receipt VALUES (?,?,?,?)',[i,'clear' if v is None else 'write',k,v])
        outcome=case['outcome']
        assert outcome in ('commit','rollback')
        db.execute(outcome.upper())
        state=[list(r) for r in db.execute('SELECT k,v FROM x ORDER BY k').fetchall()]
        events=[list(r) for r in db.execute('SELECT kind,k,v FROM receipt ORDER BY i').fetchall()]
        return state,events
    finally: db.close()

def observe(case,actual):
    state,events=actual
    es,ee=expected(case)
    return {
        'typed':case['outcome']=='commit' and state==es and events==ee,
        'poststate_only':state==es,
        'committed_poststate':case['outcome']=='commit' and state==es,
        'committed_poststate_event_count':case['outcome']=='commit' and state==es and len(events)==len(ee),
        'committed_poststate_event_bag':case['outcome']=='commit' and state==es and Counter(map(tuple,events))==Counter(map(tuple,ee)),
    }

def main():
    data=Path(sys.argv[1]).read_bytes()
    arr=json.loads(data)
    assert len(arr)==24 and len({a['id'] for a in arr})==len(arr)
    results={}
    for case in arr:
        pair={eng:native(case,eng) for eng in ('SQLite','DuckDB')}
        assert pair['SQLite']==pair['DuckDB'],case['id']
        results[case['id']]={eng:observe(case,got) for eng,got in pair.items()}
    print(json.dumps({'versions':{'SQLite':sqlite3.sqlite_version,'DuckDB':duckdb.__version__},
      'case_sha256':hashlib.sha256(data).hexdigest(),'cases':results},sort_keys=True,indent=2))
if __name__=='__main__': main()
