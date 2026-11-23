"""Authored coordinate and calendar controls; not public corpus observations."""
import json, pathlib, subprocess,tempfile
from openpyxl import Workbook
p=pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as t:
 f=pathlib.Path(t)/'fixture.xlsx'; b=Workbook(); w=b.active; w.title='calibration'
 for row,serial in [(1,1),(2,59),(4,61),(7,70)]:
  w.cell(row,1,'anchor'); v=w.cell(row,2,serial);v.number_format='yyyy-mm-dd'
 b.save(f)
 coords=[['calibration',r,2] for r in [1,2,3,4,7]]
 version,vals=json.loads(subprocess.check_output(['/usr/bin/python3',str(p/'gdal_read.py'),str(f)],input=json.dumps(coords),text=True))
 assert vals==[['Date','1899-12-31'],['Date','1900-02-27'],['absent',None],['Date','1900-03-01'],['Date','1900-03-10']],vals
 print(json.dumps({'native_version':version,'authored_only':True,'serials_and_gap':[1,59,None,61,70],'native_observations':vals},sort_keys=True))
