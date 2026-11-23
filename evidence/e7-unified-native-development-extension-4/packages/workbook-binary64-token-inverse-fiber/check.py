"""Compute every admitted preimage of one native XLSX decimal token, with exact rational endpoints."""
import decimal as D, random, struct, math, json, tempfile
from fractions import Fraction
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
import openpyxl as xl
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
LOW=0x0010000000000000; HIGH=0x7ff0000000000000
def value(bits):return struct.unpack('>d',bits.to_bytes(8,'big'))[0]
def power(k):return Fraction(10**k,1) if k>=0 else Fraction(1,10**(-k))
def fiber(token):
 d=D.Decimal(token);t=Fraction(d);assert t>0
 q=power(d.adjusted()-15);coeff=t/q;assert coeff.denominator==1
 prevstep=q/10 if t==power(d.adjusted()) else q
 a,b=t-prevstep/2,t+q/2
 closed=coeff.numerator%2==0
 def first(endpoint,strict):
  lo,hi=LOW,HIGH
  while lo<hi:
   z=(lo+hi)//2;v=Fraction(value(z))
   if v<endpoint or (strict and v==endpoint):lo=z+1
   else:hi=z
  return lo
 return first(a,not closed),first(b,closed)
def same_decimal(x,y):return D.Decimal(x)==D.Decimal(y)
def main():
 rng=random.Random(105)
 values=[rng.randrange(LOW,HIGH) for _ in range(1600)]
 for exp in range(-300,301,3):
  x=float('1e'+str(exp));u=int.from_bytes(struct.pack('>d',x),'big')
  values.extend(u+delta for delta in range(-8,9))
 # Include values close to normal min, finite max and exact decimal powers.
 values+=list(range(LOW,LOW+12))+list(range(HIGH-12,HIGH))
 with tempfile.TemporaryDirectory() as tmp:
  w=xl.Workbook();p=Path(tmp)/'native.xlsx'
  seen=[]
  for u in values:w.active.append([value(u)])
  w.save(p)
  with ZipFile(p) as z:
   t=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
   tokens=[x.text for x in t.findall('.//s:c/s:v',NS)]
  assert len(tokens)==len(values)
  hist={};audits=0;witness=None
  for u,token in zip(values,tokens):
   a,b=fiber(token);assert a<=u<b
   if b-a==9 and witness is None:witness=(token,a,b)
   hist[b-a]=hist.get(b-a,0)+1
   for v in range(max(LOW,a-1),min(HIGH,b+1)):
    assert same_decimal(format(value(v),'.16g'),token)==(a<=v<b)
    audits+=1
  token,a,b=witness
  w=xl.Workbook()
  for z in range(a,b):w.active.append([value(z)])
  w.save(p)
  with ZipFile(p) as z:
   t=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
   assert [x.text for x in t.findall('.//s:c/s:v',NS)]==[token]*9
 # The decade lower edge bounds the minimum adjacent binary64 spacing.
 # Decimal powers use asymmetric intervals and are checked separately.
 for k in range(-308,309):
  edge=max(power(k),Fraction(value(LOW)))
  e=edge.numerator.bit_length()-edge.denominator.bit_length()
  if edge < Fraction(2)**e:e-=1
  spacing=Fraction(2)**(e-52)
  assert power(k-15)<9*spacing
  a,b=fiber('1e'+str(k));assert b-a<=9
 assert max(hist)==9
 one=fiber('1')
 assert [value(i) for i in range(*one)]==[1.,1.0000000000000002,1.0000000000000004]
 print(json.dumps({'openpyxl':xl.__version__,'native_cells':len(values),'full_fiber_boundary_checks':audits,
  'observed_fiber_sizes':hist,'sharp_maximum_positive_normal_fiber':9,'decade_certificates':617,'sharp_native_token':token,'sharp_native_preimages':[float.hex(value(i)) for i in range(witness[1],witness[2])],'exact_fiber_1':[float.hex(value(i)) for i in range(*one)]},indent=2,sort_keys=True))
if __name__=='__main__':main()
