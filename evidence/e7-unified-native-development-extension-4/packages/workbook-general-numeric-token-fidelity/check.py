import openpyxl as xl
import math, random, struct, tempfile, json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def bit(x):return struct.pack('>d',x).hex()
def same(a,b):
 return (int==type(b) and a==b) if int==type(a) else bit(a)==bit(b)
def literal(x):return repr(x)
def cells(p):
 with ZipFile(p) as z:
  t=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
  return [c.find('s:v',NS).text for c in t.findall('.//s:c',NS)]
def raw_patch(src,dst,tokens):
 with ZipFile(src) as r,ZipFile(dst,'w') as w:
  for n in r.namelist():
   s=r.read(n)
   if n=='xl/worksheets/sheet1.xml':
    t=E.fromstring(s)
    for c,v in zip(t.findall('.//s:c',NS),tokens,strict=True):c.find('s:v',NS).text=v
    s=E.tostring(t)
   w.writestr(n,s)
def obs(p,ro):
 w=xl.load_workbook(p,read_only=ro,data_only=True)
 out=[r[0] for r in w.active.iter_rows(values_only=True)]
 w.close();return out
def main():
 rng=random.Random(104)
 controls=[1.0,math.nextafter(1.,2.),math.nextafter(math.nextafter(1.,2.),2.),
           math.nextafter(1.,0.),2**53,2**53+1,2**53+2,2**63-1,0,-0.0]
 samples=[math.ldexp(rng.random()+0.5,rng.randrange(-250,250)) for _ in range(400)]
 samples += [2**53+rng.randrange(-1000,1000) for _ in range(100)]
 numbers=controls+samples
 counts={}
 with tempfile.TemporaryDirectory() as t:
  p=Path(t)/'default.xlsx';a=Path(t)/'exact.xlsx';out=Path(t)/'resaved.xlsx'
  w=xl.Workbook()
  for x in numbers:w.active.append([x])
  w.save(p)
  tokens=cells(p)
  for ro in (False,True):
   ordinary=obs(p,ro)
   assert len(ordinary)==len(numbers)
   masks=[not same(x,y) for x,y in zip(numbers,ordinary,strict=True)]
   counts[str(ro)]=sum(masks)
   assert all((not same(x,(float(s) if '.' in s or 'e' in s.lower() else int(s))))==m for x,s,m in zip(numbers,tokens,masks))
  raw_patch(p,a,[literal(x) for x in numbers])
  for ro in (False,True):assert all(same(x,y) for x,y in zip(numbers,obs(a,ro),strict=True))
  xl.load_workbook(a).save(out)
  assert cells(out)==tokens
  assert tokens[0]==tokens[1]==tokens[2]=='1' and tokens[4]==tokens[5]
 print(json.dumps({'openpyxl':xl.__version__,'total':len(numbers),'classic_and_stream_mismatches':counts,'controls':[[repr(x),y] for x,y in zip(controls,tokens)],'patched_reader_mismatches':0},indent=2,sort_keys=True))
if __name__=='__main__':main()
