from os import environ
from collections import Counter
import pathlib,json,hashlib,tarfile,csv,io,math,openpyxl
P=pathlib.Path(environ['OBSEQ_XLSX_ARCHIVE']);M=pathlib.Path(environ['OBSEQ_XLSX_SELECTION']);h=lambda b:hashlib.sha256(b).hexdigest()
with P.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()=='9cf7228b54f1edcdd4b372eb736774adf29cb4f804c9920229bac6c154833399'
assert h(M.read_bytes())=='e345a682a73878738e902c7b5eb3d92d191708994cbf10cac9d30e336c7ed102'
rec={x['selection_id']:x for x in csv.DictReader(M.open()) if x['stratum']=='input' and x['worksheets']=='1' and 4000<=int(x['available_size'])<=100000 and all(x[k]=='0' for k in ('formula','external_relationships','risky_part_names','formula_risk_hints'))}
def op(b):return openpyxl.load_workbook(io.BytesIO(b),keep_links=False)
from datetime import datetime
from openpyxl.utils.datetime import to_excel
from zipfile import ZipFile
from xml.etree import ElementTree
def xmlval(b,addr):
 with ZipFile(io.BytesIO(b)) as z:
  rt=ElementTree.fromstring(z.read('xl/worksheets/sheet1.xml'))
  return next((c.get('t','n'),c.find('{*}v').text) for c in rt.findall('.//{*}c') if c.get('r')==addr)
rows=[];seen=set()
with tarfile.open(P,'r|gz') as t:
 for m in t:
  k=h(('pvl-eab-e4-v1:'+m.name).encode())
  if k not in rec:continue
  b=t.extractfile(m).read();s=h(b);assert s==rec[k]['artifact_sha256']
  if s in seen:continue
  w=op(b); ws=w.active
  cs=sorted((c for c in ws._cells.values() if type(c.value) is int and 61<=c.value<=60000 and c.number_format=='General'),key=lambda c:(c.row,c.column))
  if not cs:continue
  cell=cs[0];a=cell.coordinate;v=cell.value
  physical=xmlval(b,a); assert physical==('n',str(v))
  out=[]
  for mutant in (False,True):
   w=op(b); w.active[a].number_format='yyyy-mm-dd' if mutant else 'General'
   io1=io.BytesIO();w.save(io1);w.close();raw=io1.getvalue(); assert xmlval(raw,a)==physical
   w=op(raw);x=w.active[a].value
   out.append((type(x).__name__,to_excel(x,w.epoch) if isinstance(x,datetime) else x));w.close()
  assert out==[('int',v),('datetime',v)]
  rows.append(dict(workbook_sha256=s,ordered_storage_detect=False,untyped_serial_detect=False,typed_schema_detect=True,type_before=out[0][0],type_after=out[1][0]));seen.add(s)
  if len(rows)==16:break
assert len(rows)==16
print(json.dumps(dict(openpyxl=openpyxl.__version__,runs=rows,wilson_detection_16_of_16=[.806392,1],wilson_detection_0_of_16=[0,.193608]),sort_keys=True,indent=2))
