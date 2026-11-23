import pathlib,json,math,hashlib,duckdb
from decimal import Decimal
p=pathlib.Path(__file__).resolve().parent
f=pathlib.Path('/tmp/pvl-eab-submission/e7-scored/BLIND.json')
assert hashlib.sha256(f.read_bytes()).hexdigest()=='8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831'
c=duckdb.connect(config={'allow_unsigned_extensions':'false','autoinstall_known_extensions':'false','autoload_known_extensions':'false'})
c.execute("load '"+str(p/'spatial.duckdb_extension')+"'")
def num(t):
 q=Decimal(str(t)); x=float(q); assert math.isfinite(x) and Decimal.from_float(x)==q; return repr(x)
def wkt(points,n):
 assert 1<=len(points)<=10 and all(len(x)==n for x in points)
 return ('MULTIPOINT Z' if n==3 else 'MULTIPOINT')+' ('+','.join('('+' '.join(map(num,x))+')' for x in points)+')'
out=[]
for r in json.loads(f.read_bytes()):
 if r['subtype']!='equivalent point set': continue
 cid=r['case_id']; dim=3 if cid.endswith(('-05','-06')) else 2
 cols='ST_X(x.geom),ST_Y(x.geom)'+(',ST_Z(x.geom)' if cid.endswith('-06') else '')
 a=wkt(r['inputs']['points'],dim); b=wkt(r['candidate']['points'],dim)
 x=c.execute(f'''
 WITH a AS (SELECT DISTINCT {cols} FROM UNNEST(ST_Dump(ST_GeomFromText(?))) t(x)),
      b AS (SELECT DISTINCT {cols} FROM UNNEST(ST_Dump(ST_GeomFromText(?))) t(x)),
      a_only AS (SELECT * FROM a EXCEPT SELECT * FROM b),
      b_only AS (SELECT * FROM b EXCEPT SELECT * FROM a)
 SELECT (SELECT count(*) FROM a_only),(SELECT count(*) FROM b_only)
 ''',[a,b]).fetchone()
 out.append(dict(case_id=cid,mismatches_by_direction=list(x),duckdb_typed_membership=x==(0,0)))
print(json.dumps(out,indent=2))
