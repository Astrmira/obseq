import datetime as D,calendar,tempfile,sqlite3,json,hashlib
from pathlib import Path
import pandas as pd,openpyxl as xl
m=json.load(open('manifest.json'));assert m['schema']=='monthly-recurrence/v1'
def length_after(t,n):
 y,j=divmod(12*t.year+t.month-1+n,12)
 return y,j+1,calendar.monthrange(y,j+1)[1]
def independent(t,n):
 y,j,l=length_after(t,n)
 return D.date(y,j,min(t.day,l)).isoformat()
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp)/'input.xlsx';w=xl.Workbook();s=w.active
 s.append(['id','immutable_anchor'])
 for i,text in enumerate(m['anchors']):s.append([i,D.date.fromisoformat(text)])
 w.save(p);w=xl.load_workbook(p,read_only=True,data_only=True)
 rows=list(w.active.iter_rows(min_row=2,values_only=True));w.close()
out={}
with sqlite3.connect(':memory:') as db:
 for idx,anchor in rows:
  t=anchor.date();assert t.isoformat()==m['anchors'][idx]
  pandas_t=pd.Timestamp(t);previous=t.isoformat()
  day_so_far=t.day;disjoint=[];ceiling=[]
  for n in range(1,m['slots']+1):
   exp=independent(t,n)
   direct,default,chain=db.execute(
    "select date(?,?,'floor'),date(?,?),date(?,'+1 month','floor')",
    (t.isoformat(),f'+{n} months',t.isoformat(),f'+{n} months',previous)).fetchone()
   native=(pandas_t+pd.DateOffset(months=n)).date().isoformat()
   y,j,l=length_after(t,n);day_so_far=min(day_so_far,l)
   assert chain==D.date(y,j,day_so_far).isoformat()
   assert direct==native==exp
   if chain!=exp:disjoint.append(n)
   if default!=exp:ceiling.append(n)
   previous=chain
  out[t.isoformat()]={'chain_false_slots':disjoint,'sqlite_default_false_slots':ceiling}
assert sum(len(r['chain_false_slots']) for r in out.values())>sum(len(r['sqlite_default_false_slots']) for r in out.values())>0
print(json.dumps({'openpyxl':xl.__version__,'pandas':pd.__version__,'sqlite':sqlite3.sqlite_version,
 "manifest_sha256":hashlib.sha256(json.dumps(m,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"slot_checks":len(rows)*m['slots'],'cases':out},sort_keys=True,indent=2))
