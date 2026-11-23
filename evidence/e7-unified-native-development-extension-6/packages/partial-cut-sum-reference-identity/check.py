import argparse,itertools,re,json,pathlib,tempfile,subprocess
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import openpyxl as xl
from openpyxl.utils.cell import range_boundaries,get_column_letter
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
ATOM=r'[A-Z]{1,3}[1-9][0-9]{0,6}'
ARG=ATOM+r'(?::'+ATOM+r')?'
SUM=re.compile(r'=SUM\(('+ARG+r'(?:,'+ARG+r')*)\)\Z')
# All rectangles are half-open (row-start, col-start, row-stop, col-stop).
def rect(a):
 c1,r1,c2,r2=range_boundaries(a)
 if not (1<=r1<=r2<=1048576 and 1<=c1<=c2<=16384):raise ValueError('unqualified-address')
 return r1,c1,r2+1,c2+1
def stamp(R):
 a,b,c,d=R;x=f'{get_column_letter(b)}{a}';y=f'{get_column_letter(d-1)}{c-1}'
 return x if x==y else x+':'+y
def contains(R,p):a,b,c,d=R;i,j=p;return a<=i<c and b<=j<d
def exact_intersection(R,S):
 a,b,c,d=R;x,y,z,w=S
 result=max(a,x),max(b,y),min(c,z),min(d,w)
 return result if valid(result) else None
def valid(R):return R[0]<R[2] and R[1]<R[3]
def shift(R,dr,dc):a,b,c,d=R;return a+dr,b+dc,c+dr,d+dc
def pieces(R,S,dr,dc):
 overlap=exact_intersection(R,S)
 if overlap is None:return [R]
 a,b,c,d=R; i,j,k,l=overlap
 out=[(a,b,i,d),(k,b,c,d),(i,b,k,j),(i,l,k,d),shift(overlap,dr,dc)]
 return [r for r in out if valid(r)]
def model(s):return {k:v.value for k,v in s._cells.items() if v.value is not None}
def qualify(ws,source,dr,dc):
 S=rect(source);D=shift(S,dr,dc)
 if not (1<=D[0]<D[2]<=1048577 and 1<=D[1]<D[3]<=16385) or exact_intersection(S,D):
  raise ValueError('unqualified-destination')
 before=model(ws);expected={};formula_args={}
 if len(ws.parent.worksheets)!=1 or ws.parent.defined_names or ws.merged_cells.ranges or ws.tables or ws.auto_filter.ref or ws.conditional_formatting or ws.data_validations.dataValidation or ws.defined_names:
  raise ValueError('unqualified-feature')
 if any(contains(D,p) for p in before):raise ValueError('occupied-destination')
 for p,v in before.items():
  t=(p[0]+dr,p[1]+dc) if contains(S,p) else p
  if type(v)==int:
   if not 0<=v<=10**6:raise ValueError('unqualified-value')
  elif isinstance(v,str) and (m:=SUM.fullmatch(v)):
   args=[rect(a) for a in m[1].split(',')]
   if any(exact_intersection(D,R) for R in args):raise ValueError('destination-already-referenced')
   formula_args[p]=args
   newargs=[stamp(U) for R in args for U in pieces(R,S,dr,dc)]
   if len(newargs)>100:raise ValueError('argument-budget')
   expected[t]='=SUM('+','.join(newargs)+')'
   continue
  else:raise ValueError('unqualified-formula')
  expected[t]=v
 # Formula dependencies need only the sparse set of formula host coordinates.
 active=set();computed={}
 def value(p):
  if p in active:raise ValueError('cyclic-formula')
  if p in computed:return computed[p]
  active.add(p);total=0
  for R in formula_args[p]:
   for q,v in before.items():
    if contains(R,q):total+=value(q) if q in formula_args else v
    if total>2**53:raise ValueError('inexact-sum-domain')
  active.remove(p);computed[p]=total;return total
 for p in formula_args:value(p)
 return expected
def fixture(s):
 for k,v in {'A1':1,'B2':2,'D4':5,'E5':7,'H12':11,'C3':'=SUM(B2,B2,H12)',
  'L1':'=SUM(A1:E5,B2:D4,C3,A1:E5)'}.items():s[k]=v
def xml_formulas(path):
 with ZipFile(path) as z:t=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
 return {c.get('r'):f.text for c in t.findall('.//s:c',NS) if (f:=c.find('s:f',NS)) is not None}
def exact_geometry():
 # Literal cell-set and independent multiplicity counters on small authored boxes.
 from collections import Counter
 def cells(R):
  a,b,c,d=R;return {(r,k) for r in range(a,c) for k in range(b,d)}
 terms=[(a,b,c,d) for a,b,c,d in itertools.product(range(1,5),repeat=4) if a<c and b<d]
 count=0
 for A,B,S in itertools.product(terms[:8],terms[::8],terms[::10]):
  reference=Counter()
  out=Counter()
  source=cells(S)
  for R in (A,B,A):
   reference.update((r+6,c+6) if (r,c) in source else (r,c) for r,c in cells(R))
   for U in pieces(R,S,6,6):out.update(cells(U))
  assert reference==out
  count+=1
 # Pure coordinate arithmetic on a rectangle spanning over four billion cells.
 R=(1,1,1048577,4097);S=(2,3,1048576,5);D=shift(S,0,12000)
 assert not exact_intersection(R,D)
 U=pieces(R,S,0,12000);area=lambda x:(x[2]-x[0])*(x[3]-x[1])
 assert len(U)==5 and sum(map(area,U))==area(R)==4294967296
 assert all(not exact_intersection(a,b) for a,b in itertools.combinations(U,2))
 return count
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--consumer',action='store_true');arg=ap.parse_args()
 outputs={}
 with tempfile.TemporaryDirectory() as tmp:
  d=pathlib.Path(tmp);baseline=d/'prior.xlsx';staged=d/'staged.xlsx'
  w=xl.Workbook();fixture(w.active);w.save(baseline);prior=baseline.read_bytes()
  expected=qualify(w.active,'B2:D4',5,5)
  for arm in ('openpyxl-relative','repair'):
   a=xl.load_workbook(baseline);s=a.active
   s.move_range('B2:D4',rows=5,cols=5,translate=arm=='openpyxl-relative')
   if arm=='repair':
    for p,v in expected.items():
     if isinstance(v,str):s.cell(*p).value=v
    assert model(s)==expected
   a.save(staged);observed=xml_formulas(staged)
   if arm=='repair':
    assert model(xl.load_workbook(staged).active)==expected
    assert observed=={'H8':'SUM(G7,G7,H12)','L1':
      'SUM(A1:E1,A5:E5,A2:A4,E2:E4,G7:I9,G7:I9,H8,A1:E1,A5:E5,A2:A4,E2:E4,G7:I9)'}
    staged.replace(d/'accepted.xlsx')
   else:assert observed=={'H8':'SUM(G7,G7,M17)','L1':'SUM(A1:E5,B2:D4,C3,A1:E5)'}
   outputs[arm]=observed
  assert baseline.read_bytes()==prior
  blocked={}
  for name,f,reason in [('markers','=SUM($B$2:C3)','unqualified-formula'),
                        ('blank-dest','=SUM(G7:H8)','destination-already-referenced'),
                        ('non-sum','=MAX(A1:E5)','unqualified-formula')]:
   w=xl.load_workbook(baseline);w.active['A8']=f;before=model(w.active)
   try:qualify(w.active,'B2:D4',5,5)
   except ValueError as e:assert str(e)==reason and model(w.active)==before;blocked[name]=reason
   else:raise AssertionError(name)
  cached={}
  if arg.consumer:
   p=d/'consumer.xlsx';w=xl.load_workbook(d/'accepted.xlsx');w.active.title='Patched';fixture(w.create_sheet('Original'));w.save(p)
   rec=d/'out';rec.mkdir()
   subprocess.run(['soffice','-env:UserInstallation='+(d/'profile').as_uri(),'--headless','--convert-to','xlsx','--outdir',str(rec),str(p)],check=True,capture_output=True,timeout=100)
   b=xl.load_workbook(rec/'consumer.xlsx',data_only=True)
   cached={s:[b[s][a].value for a in loc] for s,loc in [('Original',['C3','L1']),('Patched',['H8','L1'])]}
   assert cached['Original']==cached['Patched']==[15,97],cached
 out={'openpyxl':xl.__version__,'xml':outputs,'blocked':blocked,'literal_multiset_tests':exact_geometry()}
 if arg.consumer:out['cached']=cached
 print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()
