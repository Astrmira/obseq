"""Local native PostgreSQL expression and generated provenance; raw source stays local."""
from pathlib import Path
import argparse,csv,hashlib,json,re,subprocess
from collections import defaultdict
from datetime import datetime
from tempfile import TemporaryDirectory
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
COL="tpep_pickup_datetime"
LOW=datetime(2025,11,2,0,30)
HIGH=datetime(2025,11,2,4,30)

def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def safe(p):return "'"+str(p).replace("'","''")+"'"

def run(cmd,input=None):
    r=subprocess.run([str(x) for x in cmd],input=input,text=True,capture_output=True,timeout=150)
    errors=sum(e in r.stderr for e in ("ERROR:","FATAL:","PANIC:"))
    assert r.returncode==0 and errors==0,(r.returncode,errors,r.stderr[-1500:])
    return r.stdout

def fun(delta):
    return f"""CREATE OR REPLACE FUNCTION slot15(t timestamp) RETURNS integer LANGUAGE plpgsql IMMUTABLE STRICT AS $$ BEGIN RETURN (extract(hour FROM t)::integer*4 + extract(minute FROM t)::integer/15 + {delta}) % 96; END $$;"""

def sqlcase(keys,file):
    sql=[fun(0),"""CREATE UNLOGGED TABLE events(rid bigint primary key,
       pickup timestamp NOT NULL, bin integer GENERATED ALWAYS AS (slot15(pickup)) STORED);""".replace("\n"," "),
       f"COPY events(rid,pickup) FROM {safe(file)} WITH (FORMAT csv);",
       "CREATE INDEX idx_eval on events(slot15(pickup));",
       "CREATE INDEX idx_stored on events(bin);",
       "ANALYZE events;"]
    for phase,action in enumerate((None,fun(1),
        "REINDEX INDEX idx_eval; REINDEX INDEX idx_stored;",
        "ALTER TABLE events ALTER COLUMN bin SET EXPRESSION AS (slot15(pickup));",fun(0),
        "ALTER TABLE events ALTER COLUMN bin SET EXPRESSION AS (slot15(pickup));")):
        if action:sql.append(action)
        sql += ["SET enable_indexscan=off;","SET enable_bitmapscan=off;","SET enable_seqscan=on;"]
        group="SELECT slot15(pickup) k,rid FROM events"
        sql.append(f"""SELECT encode(convert_to(q::text,'UTF8'),'hex') AS phase{phase}seq
          FROM (SELECT jsonb_object_agg(k,v) q FROM
          (SELECT k,array_agg(rid ORDER BY rid) v FROM ({group}) t GROUP BY k) bag) guard;""".replace("\n"," "))
        sql += ["SET enable_indexscan=on;","SET enable_bitmapscan=off;","SET enable_seqscan=off;"]
        for name,key in (("expr","slot15(pickup)"),("stored","bin")):
            sql.append(f"SELECT 'plan_{phase}_{name}' AS marker;")
            sql.append(f"EXPLAIN (COSTS OFF) SELECT rid FROM events WHERE {key}={keys[0]};")
            for keyval in keys:
                sql.append(f"SELECT coalesce(string_agg(rid::text,',' ORDER BY rid),'') AS p{phase}{name}_{keyval} FROM events WHERE {key}={keyval};")
    return "\n".join(sql)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument('file',type=Path);p.add_argument('bin',type=Path);p.add_argument('scratch',type=Path)
    a=p.parse_args()
    for line in (ROOT/'PRE.sha256').read_text().splitlines():
        h,n=line.split();assert digest(ROOT/n)==h
    assert digest(a.file)==(ROOT/'SOURCE.sha256').read_text().split()[0]
    assert pa.__version__=="26.0.1"
    T=pq.read_table(a.file,columns=[COL],filters=[(COL,">=",LOW),(COL,"<",HIGH)]).column(0)
    assert T.type==pa.timestamp("us")
    old=defaultdict(list);new=defaultdict(list)
    ver=run([a.bin/'postgres','--version']).strip()
    assert '17.12' in ver
    with TemporaryDirectory(prefix='eab-native-derived-',dir=a.scratch) as path:
        work=Path(path)
        f=work/'src.csv';target=work/'cluster'
        with f.open("w",newline="") as stream:
            writer=csv.writer(stream)
            for rid,t in enumerate(T.to_pylist()):
                assert LOW<=t<HIGH
                k=t.hour*4+t.minute//15
                old[k].append(rid);new[(k+1)%96].append(rid)
                writer.writerow([rid,t.isoformat(sep=" ",timespec="microseconds")])
        keys=sorted(set(old)|set(new))
        cluster=[a.bin/'initdb','--no-sync','--locale=C.UTF-8','--encoding=UTF8',
                 '--auth-local=peer','--auth-host=scram-sha-256','-D',target]
        run(cluster)
        out=run([a.bin/'postgres','--single','-D',target,
                 '-c','shared_buffers=32MB','-c','work_mem=16MB','-c','jit=off','postgres'],
                sqlcase(keys,f))
    # Native streams may contain source ordinals, so only categorical plan data leaves memory.
    obs=dict(re.findall(r'\b(phase[0-5]seq|p[0-5](?:expr|stored)_\d+) = "([^"]*)"',out))
    plans={}
    for phase,n in enumerate(("v1_baseline","v2_replace_function","v2_reindex_both","v2_rewrite_generated",
                              "v1_replace_again","v1_direct_rewrite_without_reindex")):
        seq=json.loads(bytes.fromhex(obs[f'phase{phase}seq']).decode())
        assert {int(k):v for k,v in seq.items()}==({**old} if phase in (0,4,5) else {**new})
        target=old if phase in (0,4,5) else new
        row=dict(phase=n,plain_seq_current_by_all_ids=True)
        for name,idx in (("expr","idx_eval"),("stored","idx_stored")):
            plan=out.split('marker = "plan_'+str(phase)+'_'+name+'"',1)[1].split('backend> ',2)[1]
            assert ('using '+idx+' on events') in plan,(phase,name)
            got={k:(list(map(int,raw.split(','))) if (raw:=obs[f'p{phase}{name}_{k}']) else []) for k in keys}
            expected=old if phase in (0,5) or (name=='expr' and phase==1) or (name=='stored' and phase in (1,2)) else new
            assert all(got[k]==expected.get(k,[]) for k in keys),(phase,name)
            row[name]={'native_index':idx,
                       'wrong_bucket_memberships':sum(len(set(got[k])-set(target.get(k,[]))) for k in keys),
                       'missing_bucket_memberships':sum(len(set(target.get(k,[]))-set(got[k])) for k in keys)}
        plans[n]=row
    print(json.dumps(dict(input_rows=len(T),bucket_queries_per_index=len(keys), PostgreSQL=ver,
          native_phases=plans),indent=2,sort_keys=True))

if __name__=="__main__":main()
