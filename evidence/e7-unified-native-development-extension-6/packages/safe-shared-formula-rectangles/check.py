import argparse,collections,itertools,json,pathlib,re,subprocess,tempfile
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import openpyxl as x
from openpyxl.utils.cell import get_column_letter as L,column_index_from_string as N,coordinate_to_tuple
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
R=re.compile(r'(\$?)([A-Z]{1,3})(\$?)([1-9][0-9]*)')
def at(p):return L(p[1])+str(p[0])
def old_formula(row,col):
 a=L(col-1);i=row-1
 return f'{a}{i}+2*$A{i}+4*{a}$1+8*$A$1'
def inside(p):return 1<=p[0]<=2 and 1<=p[1]<=2
def cut(p):return (p[0]+6,p[1]+6) if inside(p) else p
def rewrite(f):
 def r(m):
  C,c,E,i=m.groups();a,b=cut((int(i),N(c)))
  return f'{C}{L(b)}{E}{a}'
 return R.sub(r,f)
def signature(host,f):
 a,b=host;parts=[];end=0
 for m in R.finditer(f):
  C,c,E,i=m.groups();i,j=int(i),N(c)
  parts.append(f[end:m.start()]);parts.append((bool(C),j if C else j-b,bool(E),i if E else i-a))
  end=m.end()
 return tuple(parts+[f[end:]])
def partition(formulas):
 rows=collections.defaultdict(dict)
 for (i,j),f in formulas.items():rows[i][j]=signature((i,j),f)
 all_ranges=[];active={}
 for i,cols in sorted(rows.items()):
  runs=[]
  for j,v in sorted(cols.items()):
   if runs and runs[-1][1]+1==j and runs[-1][2]==v:runs[-1]=(runs[-1][0],j,v)
   else:runs.append((j,j,v))
  new={}
  for a,b,v in runs:
   key=(a,b,v);prev=active.pop(key,None)
   if prev and prev[2]+1==i:new[key]=(prev[0],a,i,b)
   else:
    if prev:all_ranges.append(prev)
    new[key]=(i,a,i,b)
  all_ranges+=list(active.values());active=new
 all_ranges+=list(active.values())
 return sorted(all_ranges)
def coords(box):
 a,b,c,d=box
 return list(itertools.product(range(a,c+1),range(b,d+1)))
def package(src,dst,by_sheet):
 with ZipFile(src) as z,ZipFile(dst,'w') as out:
  for n in z.namelist():
   payload=z.read(n)
   if n in by_sheet:
    root=ET.fromstring(payload)
    fs={coordinate_to_tuple(c.get('r')):c.find('s:f',NS) for c in root.findall('.//s:c',NS) if c.find('s:f',NS) is not None}
    for si,box in enumerate(by_sheet[n]):
     group=coords(box)
     if len(group)==1:continue
     for p in group:
      node=fs[p];node.set('t','shared');node.set('si',str(si))
      if p==group[0]:node.set('ref',at(group[0])+':'+at(group[-1]))
      else:node.text=None
    payload=ET.tostring(root)
   out.writestr(n,payload)
def raw_expand(p,index):
 with ZipFile(p) as z:root=ET.fromstring(z.read(f'xl/worksheets/sheet{index}.xml'))
 fs={coordinate_to_tuple(c.get('r')):c.find('s:f',NS) for c in root.findall('.//s:c',NS) if c.find('s:f',NS) is not None}
 # Independent reader uses master/follower delta, not signature comparison.
 masks={};out={}
 for h,node in fs.items():
  if node.get('t')=='shared' and node.get('ref'):
   q,r=map(coordinate_to_tuple,node.get('ref').split(':'))
   assert h==q and node.get('si') not in masks
   masks[node.get('si')]=(h,q,r,node.text)
 for si,h in masks.items():
  _,q,r,_=h
  expected=set(itertools.product(range(q[0],r[0]+1),range(q[1],r[1]+1)))
  assert expected=={a for a,node in fs.items() if node.get('t')=='shared' and node.get('si')==si}
 for h,node in fs.items():
  if node.get('t')!='shared':out[h]=node.text;continue
  master,q,r,text=masks[node.get('si')]
  assert (node.text is not None)==(h==master)
  assert q[0]<=h[0]<=r[0] and q[1]<=h[1]<=r[1]
  def tr(m):
   C,c,E,i=m.groups()
   return f'{C}{L(N(c)+(0 if C else h[1]-master[1]))}{E}{int(i)+(0 if E else h[0]-master[0])}'
  out[h]=R.sub(tr,text)
 return out
def eval_all(lits,fs):
 cache=dict(lits);active=set()
 def go(p):
  if p in cache:return cache[p]
  if p not in fs:return 0
  assert p not in active;active.add(p)
  terms=fs[p].split('+');v=0
  for t in terms:
   v+=int(t.split('*')[0] if '*' in t else 1)*go(coordinate_to_tuple(t.rsplit('*',1)[-1].replace('$','')))
  active.remove(p);cache[p]=v;return v
 return {at(p):go(p) for p in sorted(fs)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--consumer',action='store_true');a=ap.parse_args()
 formulas={p:old_formula(*p) for p in coords((2,2,5,5))}
 literals={(1,c):7+4*c for c in range(1,6)}|{(i,1):6*i+7 for i in range(2,6)}
 revised={cut(p):rewrite(f) for p,f in formulas.items()}
 revised_values={cut(p):v for p,v in literals.items()}
 groups=partition(revised)
 assert collections.Counter(p for g in groups for p in coords(g))==collections.Counter(revised.keys())
 assert any(i<k and j<l for i,j,k,l in groups)
 assert all(len({signature(p,revised[p]) for p in coords(g)})==1 for g in groups)
 # Select the lexicographically first adjacent pair with different signatures.
 bad=next((i,j,i,j+1) for i,j in sorted(revised)
          if (i,j+1) in revised and signature((i,j),revised[i,j])!=signature((i,j+1),revised[i,j+1]))
 assert len(coords(bad))==2
 def populate(s,ls,fs):
  for p,v in ls.items():s.cell(*p).value=v
  for p,v in fs.items():s.cell(*p).value='='+v
 def label(g):return at(g[:2])+':'+at(g[2:])
 with tempfile.TemporaryDirectory() as tmp:
  d=pathlib.Path(tmp);p=d/'original.xlsx';q=d/'shared.xlsx'
  w=x.Workbook();populate(w.active,literals,formulas);w.save(p)
  package(p,q,{'xl/worksheets/sheet1.xml':[(2,2,5,5)]})
  assert raw_expand(q,1)==formulas
  verified=x.load_workbook(q).active
  assert {pos:verified.cell(*pos).value[1:] for pos in formulas}==formulas
  qbytes=q.read_bytes()
  p=d/'explicit.xlsx';pack=d/'staged.xlsx';recalc=d/'out';recalc.mkdir()
  w=x.Workbook();w.active.title='Expanded'
  for sheet in [w.active,w.create_sheet('Repacked'),w.create_sheet('BadMerge')]:populate(sheet,revised_values,revised)
  w.save(p)
  package(p,pack,{'xl/worksheets/sheet2.xml':groups,'xl/worksheets/sheet3.xml':[bad]})
  e1,e2,e3=[raw_expand(pack,i) for i in (1,2,3)]
  assert e1==e2==revised
  wb=x.load_workbook(pack);pws=wb['Repacked']
  assert {pos:pws.cell(*pos).value[1:] for pos in revised}==revised
  wb.close()
  assert [p for p in sorted(revised) if e3[p]!=revised[p]]==[coords(bad)[1]]
  assert q.read_bytes()==qbytes
  gold=eval_all(revised_values,revised);badv=eval_all(revised_values,e3)
  assert badv!=gold
  result={'source_shared_range':'B2:E5','safe_shared_ranges':[label(g) for g in groups if len(coords(g))>1],
          'ordinary_singletons':[at(g[:2]) for g in groups if len(coords(g))==1],'nonshareable_pair':label(bad),
          'raw_mismatched_follower':at(coords(bad)[1]),'affected_value_cells':sorted(k for k in gold if gold[k]!=badv[k])}
  if a.consumer:
   subprocess.run(['soffice','-env:UserInstallation='+(d/'profile').as_uri(),'--headless','--convert-to','xlsx','--outdir',str(recalc),str(pack)],check=True,timeout=110,capture_output=True)
   c=x.load_workbook(recalc/'staged.xlsx',data_only=True)
   live={s.title:{k:s[k].value for k in gold} for s in c}
   assert live['Expanded']==live['Repacked']==gold and live['BadMerge']==badv
   result['libreoffice_cached_output']=live
 print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__':main()
