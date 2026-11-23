import openpyxl as x
from tempfile import TemporaryDirectory
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
import json,itertools
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def patch(src,dst,dim,trim=False):
 with ZipFile(src) as a,ZipFile(dst,'w') as b:
  for n in a.namelist():
   data=a.read(n)
   if n=='xl/worksheets/sheet1.xml':
    t=E.fromstring(data);d=t.find('s:dimension',NS)
    if dim is None:t.remove(d)
    else:d.set('ref',dim)
    # Author one known cached numeric value without recalculating it.
    for c in t.findall('.//s:c',NS):
     if c.get('r')=='J30':c.find('s:v',NS).text='7'
    if trim:
     table=t.find("s:sheetData",NS)
     for row in list(table):
      if int(row.get("r"))>10:table.remove(row)
      else:
       for c in list(row):
        if c.get("r").startswith("K"):row.remove(c)
    data=E.tostring(t)
   b.writestr(n,data)
def decode(p,readonly,data,repair):
 b=x.load_workbook(p,read_only=readonly,data_only=data);s=b.active
 if repair:s.reset_dimensions()
 obs={}; cells=0;rows=0
 for i,row in enumerate(s.iter_rows(),1):
  rows+=1;cells+=len(row)
  for j,c in enumerate(row,1):
   if c.value is not None:obs[f'{i},{j}']=c.value
 b.close()
 return dict(rows=rows,cells=cells,observed=obs)
def main():
 with TemporaryDirectory() as tmp:
  d=Path(tmp);s=d/'source.xlsx'
  w=x.Workbook();sheet=w.active
  for coord,v in [('A1','anchor'),('B4',0),('D9',3),('K10','wide'),('C38','late'),('J30','=D9+4')]:
   sheet[coord]=v
  # Cache guard must also count formula-only cells with an unset cache.
  sheet['N42']='=NA()'
  w.save(s)
  results={}
  for dim in ['A1:N42','A1:D10','A1:L20','D10:N42','A1:Z55',None]:
   p=d/'test.xlsx';patch(s,p,dim)
   modes={}
   for data in [False,True]:
    ref=decode(p,False,data,False); default=decode(p,True,data,False);repaired=decode(p,True,data,True)
    exp={'1,1':'anchor','4,2':0,'9,4':3,'10,11':'wide','38,3':'late','30,10':7 if data else '=D9+4'}
    if not data:exp['42,14']='=NA()'
    assert ref['observed']==repaired['observed']==exp
    clipped=sorted(exp.keys()-default['observed'].keys())
    should=dim in ['A1:D10','A1:L20']
    assert bool(clipped)==should and all(exp[i]==v for i,v in default['observed'].items())
    modes['values' if data else 'formula']={'clipped':clipped,'default_rows':default['rows'],'default_cells':default['cells'],'repair_rows':repaired['rows'],'repair_cells':repaired['cells']}
   results[str(dim)]=modes
  full=d/"full.xlsx"; trimmed=d/"trimmed.xlsx"
  patch(s,full,"A1:D10");patch(s,trimmed,"A1:D10",True)
  for data in [False,True]:
   assert decode(full,True,data,False)==decode(trimmed,True,data,False)
   assert decode(full,True,data,True)["observed"]!=decode(trimmed,True,data,True)["observed"]
 print(json.dumps({'openpyxl':x.__version__,'cases':results},sort_keys=True,indent=2))
if __name__=='__main__':main()
