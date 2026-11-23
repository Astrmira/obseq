import sqlite3,pathlib,tempfile,sys,json
from zipfile import ZipFile
from xml.etree import ElementTree as E
import openpyxl as xl,pandas as pd
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def sqlite(case,mode,p):
 def attach(epoch):
  d=sqlite3.connect(p)
  d.create_function('score',2,lambda a,b:a+epoch*b,deterministic=True)
  return d
 d=attach(0);d.execute('create table t(id integer primary key,g integer,b integer,s integer,v integer as(score(b,s)) stored)')
 d.executemany('insert into t(id,g,b,s) values(?,?,?,?)',case['inputs']);d.commit();d.close()
 d=attach(case['epoch'])
 raw=d.execute('select id,g,b,s from t order by 1').fetchall()
 d.execute('create temp table quota(g integer primary key,k integer)')
 d.executemany('insert into quota values(?,?)',((int(g),k) for g,k in case['quotas'].items()))
 v='v' if mode=='default' else 'score(b,s)'
 q=f'select id from (select id,g,row_number() over(partition by g order by {v} desc,id) n from t) join quota using(g) where n<=k'
 ids=[i for i, in d.execute(q)]
 scores=d.execute(f'select id,{v} from t order by 1').fetchall();d.close()
 return dict(input=raw,scores=scores,ids=ids,versions={'sqlite':sqlite3.sqlite_version})
def xlsx(case,mode,p):
 w=xl.Workbook();s=w.active;s.append(['id','g','b','s','v'])
 for row,r in enumerate(reversed(case['inputs']),2):s.append(r+[f'=C{row}+0*D{row}'])
 raw=p.with_suffix('.draft.xlsx');w.save(raw)
 with ZipFile(raw) as zi,ZipFile(p,'w') as zo:
  for n in zi.namelist():
   z=zi.read(n)
   if n=='xl/worksheets/sheet1.xml':
    t=E.fromstring(z)
    for row,r in enumerate(reversed(case['inputs']),2):t.find(f".//s:c[@r='E{row}']/s:v",NS).text=str(r[2])
    z=E.tostring(t)
   zo.writestr(n,z)
 w=xl.load_workbook(p,read_only=True,data_only=True)
 rows=list(w.active.iter_rows(min_row=2,values_only=True));w.close()
 raw=sorted(r[:4] for r in rows)
 d=pd.DataFrame(rows,columns=['id','g','b','s','v'])
 if mode=='correct':d['v']=d['b']+case['epoch']*d['s']
 q={int(g):k for g,k in case['quotas'].items()}
 d=d.sort_values(['g','v','id'],ascending=[True,False,False]);sel=d[d.groupby('g').cumcount()<d['g'].map(q)]
 return dict(input=raw,scores=d.sort_values('id')[['id','v']].values.tolist(),ids=sel['id'].tolist(),versions={'openpyxl':xl.__version__,'pandas':pd.__version__})
def main():
 case,mode=json.load(sys.stdin)
 with tempfile.TemporaryDirectory() as t:
  r=sqlite(case,mode,pathlib.Path(t)/'test.db') if case['route']=='sqlite_rank' else xlsx(case,mode,pathlib.Path(t)/'test.xlsx')
 print(json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
