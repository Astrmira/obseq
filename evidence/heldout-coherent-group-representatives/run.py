from pathlib import Path
import hashlib,json,re,sqlite3,subprocess,sys,tempfile
import duckdb
f,pg,scratch=map(Path,sys.argv[1:])
cases=json.loads(f.read_text())
assert isinstance(cases,list)
schema="""CREATE TABLE cohort(c VARCHAR PRIMARY KEY);
CREATE TABLE src(c VARCHAR,g VARCHAR,rid BIGINT,s BIGINT,d BIGINT,p BIGINT,t BIGINT, PRIMARY KEY(c,rid));
CREATE TABLE cand(c VARCHAR,g VARCHAR,rid BIGINT,s BIGINT,d BIGINT,p BIGINT,t BIGINT);"""
base="""WITH minima AS (SELECT c,g,min(s) ms FROM src WHERE s IS NOT NULL GROUP BY c,g),
scope AS (SELECT c,g,count(*) n FROM cand GROUP BY c,g),
missing AS (SELECT m.c,m.g FROM minima m LEFT JOIN scope z ON m.c=z.c AND m.g=z.g WHERE z.n IS NULL),
bad AS (SELECT w.c FROM cand w LEFT JOIN minima m ON w.c=m.c AND w.g=m.g
 WHERE w.s IS NULL OR m.ms IS NULL OR w.s<>m.ms OR NOT ({admit}))
 SELECT h.c, CASE WHEN
 NOT EXISTS (SELECT 1 FROM missing WHERE c=h.c) AND
 NOT EXISTS (SELECT 1 FROM scope WHERE c=h.c AND n<>1) AND
 NOT EXISTS (SELECT 1 FROM bad WHERE c=h.c) THEN 1 ELSE 0 END verdict
 FROM cohort h ORDER BY h.c"""
tied="x.c=w.c AND x.g=w.g AND x.s=m.ms"
payload=" AND ".join(f"x.{k} IS NOT DISTINCT FROM w.{k}" for k in ("d","p","t"))
queries={}
for k,expr in {
        'coupled':f"EXISTS (SELECT 1 FROM src x WHERE {tied} AND {payload} AND (w.rid IS NULL OR x.rid=w.rid))",
        'fixed_golden':f"EXISTS (SELECT 1 FROM src x WHERE {tied} AND {payload} AND (w.rid IS NULL OR x.rid=w.rid) "
                       "AND x.rid=(SELECT min(y.rid) FROM src y WHERE y.c=w.c AND y.g=w.g AND y.s=m.ms))",
        'marginal':" AND ".join(f"EXISTS (SELECT 1 FROM src x WHERE {tied} AND x.{f} IS NOT DISTINCT FROM w.{f})"
                                  for f in ("d","p","t"))}.items():
    queries[k]=base.format(admit=expr)
fields=("g","rid","s","d","p","t")
groups={'cohort':[],'src':[],'cand':[]}
for c in cases:
    name=c["id"]
    assert type(name) is str and "\x00" not in name
    groups["cohort"].append((name,))
    for group,key in (("src","source"),("cand","candidate")):
        for x in c[key]:
            assert set(x)==set(fields)
            assert type(x["g"]) is str and all(type(x[a]) is int or x[a] is None for a in fields[1:])
            assert x["rid"] is not None or group=="cand"
            groups[group].append((name,*[x[k] for k in fields]))
def native(db,key):
    for stmt in schema.split(';'):
        if stmt.strip():db.execute(stmt)
    for name,v in groups.items():
        if v:db.executemany(f"insert into {name} values ({','.join('?' for _ in v[0])})",v)
    return {m:{a:bool(b) for a,b in db.execute(q).fetchall()} for m,q in queries.items()}
a=native(duckdb.connect(config={'threads':1}),"duckdb")
b=native(sqlite3.connect(":memory:"),"sqlite")
def sqlit(x):
    if x is None:return 'NULL'
    if type(x) is int:return str(x)
    assert "\x00" not in x
    return "'"+x.replace("'","''")+"'"
def invoke(cmd,s=None):
    d=subprocess.run([str(x) for x in cmd],input=s,text=True,capture_output=True,timeout=45)
    assert d.returncode==0 and not any(x in d.stderr for x in ("ERROR:","FATAL:","PANIC:")),d.stderr[-1600:]
    return d.stdout
ver=invoke([pg/"postgres","--version"]).strip()
with tempfile.TemporaryDirectory(prefix="e7-o3-",dir=scratch) as t:
    dat=Path(t)/"pg"
    invoke([pg/"initdb","--no-sync","--locale=C.UTF-8","--encoding=UTF8","--auth-local=peer","--auth-host=scram-sha-256","-D",dat])
    inserts=[f"INSERT INTO {k} VALUES {','.join('('+','.join(sqlit(x) for x in row)+')' for row in rows)};"
              for k,rows in groups.items() if rows]
    outs=[f"SELECT encode(convert_to((jsonb_object_agg(c,verdict))::text,'UTF8'),'hex') AS {k} from ({q}) t;".replace("\n"," ")
          for k,q in queries.items()]
    batch="SET standard_conforming_strings=on;\n"+schema+"\n"+"\n".join(inserts+outs)+"\n"
    msg=invoke([pg/"postgres","--single","-D",dat,"-c","shared_buffers=32MB","-c","jit=off","postgres"],batch)
    c={m:{k:bool(v) for k,v in json.loads(bytes.fromhex(vals)).items()} for m,vals in re.findall(r'(coupled|fixed_golden|marginal) = "([a-f0-9]+)"',msg)}
assert a==b==c,(a,b,c)
print(json.dumps(dict(case_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),engine_versions=dict(duckdb=duckdb.__version__,
    postgres=ver,sqlite=sqlite3.sqlite_version),predictions=dict(duckdb=a,postgres=c,sqlite=b)),sort_keys=True,indent=2))
