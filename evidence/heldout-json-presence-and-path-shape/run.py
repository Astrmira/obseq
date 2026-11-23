"""Predict authored answers from native SQLite, DuckDB and PostgreSQL JSON traversal."""
from pathlib import Path
import hashlib, json, re, sqlite3, subprocess, sys, tempfile
import duckdb

casepath,pg,scratch=map(Path,sys.argv[1:])
raw=json.loads(casepath.read_text()); cases=raw if isinstance(raw,list) else raw["cases"]
def inputs(c):
    text=c.get("json_text",c.get("json",c.get("input_json",c.get("document"))))
    path=c["path"]
    assert isinstance(text,str)
    assert isinstance(path,list) and all(isinstance(s,dict) and (set(s)=={"key"} and isinstance(s["key"],str) or set(s)=={"index"} and type(s["index"]) is int and 0<=s["index"]<2**31) for s in path)
    return text,path
def bad(status,i):
    return dict(status=status,step=i)
def terminal(node,t):
    if t=="null": return bad("explicit-null",None)
    return dict(status="value",step=None,value=json.loads(node))
sq=sqlite3.connect(":memory:")
dd=duckdb.connect(config={"threads":1})
def navigate(node,steps,engine):
    if engine=="sqlite":
        t=lambda j:sq.execute("select json_type(?)",[j]).fetchone()[0]
        query="""select case type when 'text' then json_quote(value) when 'null' then 'null'
            when 'true' then 'true' when 'false' then 'false' else cast(value as text) end
            from json_each(?) where key=?"""
        read=lambda j,k:sq.execute(query,[j,k]).fetchone()
    else:
        t=lambda j:dd.execute("select lower(json_type(?::JSON))",[j]).fetchone()[0]
        read=lambda j,k:dd.execute("select value from json_each(?::JSON) where key=?",[j,str(k)]).fetchone()
    for i,step in enumerate(steps):
        key="key" in step
        if t(node)!=("object" if key else "array"): return bad("wrong-container",i)
        match=read(node,step["key" if key else "index"])
        if match is None: return bad("missing-key" if key else "missing-index",i)
        node=match[0]
        assert isinstance(node,str)
    return terminal(node,t(node))
def invoke(cmd,sql=None):
    r=subprocess.run([str(x) for x in cmd],input=sql,text=True,capture_output=True,timeout=50)
    assert r.returncode==0 and not any(e in r.stderr for e in ("ERROR:","FATAL:","PANIC:")),r.stderr[-2000:]
    return r.stdout
def lit(v):
    assert isinstance(v,str) and "\x00" not in v
    return "'"+v.replace("'","''")+"'"
def plan(name,node,steps):
    ctes=[f"n0(node,problem,step) AS (VALUES ({lit(node)}::jsonb,NULL::text,NULL::int))"]
    for i,s in enumerate(steps):
        t,k,f=("object",lit(s["key"])+"::text","missing-key") if "key" in s else ("array",str(s["index"])+"::int","missing-index")
        old=f"n{i}"; child=f"node -> {k}"; wrong=f"jsonb_typeof(node) IS DISTINCT FROM '{t}'"
        cond=f"({wrong} OR ({child}) IS NULL)"
        ctes.append(f"""n{i+1} AS (
          SELECT CASE WHEN problem IS NOT NULL OR {wrong} THEN NULL::jsonb ELSE {child} END AS node,
           CASE WHEN problem IS NOT NULL THEN problem WHEN {wrong} THEN 'wrong-container' WHEN ({child}) IS NULL THEN '{f}' ELSE NULL END AS problem,
           CASE WHEN problem IS NOT NULL THEN step WHEN {cond} THEN {i} ELSE NULL END AS step FROM {old})""".replace("\n"," "))
    status="coalesce(problem,case when jsonb_typeof(node)='null' then 'explicit-null' else 'value' end)"
    as_json=f"""(jsonb_build_object('status',{status},'step',step) ||
       case when problem is null and jsonb_typeof(node)<>'null' then jsonb_build_object('value',node) else '{{}}'::jsonb end)""".replace("\n"," ")
    return f"WITH {','.join(ctes)} SELECT encode(convert_to(({as_json})::text,'UTF8'),'hex') AS {name} FROM n{len(steps)};"
records=[]
for idx,c in enumerate(cases):
    text,path=inputs(c)
    s,d=navigate(text,path,"sqlite"),navigate(text,path,"duckdb")
    records.append(dict(id=c.get("id",c.get("case_id",idx)),sqlite=s,duckdb=d))
with tempfile.TemporaryDirectory(prefix="e7-json-",dir=scratch) as w:
    dat=Path(w)/"pg"
    ver=invoke([pg/"postgres","--version"]).strip()
    invoke([pg/"initdb","--no-sync","--locale=C.UTF-8","--encoding=UTF8","--auth-local=peer","--auth-host=scram-sha-256","-D",dat])
    sql="SET standard_conforming_strings=on;\n"+"\n".join(plan(f"case_{i}",*inputs(c)) for i,c in enumerate(cases))+"\n"
    out=invoke([pg/"postgres","--single","-D",dat,"-c","shared_buffers=32MB","-c","jit=off","postgres"],sql)
    result={int(k):json.loads(bytes.fromhex(h)) for k,h in re.findall(r'case_([0-9]+) = "([a-f0-9]+)"',out)}
    assert len(result)==len(records)
for idx,r in enumerate(records):
    r['postgres']=result[idx]
    samples=[json.dumps(r[k],sort_keys=True) for k in ("sqlite","duckdb","postgres")]
    assert len(set(samples))==1, (r["id"],samples)
print(json.dumps(dict(versions=dict(duckdb=duckdb.__version__,sqlite=sqlite3.sqlite_version,postgres=ver),
    cases_sha256=hashlib.sha256(casepath.read_bytes()).hexdigest(),predictions=records),sort_keys=True,indent=2,ensure_ascii=False))
