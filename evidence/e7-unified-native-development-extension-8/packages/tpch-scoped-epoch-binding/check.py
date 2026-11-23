import hashlib,json,sys
from collections import defaultdict
import duckdb
path=sys.argv[1]
db=duckdb.connect(config={'threads':'1'})
db.execute("ATTACH '"+path.replace("'","''")+"' AS src (READ_ONLY)")
db.execute("CREATE TABLE s AS SELECT s_suppkey AS k,s_nationkey AS n,s_acctbal AS amount FROM src.supplier")
db.execute("CREATE TABLE n AS SELECT n_nationkey AS n,n_name AS name,n_regionkey AS r FROM src.nation")
db.execute("DETACH src")
db.execute("CREATE UNIQUE INDEX si ON s(k); CREATE UNIQUE INDEX ni ON n(n)")
db.execute("CREATE TABLE epoch (s INT,n INT,g INT,old_s INT,old_n INT); INSERT INTO epoch VALUES (0,0,0,0,0)")
def cents(v):
    y=v*100
    assert int(y)==y
    return int(y)
def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def joined():
    ss=[(k,n,cents(a)) for k,n,a in db.execute('SELECT * FROM s ORDER BY k').fetchall()]
    nn=db.execute('SELECT * FROM n ORDER BY n').fetchall()
    d={n:(name,r) for n,name,r in nn}
    assert len(d)==len(nn) and all(n in d for _,n,_ in ss)
    depend=[(k,n,d[n][0],a) for k,n,a in ss if d[n][1]==0]
    aggregates=defaultdict(lambda:[0,0])
    for _,n,name,a in depend:
        aggregates[n,name][0]+=1
        aggregates[n,name][1]+=a
    native=[(n,name,c,cents(a)) for n,name,c,a in db.execute("""
        SELECT n.n,n.name,count(*),sum(s.amount) FROM s JOIN n ON s.n=n.n
        WHERE n.r=0 GROUP BY n.n,n.name ORDER BY n.n,n.name
    """).fetchall()]
    assert native==[(n,name,*x) for (n,name),x in sorted(aggregates.items())]
    return dict(epoch=db.execute('SELECT * FROM epoch').fetchone(),
                cheap_count_max=(len(ss),ss[-1][0],len(nn),nn[-1][0]),
                full_data_digest=digest((ss,nn)), dependency_digest=digest(depend),
                contributors=len(depend), exact_dependencies=depend, output=native)
def s_edit(k,dst=None,add=None):
    old,a,old_r=db.execute('SELECT s.n,s.amount,n.r FROM s JOIN n ON s.n=n.n WHERE s.k=?',[k]).fetchone()
    new=old if dst is None else dst
    amount=a if add is None else a+add
    new_r=db.execute('SELECT r FROM n WHERE n=?',[new]).fetchone()[0]
    changed=(old,a)!=(new,amount)
    db.execute('UPDATE s SET n=?,amount=? WHERE k=?',[new,amount,k])
    db.execute('UPDATE epoch SET g=g+?,s=s+?,old_s=old_s+?',
               list(map(int, [changed,changed and (old_r==0 or new_r==0),changed and old_r==0])))
def n_edit(k,r=None,name=None):
    oldnm,oldr=db.execute('SELECT name,r FROM n WHERE n=?',[k]).fetchone()
    newnm=oldnm if name is None else name
    newr=oldr if r is None else r
    changed=(oldnm,oldr)!=(newnm,newr)
    db.execute('UPDATE n SET name=?,r=? WHERE n=?',[newnm,newr,k])
    db.execute('UPDATE epoch SET g=g+?,n=n+?,old_n=old_n+?',
               list(map(int, [changed,changed and (oldr==0 or newr==0),changed and oldr==0])))
db.execute('CREATE TEMP TABLE s_original AS FROM s; CREATE TEMP TABLE n_original AS FROM n')
before=joined()
assert before['cheap_count_max'][0]==100000 and before['cheap_count_max'][2]==25
si,ni=db.execute('SELECT s.k,s.n FROM s JOIN n ON s.n=n.n WHERE n.r=0 ORDER BY s.k LIMIT 1').fetchone()
so,no=db.execute('SELECT s.k,s.n FROM s JOIN n ON s.n=n.n WHERE n.r<>0 ORDER BY s.k LIMIT 1').fetchone()
tests=[]
for label,f,exact,scope,old,glob in [
    ('selected_amount',lambda:s_edit(si,add=1),True,True,True,True),
    ('outside_amount',lambda:s_edit(so,add=1),False,False,False,True),
    ('supplier_enters',lambda:s_edit(so,dst=ni),True,True,False,True),
    ('supplier_leaves',lambda:s_edit(si,dst=no),True,True,True,True),
    ('nation_enters',lambda:n_edit(no,r=0),True,True,False,True),
    ('outside_nation_renamed',lambda:n_edit(no,name='OUTSIDE EDIT'),False,False,False,True),
    ('rollback',lambda:s_edit(si,add=1),False,False,False,False),
    ('semantic_compensation',lambda:(s_edit(si,add=1),s_edit(si,add=-1)),False,True,True,True),
]:
    db.execute('BEGIN')
    f()
    if label=='rollback': db.execute('ROLLBACK')
    else: db.execute('COMMIT')
    after=joined()
    es,en,eg,eos,eon=after['epoch']
    dep=after['exact_dependencies']!=before['exact_dependencies']
    assert dep==(after['dependency_digest']!=before['dependency_digest'])
    output=after['output']!=before['output']
    assert after['cheap_count_max']==before['cheap_count_max']
    assert (dep,output,bool(es or en),bool(eos or eon),bool(eg))==(exact,exact,scope,old,glob)
    if label!='rollback':
        db.execute('BEGIN; DELETE FROM s; INSERT INTO s FROM s_original; DELETE FROM n; INSERT INTO n FROM n_original; UPDATE epoch SET s=0,n=0,g=0,old_s=0,old_n=0; COMMIT')
    assert db.execute('SELECT * FROM epoch').fetchone()==before['epoch']
    tests.append(dict(transition=label,exact_dependency_changed=dep,output_changed=output,
                      count_max_equal=True,scoped_epochs=[es,en],old_only_epochs=[eos,eon],global_epoch=eg,
                      contributors_delta=after['contributors']-before['contributors']))
print(json.dumps(dict(duckdb=duckdb.__version__,baseline_source_projection_sha256=before['full_data_digest'],
                     baseline_dependency_sha256=before['dependency_digest'],baseline_contributors=before['contributors'],
                     baseline_groups=len(before['output']),supplier_rows=before['cheap_count_max'][0],
                     nation_rows=before['cheap_count_max'][2],cases=tests,timings=None),indent=2,sort_keys=True))
