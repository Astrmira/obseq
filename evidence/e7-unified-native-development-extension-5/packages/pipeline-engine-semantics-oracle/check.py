"""SQLite+Python oracles, pandas native and contract adapters on composite joins."""
import itertools as it, json, sqlite3
import pandas as pd

def make(rows,side,typed):
 f=pd.DataFrame({side:range(len(rows))})
 for j,k in enumerate("xy"):
  v=[row[j] for row in rows]
  f[k]=pd.array(pd.Series(v,dtype=object),dtype="Int64") if typed else v
 return f
def join(L,R,filter_ordinary):
 for k in filter_ordinary:L=L[L[k].notna()];R=R[R[k].notna()]
 j=L.merge(R,on=["x","y"])
 z=set(zip(j.l,j.r)); assert len(z)==len(j)
 return z
def sql(L,R,safe):
 with sqlite3.connect(":memory:") as d:
  for t,rows in (("L",L),("R",R)):
   d.execute(f"create table {t}(id integer primary key,x integer,y integer)")
   d.executemany(f"insert into {t} values(?,?,?)",((i,*r) for i,r in enumerate(rows)))
  p=" and ".join(f"L.{k} {'is not distinct from' if b else '='} R.{k}" for k,b in zip("xy",safe))
  got=set(d.execute(f"select L.id,R.id from L join R on {p}"))
 assert got=={(i,j) for i,l in enumerate(L) for j,r in enumerate(R) if
  all(a==b and (a is not None or nullsafe) for a,b,nullsafe in zip(l,r,safe))}
 return got
def suites():
 for a,b in it.product([0,2**53],[-2**53,0]):
  base=list(it.product((a,a+1,None),(b,b-1,None)))
  for u,v in [(0,0),(1,3),(4,2)]:
   yield base[u:]+[base[0],base[-1]],base[v:]+[base[0]]
def main():
 out={}
 for safe in it.product((False,True),repeat=2):
  code="".join("N" if k else "=" for k in safe)
  ordinary=[k for k,b in zip("xy",safe) if not b]
  case={}
  for mode,typed,filter_set in [
   ("default",False,[]),("typed-only",True,[]),("drop-all",True,list("xy")),
   ("typed-exact-policy",True,ordinary),("default-exact-policy",False,ordinary)]:
   fp=fn=0; example=None
   for L,R in suites():
    expect=sql(L,R,safe); got=join(make(L,"l",typed),make(R,"r",typed),filter_set)
    wrong=sorted(got-expect); missing=sorted(expect-got)
    fp+=len(wrong);fn+=len(missing)
    if example is None and (wrong or missing):
     example={"false_pair_keys":[L[wrong[0][0]],R[wrong[0][1]]] if wrong else None,
              "missing_pair_keys":[L[missing[0][0]],R[missing[0][1]]] if missing else None}
   case[mode]={"fp":fp,"fn":fn,"first":example}
  assert [case["typed-exact-policy"][k] for k in ("fp","fn")]==[0,0]
  assert (case["drop-all"]["fn"]>0)==any(safe) and case["drop-all"]["fp"]==0
  assert (case["typed-only"]["fp"]>0)==(not all(safe)) and case["typed-only"]["fn"]==0
  assert case["default-exact-policy"]["fp"]>0
  out[code]=case
 print(json.dumps({"cases":len(list(suites())),"operators":out,"versions":{"pandas":pd.__version__,"sqlite":sqlite3.sqlite_version}},indent=2,sort_keys=True))
if __name__=="__main__":main()
