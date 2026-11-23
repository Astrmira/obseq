import openpyxl as x
from openpyxl.worksheet.formula import ArrayFormula,DataTableFormula
from zipfile import ZipFile
from xml.etree import ElementTree as E
from pathlib import Path
from tempfile import TemporaryDirectory
import itertools,json
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def fixture(kind):
 w=x.Workbook();s=w.active
 s['A1']=3;s['B1']=4;s['C1']=ArrayFormula('C1:D3','=A1:B3*2') if kind=='array' else DataTableFormula('C1:D3',dt2D=True,r1='A1',r2='B1')
 for i,(r,c) in enumerate(itertools.product(range(1,4),[3,4]),10):
  if (r,c)!=(1,3):s.cell(r,c,i)
 return w
def obs(w,p):
 w.save(p)
 with ZipFile(p) as z:t=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
 fs={};vs={}
 for c in t.findall('.//s:c',NS):
  f=c.find('s:f',NS);r=c.get('r')
  if f is not None:fs[r]=[f.attrib,f.text]
  elif c.find('s:v',NS) is not None:vs[r]=int(c.find('s:v',NS).text)
 return fs,vs
def rectangle(points):
 xs,ys=zip(*points)
 return len(points)==(max(xs)-min(xs)+1)*(max(ys)-min(ys)+1)
S=set(itertools.product(range(1,4),range(3,5)))
whole={(i+5,j+3) for i,j in S};partial={(1+5,3+3)}|(S-{(1,3)})
assert rectangle(whole) and not rectangle(partial)
out={}
with TemporaryDirectory() as d:
 p=Path(d)/'test.xlsx'
 for kind in ['array','table']:
  baseline=obs(fixture(kind),p);basef,basev=baseline
  for mode in ['whole-off','whole-on','whole-repaired','split-anchor']:
   w=fixture(kind);s=w.active;err=None
   try:s.move_range('C1:C1' if mode=='split-anchor' else 'C1:D3',rows=5,cols=3,translate=mode=='whole-on')
   except TypeError as e:err=str(e)
   if mode=='whole-repaired':s['F6'].value.ref='F6:G8'
   fs,vs=obs(w,p)
   assert set(fs)=={'F6'} and fs['F6'][0]['ref']==('F6:G8' if mode=='whole-repaired' else 'C1:D3')
   assert fs['F6'][1]==basef['C1'][1] and {k:v for k,v in fs['F6'][0].items() if k!='ref'}=={k:v for k,v in basef['C1'][0].items() if k!='ref'}
   assert (err is not None)==(mode=='whole-on')
   if mode=='whole-on':assert (fs,vs)!=baseline
   occupied={a for a in vs if a not in ('A1','B1')}|set(fs)
   assert occupied==({'F6','D1','C2','D2','C3','D3'} if mode=='split-anchor' else {'F6','D1' if mode=='whole-on' else 'G6','F7','G7','F8','G8'}), (kind,mode,occupied)
   out[kind+'/'+mode]={'err':err,'formula':fs,'occupied':sorted(occupied)}
print(json.dumps({'openpyxl':x.__version__,'cases':out},sort_keys=True,indent=2))
