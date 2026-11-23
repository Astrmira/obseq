"""Prepare genuine shared OOXML and compare exact expanded targets and intervention outcomes."""
import argparse,json,pathlib,re,subprocess,tempfile
from zipfile import ZipFile
from xml.etree import ElementTree as E
import openpyxl as x
from openpyxl.utils.cell import range_boundaries,column_index_from_string,get_column_letter
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
F='{'+NS['s']+'}f'
MASTER='A2+2*$A2+4*A$2+8*$A$2+16*$A$1'
R=re.compile(r'(\$?)([A-Z]{1,3})(\$?)([1-9][0-9]*)')
ORIGINAL={'B2':MASTER,'B3':'A3+2*$A3+4*A$2+8*$A$2+16*$A$1',
          'B4':'A4+2*$A4+4*A$2+8*$A$2+16*$A$1','C1':'$B$2'}
EXACT={'E6':'D6+2*$D6+4*D$6+8*$D$6+16*$A$1',
       'B3':'A3+2*$A3+4*D$6+8*$D$6+16*$A$1',
       'B4':'A4+2*$A4+4*D$6+8*$D$6+16*$A$1','C1':'$E$6'}
def change_refs(text,transform):
 def one(m):
  lc,a,lr,b=m.groups();i,j=transform(int(b),column_index_from_string(a),lr,lc)
  assert 1<=i<=1048576 and 1<=j<=16384
  return f'{lc}{get_column_letter(j)}{lr}{i}'
 return R.sub(one,text)
def stage_shared(path):
 w=x.Workbook();s=w.active
 for cell,val in {'A1':11,'A2':7,'A3':13,'A4':17}.items():s[cell]=val
 for a,v in ORIGINAL.items():s[a]='='+v
 ordinary=path.with_suffix('.plain.xlsx');w.save(ordinary)
 with ZipFile(ordinary) as src,ZipFile(path,'w') as dst:
  for n in src.namelist():
   b=src.read(n)
   if n=='xl/worksheets/sheet1.xml':
    t=E.fromstring(b)
    for i in (2,3,4):
     e=t.find(f".//s:c[@r='B{i}']/s:f",NS)
     e.attrib.clear();e.set('t','shared');e.set('si','0')
     if i==2:e.set('ref','B2:B4')
     else:e.text=None
    b=E.tostring(t)
   dst.writestr(n,b)
def formula_xml(path,index=1):
 with ZipFile(path) as z:
  root=E.fromstring(z.read(f'xl/worksheets/sheet{index}.xml'))
 return {cell.get('r'):(f.attrib,f.text) for cell in root.findall('.//s:c',NS)
         if (f:=cell.find('s:f',NS)) is not None}
def independent_expand(tokens):
 masters={};refs={}
 for host,(attr,expr) in tokens.items():
  if attr.get('t')!='shared':
   assert expr is not None;refs[host]=expr;continue
  if 'ref' in attr:
   assert attr['si'] not in masters and expr
   masters[attr['si']]=(host,attr['ref'],expr)
 for host,(attr,expr) in tokens.items():
  if attr.get('t')!='shared':continue
  origin,span,text=masters[attr['si']]
  a,b,_,_=range_boundaries(origin);c,d,_,_=range_boundaries(host)
  c1,r1,c2,r2=range_boundaries(span)
  assert c1<=c<=c2 and r1<=d<=r2
  assert (expr is not None)==(host==origin)
  refs[host]=change_refs(text,lambda i,j,lr,lc:(i+(d-b if not lr else 0),j+(c-a if not lc else 0)))
 return refs
def expansion_from(formula,master,host):
 c,r,_,_=range_boundaries(host)
 a,b,_,_=range_boundaries(master)
 return change_refs(formula,lambda i,j,lr,lc:(i+(r-b if not lr else 0),j+(c-a if not lc else 0)))
def numbers(path):
 s=x.load_workbook(path,data_only=True).active
 return [s[a].value for a in ('B2','B3','B4','C1')]
def main():
 args=argparse.ArgumentParser();args.add_argument('--consumer',action='store_true');a=args.parse_args()
 report={'openpyxl':x.__version__}
 with tempfile.TemporaryDirectory() as tmp:
  d=pathlib.Path(tmp);original=d/'shared.xlsx';stage_shared(original);before=original.read_bytes()
  raw=formula_xml(original);expanded=independent_expand(raw)
  assert expanded==ORIGINAL
  native=x.load_workbook(original).active
  assert {h:native[h].value for h in ORIGINAL}=={h:'='+f for h,f in ORIGINAL.items()}
  def source(i,j):return i==2 and j in (1,2)
  patch={}
  for h,f in expanded.items():
   c,r,_,_=range_boundaries(h)
   nh='E6' if source(r,c) else h
   patch[nh]=change_refs(f,lambda i,j,lr,lc:(i+4,j+3) if source(i,j) else (i,j))
  assert patch==EXACT
  bad={h:expansion_from(patch['E6'],'E6',h) for h in ('B3','B4')}
  assert bad=={'B3':'A3+2*$D3+4*A$6+8*$D$6+16*$A$1',
               'B4':'A4+2*$D4+4*A$6+8*$D$6+16*$A$1'}
  assert all(bad[h]!=patch[h] for h in bad)
  # The two remaining contiguous follower formulas can still share a new B3 master.
  assert expansion_from(patch['B3'],'B3','B4')==patch['B4']
  w=x.Workbook();w.remove(w.active);found={}
  for arm in ('Current','StaleFollowers'):
   for test in ('Equal','OldSite','NewSite'):
    sh=w.create_sheet(arm+test)
    for cell in ('A1','A2','A3','A4'):sh[cell]=native[cell].value
    for h,f in expanded.items():sh[h]='='+f
    sh.move_range('A2:B2',rows=4,cols=3,translate=False)
    sh['A2']=7
    for h,f in patch.items():
     if arm=='StaleFollowers' and h in ('B3','B4'):f=expanded[h]
     sh[h]='='+f
    if test=='OldSite':sh['A2']=8
    if test=='NewSite':sh['D6']=8
  staged=d/'patches.xlsx';w.save(staged)
  for i,s in enumerate(w,1):
   f=formula_xml(staged,i)
   assert all('t' not in kind for kind,text in f.values())
   observed={h:v for h,(_,v) in f.items()}
   gold=EXACT if s.title.startswith('Current') else dict(EXACT,B3=ORIGINAL['B3'],B4=ORIGINAL['B4'])
   assert observed==gold
   found[s.title]=observed
  report.update(input_shared_XML=raw,pre_cut_independent_expansion=expanded,rewritten_XML=found)
  assert original.read_bytes()==before
  if a.consumer:
   out=d/'calc';out.mkdir()
   subprocess.run(['soffice','-env:UserInstallation='+(d/'profile').as_uri(),'--headless','--convert-to','xlsx','--outdir',str(out),str(original),str(staged)],
    check=True,timeout=110,capture_output=True)
   assert numbers(out/'shared.xlsx')==[281,299,311,281]
   calc=x.load_workbook(out/'patches.xlsx',data_only=True)
   got={s.title:[s[c].value for c in ('E6','B3','B4','C1')] for s in calc}
   assert got=={
    'CurrentEqual':[281,299,311,281],'StaleFollowersEqual':[281,299,311,281],
    'CurrentOldSite':[281,299,311,281],'StaleFollowersOldSite':[281,311,323,281],
    'CurrentNewSite':[296,311,323,296],'StaleFollowersNewSite':[296,299,311,296]},got
   report['libreoffice_cached_values']=got
 print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__':main()
