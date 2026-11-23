import pathlib,sys,json,shutil
E=pathlib.Path(sys.argv[1]); W=pathlib.Path(sys.argv[2]); name=sys.argv[3]
sys.path.insert(0,str(E/'input/duck143'));import duckdb
assert shutil.disk_usage(W).free>7*1024**3
p=W/f'{name}.duckdb'; assert not p.exists()
db=duckdb.connect(str(p),config={'memory_limit':'1300MB','threads':'2','preserve_insertion_order':'false','max_temp_directory_size':'800MB','temp_directory':str(W/'spill')})
assert duckdb.__version__=='1.4.3'
db.execute(f"LOAD '{E}/input/ext143/{name}.duckdb_extension'")
db.execute(f"CALL {'dsdgen' if name=='tpcds' else 'dbgen'}(sf=10)")
db.execute('CHECKPOINT')
counts={t:db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for (t,) in db.execute('SHOW TABLES').fetchall()}
db.close()
print(json.dumps({'tables':counts,'db_size':p.stat().st_size},indent=2,sort_keys=True))
