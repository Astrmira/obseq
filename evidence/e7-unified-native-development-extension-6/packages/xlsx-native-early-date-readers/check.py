import collections,csv,datetime as dt,decimal,hashlib,io,json,pathlib,re,subprocess,sys,tarfile,tempfile,zipfile
import openpyxl
from openpyxl.styles.numbers import is_date_format,is_timedelta_format,is_datetime
from openpyxl.utils.cell import coordinate_to_tuple
from xml.etree import ElementTree as ET
here=pathlib.Path(__file__).resolve().parent
archive,manifest=map(pathlib.Path,sys.argv[1:3])
digest=lambda b:hashlib.sha256(b).hexdigest()
source='9cf7228b54f1edcdd4b372eb736774adf29cb4f804c9920229bac6c154833399'
assert digest(archive.read_bytes())==source
R=list(csv.DictReader(manifest.open())); assert len(R)==2000
p={x['selection_id']:x for x in R if int(x['date_1900_before_march']) and not any(int(x[k]) for k in ['external_relationships','risky_part_names','formula_risk_hints'])}
stats=collections.Counter(); details=collections.Counter(); seen=set()
with tempfile.TemporaryDirectory() as tmp,tarfile.open(archive,'r|gz') as t:
 for m in t:
  k=digest(('pvl-eab-e4-v1:'+m.name).encode())
  if k not in p: continue
  assert k not in seen;seen.add(k);record=p[k]; b=t.extractfile(m).read();assert digest(b)==record['artifact_sha256']
  path=pathlib.Path(tmp)/'source.xlsx';path.write_bytes(b)
  book=openpyxl.load_workbook(io.BytesIO(b),data_only=True,read_only=True,keep_links=False)
  assert book.epoch==dt.datetime(1899,12,30)
  req=[]
  with zipfile.ZipFile(io.BytesIO(b)) as z:
   for ws in book:
    early=[];ctrl={}; bypos={}
    for row in ws.iter_rows():
     for c in row:
      if hasattr(c,'coordinate'):bypos[c.coordinate]=c
    for c in ET.fromstring(z.read(ws._worksheet_path)).findall('.//{*}c'):
     val=c.find('{*}v'); a=c.get('r'); v=bypos.get(a)
     if c.get('t','n')!='n' or val is None or not val.text or v is None:continue
     fmt=v.number_format
     if not is_date_format(fmt) or is_timedelta_format(fmt):continue
     num=decimal.Decimal(val.text)
     if not 1<=num<2958466:continue
     r,col=coordinate_to_tuple(a); rec=(ws.title,r,col,num,v.value,is_datetime(fmt) or 'other')
     if num<61:early.append(rec)
     elif col not in ctrl or r<ctrl[col][1]:ctrl[col]=rec
    req.extend([('early',e) for e in early]);req.extend([('control',ctrl[col]) for col in sorted({e[2] for e in early}&ctrl.keys())])
  assert sum(cat=='early' for cat,_ in req)==int(record['date_1900_before_march']);book.close()
  cp=subprocess.run(['/usr/bin/python3',str(here/'gdal_read.py'),str(path)],input=json.dumps([v[:3] for _,v in req]),text=True,capture_output=True,check=True)
  version,out=json.loads(cp.stdout);assert len(out)==len(req)
  for (cat,(_,_,_,num,value,fmt)),(kind,iso) in zip(req,out):
   if int(num)==60:ref=None
   else:ref=(dt.date(1899,12,31) if num<60 else dt.date(1899,12,30))+dt.timedelta(days=int(num))
   def classify(d):return 'not_calendar' if d is None else ('phantom' if ref is None else 'delta_days='+str((d-ref).days))
   ox=classify(value.date() if isinstance(value,dt.datetime) else value if isinstance(value,dt.date) else None)
   gx=classify(dt.date.fromisoformat(iso) if iso else None)
   stats[(cat,fmt,ox,kind,gx)]+=1;details[(record['stratum'],cat)]+=1
assert set(p)==seen
print(json.dumps({'versions':{'gdal':version,'openpyxl':openpyxl.__version__},'source_sha256':source,'manifest_sha256':digest(manifest.read_bytes()),'paths':len(seen),'coverage':{'|'.join(k):v for k,v in sorted(details.items())},'cells_by_cohort_format_openpyxl_gdaltype_gdal':{'|'.join(k):v for k,v in sorted(stats.items())}},indent=2,sort_keys=True))
