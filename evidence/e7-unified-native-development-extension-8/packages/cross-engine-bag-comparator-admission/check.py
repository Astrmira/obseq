"""Native postgres --single, never listens; use an empty generated scratch cluster."""
import csv, hashlib, json, re, sqlite3, subprocess, sys, tempfile
from pathlib import Path

input_dir, pg, scratch=map(Path,sys.argv[1:])
def invoke(args, sql=None):
    q=subprocess.run([str(x) for x in args], input=sql,text=True,capture_output=True,timeout=45)
    assert q.returncode==0 and not any(s in q.stderr for s in ('ERROR:','FATAL:','PANIC:')),q.stderr[-2000:]
    return q.stdout
rows=[]
for ln in Path(__file__).with_name('INPUTS.sha256').read_text().splitlines():
    sha,name=ln.split()
    data=(input_dir/name).read_bytes(); assert hashlib.sha256(data).hexdigest()==sha
    rows.extend(map(int,data.splitlines()))
def f64(n):
    u=1<<max(n.bit_length()-53,0)
    q,r=divmod(n,u)
    return (q+((r*2>u) or (r*2==u and q%2!=0)))*u
changed=sum(x!=f64(x) for x in rows)
pairs={}
for v in set(rows): pairs.setdefault(f64(v),[]).append(v)
collisions=[ks for ks in pairs.values() if len(ks)>1]
assert len(collisions)==1
a,b=sorted(collisions[0])
with tempfile.TemporaryDirectory(prefix='native-bag-pg-',dir=scratch) as x:
    d=Path(x); c=d/'cluster'; src=d/'source.csv'
    with src.open('w',newline='') as f:
        csv.writer(f).writerows(enumerate(rows+[None],1))
    safe="'"+str(src).replace("'","''")+"'"
    setup=["CREATE TABLE src(pos BIGINT NOT NULL,id BIGINT);",
           f"COPY src(pos,id) FROM {safe} WITH (FORMAT csv);"]
    wanted={}
    def verdict(name, value, expected):
        setup.append(f'SELECT ({value}) AS {name};');wanted[name]=str(expected)
    def diff(name, a,b,exp,all_=True):
        q='EXCEPT ALL' if all_ else 'EXCEPT'
        for i,(l,r) in enumerate(((a,b),(b,a)),1):
            verdict(name+str(i),f'SELECT count(*) FROM (({l}) {q} ({r})) AS t', exp)
    origin='SELECT pos,id FROM src'; cast='SELECT pos,id::double precision AS id FROM src'
    lift='SELECT pos,id::double precision::bigint AS id FROM src'
    verdict('bound_common_type',f'SELECT pg_typeof(id)::text FROM (({origin}) UNION ALL ({cast})) t LIMIT 1','double precision')
    diff('native_mixed_',origin,cast,0)
    diff('exact_lift_',origin,lift,changed)
    verdict('native_mixed_eq_count','SELECT count(*) FROM src WHERE id=id::double precision',len(rows))
    verdict('exact_value_eq_count','SELECT count(*) FROM src WHERE id=id::double precision::bigint',len(rows)-changed)
    a3=f'SELECT * FROM (VALUES ({a}::bigint),({a}::bigint),({b}::bigint)) t(id)'
    b3=f'SELECT * FROM (VALUES ({a}::bigint),({b}::bigint),({b}::bigint)) t(id)'
    diff('native_multiset_dup_',a3,b3,1);diff('native_set_dup_',a3,b3,0,False)
    diff('exact_widening_',origin,'SELECT pos,id::numeric FROM src',0)
    diff('json_presence_',"""SELECT '{"id":41}'::jsonb j""","""SELECT '{"id":41,"memo":null}'::jsonb j""",1)
    version=invoke([pg/'postgres','--version']).strip()
    assert version.startswith('postgres (PostgreSQL) 17.')
    invoke([pg/'initdb','--no-sync','--locale=C.UTF-8','--encoding=UTF8',
            '--auth-local=peer','--auth-host=scram-sha-256','-D',c])
    out=invoke([pg/'postgres','--single','-D',c,'-c','shared_buffers=32MB','-c','work_mem=16MB',
                '-c','jit=off','postgres'],'\n'.join(setup)+'\n')
    obs={k:v for k,v in re.findall(r'\b([a-z_0-9]+) = "([^"]+)"',out) if k in wanted}
    assert obs==wanted,(obs,wanted)
# Untyped SQLite columns preserve each operand's storage class; ordinal is unique.
sq=sqlite3.connect(':memory:')
sq.execute('create table src(pos,id)')
sq.executemany('insert into src values (?,?)',enumerate(rows+[None],1))
orig='select pos,id from src'; narrowed='select pos,cast(id as real) id from src'
def sqlite_diff(a,b):
    return [sq.execute(f'select count(*) from ({l} EXCEPT {r})').fetchone()[0]
            for l,r in ((a,b),(b,a))]
mixed=sqlite_diff(orig,narrowed)
both_real=sqlite_diff(narrowed,narrowed)
assert mixed==[changed,changed] and both_real==[0,0]
grouped=sq.execute(f"""
with l as ({orig}),r as ({narrowed}),
all_values as (select pos,id,0 side from l union all select pos,id,1 side from r),
groups as (select pos,id,sum(side=0) nl,sum(side=1) nr from all_values group by pos,id)
select sum(max(nl-nr,0)),sum(max(nr-nl,0)) from groups
""").fetchone()
assert grouped==(changed,changed)
authored=sq.execute("""
with u(key) as (values (7),(7),(8)),v(key) as (values (7),(8),(8)),
bag as (select key,1 s from u union all select key,-1 from v),
g as (select key,sum(s) d from bag group by key)
select sum(max(d,0)),sum(max(-d,0)) from g
""").fetchone()
assert authored==(1,1)
print(json.dumps(dict(postgres_version=version,tweet_rows=len(rows),authored_null_rows=1,
    changed_exact_ids=changed,collision_classes=len(collisions),postgres_assertions=obs,
    sqlite=dict(version=sqlite3.sqlite_version,mixed_native_distinct_directions=mixed,
    mixed_grouped_bag_directions=grouped,duplicate_grouped_bag_directions=authored,
    explicit_both_real_distinct_directions=both_real)),sort_keys=True,indent=2))
