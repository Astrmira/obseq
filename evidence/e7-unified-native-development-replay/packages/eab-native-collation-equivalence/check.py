import json,sqlite3,tempfile
from pathlib import Path
from osgeo import gdal, ogr
gdal.UseExceptions()
keys=['A','a','a ','a  ','a\t','A ','Ä','ä','ß','SS','é','e\u0301','',None,'a']
def quoted(s):return "'"+s.replace("'","''")+"'"
def pykey(s,col):
 if col=='RTRIM':return s.rstrip(' ')
 if col=='NOCASE':return s.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))
 return s
with tempfile.TemporaryDirectory() as tmp:
 results={}
 for driver in ['Memory','GPKG']:
  ds=ogr.GetDriverByName(driver).CreateDataSource('layer' if driver=='Memory' else str(Path(tmp)/'case.gpkg'))
  layer=ds.CreateLayer('t',geom_type=ogr.wkbNone)
  for name,tp in [('rid',ogr.OFTInteger),('k',ogr.OFTString)]:layer.CreateField(ogr.FieldDefn(name,tp))
  with sqlite3.connect(':memory:') as sql:
   sql.execute('create table t(rid integer,k text)')
   for i,k in enumerate(keys):
    sql.execute('insert into t values(?,?)',(i,k))
    f=ogr.Feature(layer.GetLayerDefn());f.SetField(0,i)
    if k is None:f.SetFieldNull(1)
    else:f.SetField(1,k)
    layer.CreateFeature(f)
   def query(what):
    r=ds.ExecuteSQL(what,dialect='SQLITE')
    ret=[(f.GetField(0),f.GetField(1)) for f in r]
    ds.ReleaseResultSet(r)
    return ret
   assert query('select rid,k from t order by rid')==list(enumerate(keys))
   comp=[]
   for pred,col,target in __import__('itertools').product(['direct','computed'],['BINARY','NOCASE','RTRIM'],keys[:13]):
    expr='k' if pred=='direct' else "(k || '')"
    text=f'select rid,k from t where {expr}={quoted(target)} collate {col} order by rid'
    exp=[(i,k) for i,k in enumerate(keys) if k is not None and pykey(k,col)==pykey(target,col)]
    assert exp==sql.execute(text).fetchall()
    ret=query(text)
    extra=sorted(set(ret)-set(exp)); missing=sorted(set(exp)-set(ret))
    comp.append(dict(shape=pred,collation=col,target=target,extra=extra,missing=missing))
   results[driver]=comp
 assert all(not r['extra'] and not r['missing'] for driver,rs in results.items() for r in rs if r['shape']=='computed' or driver=='GPKG')
 assert any(r['extra'] or r['missing'] for r in results['Memory'] if r['shape']=='direct')
print(json.dumps({'gdal':gdal.VersionInfo(),'sqlite':sqlite3.sqlite_version,'cases':results},sort_keys=True,indent=2))
