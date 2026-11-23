import openpyxl as x
from openpyxl.worksheet.formula import ArrayFormula,DataTableFormula
from openpyxl.utils.cell import range_boundaries,get_column_letter
from pathlib import Path
from tempfile import TemporaryDirectory
import json,itertools
from zipfile import ZipFile
from xml.etree import ElementTree as ET
def coords(ref):
 a,b,c,d=range_boundaries(ref)
 return set(itertools.product(range(b,d+1),range(a,c+1)))
def fmt(points):
 r,c=zip(*points)
 return f'{get_column_letter(min(c))}{min(r)}:{get_column_letter(max(c))}{max(r)}'
def gid(obj):return type(obj).__name__
def source(p):
 w=x.Workbook();s=w.active
 s['K1']=1;s['L1']=2
 s['B2']=ArrayFormula('B2:C3','=K1:L2*2')
 s['C3']=7
 s['F2']=DataTableFormula('F2:G3',dt2D=True,r1='K1',r2='L1')
 s['G3']=9;s['A4']=17
 w.save(p)
def snapshot(w):
 s=w.active
 return {(r,c):(gid(cell.value),dict(vars(cell.value))) if isinstance(cell.value,(ArrayFormula,DataTableFormula)) else cell.value
         for (r,c),cell in s._cells.items() if cell.value is not None}
def plan(before,ref,dr,dc):
 src=coords(ref);shift=lambda p:(p[0]+dr,p[1]+dc);dst={shift(p) for p in src}
 if any(not (1<=r<=1048576 and 1<=c<=16384) for r,c in dst):return 'out-of-bounds',{}
 if dst&src:return 'self-overlap',{}
 anchors={}
 for p,v in before.items():
  if isinstance(v,str) and v.startswith('='):return 'unqualified-formula',{}
  if isinstance(v,tuple):
   group=coords(v[1]['ref'])
   if src & group and not group<=src:return 'split-output',{}
   if dst&group:return 'destination-output',{}
   if p in src:anchors[p]=fmt({shift(q) for q in group})
 if dst&before.keys():return 'destination-content',{}
 # Both authored inputs are K1:L2. Ordinary formulas/other inputs were not qualified.
 if src&coords('K1:L2') and (dr or dc):return 'input-unqualified',{}
 return 'admitted',anchors
def proposed(snapshot_before,ref,dr,dc,anchors):
 S=coords(ref);out={}
 for p,value in snapshot_before.items():
  g=(p[0]+dr,p[1]+dc) if p in S else p
  if p in anchors:value=(value[0],dict(value[1],ref=anchors[p]))
  out[g]=value
 return out
def case(src,baseline,dst,requests,inject=False):
 w=x.load_workbook(src)
 result=[];model=snapshot(w)
 for i,(ref,dr,dc) in enumerate(requests):
  decision,anc=plan(model,ref,dr,dc);result.append(decision)
  if decision!='admitted':
   assert dst.read_bytes()==baseline
   return result
  s=w.active
  s.move_range(ref,rows=dr,cols=dc,translate=False)
  for (r,c),rr in anc.items():s.cell(r+dr,c+dc).value.ref=rr
  model=proposed(model,ref,dr,dc,anc)
  if inject and i==len(requests)-1:s['P20']=123
 tmp=dst.with_suffix('.staged.xlsx')
 w.save(tmp);reader=x.load_workbook(tmp)
 if snapshot(reader)!=model:
  assert dst.read_bytes()==baseline
  return result+['postcheck-rejected']
 tmp.replace(dst)
 assert snapshot(x.load_workbook(dst))==model
 return result+['committed']
arms={
 'whole-both':([('B2:C3',5,0),('F2:G3',5,0)],False,['admitted','admitted','committed']),
 'split':([('B2:B2',5,0)],False,['split-output']),
 'blank-dest-owned':([('A4:A4',-2,6)],False,['destination-output']),
 'overlap':([('B2:C3',1,0)],False,['self-overlap']),
 'oob':([('B2:C3',-4,0)],False,['out-of-bounds']),
 'unqualified-input':([('K1:L2',5,0)],False,['input-unqualified']),
 'late-preflight':([('B2:C3',5,0),('F2:F2',5,0)],False,['admitted','split-output']),
 'late-postcheck':([('B2:C3',5,0),('F2:G3',5,0)],True,['admitted','admitted','postcheck-rejected'])}
out={}
with TemporaryDirectory() as tmp:
 src=Path(tmp)/'source.xlsx';source(src);baseline=src.read_bytes()
 for k,(moves,inject,expected) in arms.items():
  p=Path(tmp)/(k+'.xlsx');p.write_bytes(baseline)
  states=case(src,baseline,p,moves,inject)
  assert states==expected
  assert (p.read_bytes()!=baseline)==(states[-1]=='committed')
  if states[-1]=='committed':
   with ZipFile(p) as z:
    t=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
   ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
   graph={c.get('r'):f.get('ref') for c in t.findall('.//s:c',ns) if (f:=c.find('s:f',ns)) is not None}
   assert graph=={'B7':'B7:C8','F7':'F7:G8'}
  out[k]=states
print(json.dumps({'openpyxl':x.__version__,'results':out},sort_keys=True,indent=2))
