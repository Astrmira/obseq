import argparse, pathlib, json, tempfile, subprocess, re
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import openpyxl as xl
from openpyxl.utils.cell import get_column_letter as letter,column_index_from_string as column
from openpyxl.worksheet.cell_range import CellRange
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REF=r'\$?[A-Z]{1,3}\$?[1-9][0-9]{0,6}'
BODY=re.compile(r'='+REF+r'(?:[+-]'+REF+r')*\Z')
TOKEN=re.compile(r'(\$?)([A-Z]{1,3})(\$?)([1-9][0-9]{0,6})')
def parts(m):
 c=column(m[2]);r=int(m[4])
 if c>16384 or r>1048576:raise ValueError('invalid-address')
 return r,c
def retarget(text,src,dr,dc):
 if not BODY.fullmatch(text):raise ValueError('unsupported-formula')
 def f(m):
  r,c=parts(m)
  if (r,c) not in src:return m[0]
  return f'{m[1]}{letter(c+dc)}{m[3]}{r+dr}'
 return TOKEN.sub(f,text)
def cells_range(r):
 b=CellRange(r)
 if b.title is not None:raise ValueError('qualified-range')
 return {(i,j) for i in range(b.min_row,b.max_row+1) for j in range(b.min_col,b.max_col+1)}
def snapshot(s):return {(r,c):cell.value for (r,c),cell in s._cells.items() if cell.value is not None}
def preflight(w,ref,dr,dc):
 if len(w.worksheets)!=1:raise ValueError('multi-sheet')
 s=w.active
 if s.merged_cells.ranges or s.tables or s.auto_filter.ref or s.conditional_formatting or s.data_validations.dataValidation or w.defined_names or s.defined_names:
  raise ValueError('unqualified-feature')
 old=snapshot(s);src=cells_range(ref);dst={(r+dr,c+dc) for r,c in src}
 if src&dst or dst&old.keys() or any(not(1<=r<=1048576 and 1<=c<=16384) for r,c in dst):raise ValueError('invalid-destination')
 expect={};formula_deps={}
 for (r,c),v in old.items():
  target=(r+dr,c+dc) if (r,c) in src else (r,c)
  if not isinstance(v,str):
   if type(v)!=int:raise ValueError('unqualified-scalar')
  else:
   repaired=retarget(v,src,dr,dc)
   deps={parts(m) for m in TOKEN.finditer(v)}
   if deps&dst:raise ValueError('preexisting-destination-reference')
   formula_deps[r,c]=deps
   v=repaired
  expect[target]=v
 seen=set();active=set()
 def go(x):
  if x in active:raise ValueError('cyclic-formula')
  if x in seen or x not in formula_deps:return
  active.add(x)
  for leaf in formula_deps[x]:go(leaf)
  active.remove(x);seen.add(x)
 for x in formula_deps:go(x)
 return expect
def repair(w,ref,dr,dc):
 expected=preflight(w,ref,dr,dc);s=w.active
 s.move_range(ref,rows=dr,cols=dc,translate=False)
 for (r,c),v in expected.items():
  if isinstance(v,str):s.cell(r,c).value=v
 assert snapshot(s)==expected
def fill(s):
 for a,b in {'B2':2,'H10':13,'C2':'=$B2+B$2+$B$2+H10','C3':'=B3+$H$10',
            'D4':'=C$2+$C2+$C$2+B2','J2':'=$C3-H10'}.items():s[a]=b
def geometry(p):
 with ZipFile(p) as z:t=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
 return {c.get('r'):f.text for c in t.findall('.//s:c',NS) if (f:=c.find('s:f',NS)) is not None}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--consumer',action='store_true');args=ap.parse_args()
 patched={'F6':'$E6+E$6+$E$6+H10','F7':'E7+$H$10','D4':'F$6+$F6+$F$6+E6','J2':'$F7-H10'}
 out={}
 with tempfile.TemporaryDirectory() as d:
  d=pathlib.Path(d)
  for mode in ('baseline','off','on','repair'):
   w=xl.Workbook();fill(w.active)
   if mode in ('off','on'):w.active.move_range('B2:C3',rows=4,cols=3,translate=mode=='on')
   if mode=='repair':repair(w,'B2:C3',4,3)
   p=d/(mode+'.xlsx');w.save(p)
   out[mode]=geometry(p)
  assert out['repair']==patched and out['on']!=patched and out['off']!=patched
  assert out['on']['F6']=='$B6+E$2+$B$2+K14' and out['on']['D4']==out['baseline']['D4']
  blocked={}
  fixtures={'range':('A1','=SUM(B2:C3)','unsupported-formula'),
            'blank-dest-inbound':('A1','=E6','preexisting-destination-reference'),
            'cycle':('B2','=C2','cyclic-formula'),
            'array':('A1',xl.worksheet.formula.ArrayFormula('A1:A2','=B2:B3'),'unqualified-scalar')}
  for k,(host,f,why) in fixtures.items():
   w=xl.Workbook();fill(w.active);w.active[host]=f;before=snapshot(w.active)
   try:repair(w,'B2:C3',4,3)
   except ValueError as e:
    assert str(e)==why and snapshot(w.active)==before;blocked[k]=why
   else:raise AssertionError(k)
  consumers={}
  if args.consumer:
   p=d/'compare.xlsx'
   wb=xl.load_workbook(d/'repair.xlsx');sh=wb.active;sh.title='Patched';base=wb.create_sheet('Original');fill(base);wb.save(p)
   rec=d/'native';rec.mkdir()
   subprocess.run(['soffice','-env:UserInstallation='+(d/'profile').as_uri(),
    '--headless','--convert-to','xlsx','--outdir',str(rec),str(p)],check=True,capture_output=True,timeout=100)
   nb=xl.load_workbook(rec/'compare.xlsx',data_only=True)
   consumers={kind:[nb[kind][a].value for a in addrs] for kind,addrs in
              [('Original',('C2','C3','D4','J2')),('Patched',('F6','F7','D4','J2'))]}
   assert consumers['Original']==consumers['Patched']==[19,13,59,0]
 print(json.dumps({'openpyxl':xl.__version__,'formulas':out,'blocked_without_mutation':blocked,**({'cached':consumers} if args.consumer else {})},indent=2,sort_keys=True))
if __name__=='__main__':main()
