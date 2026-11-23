import os, json, logging, pathlib, sqlite3, sys, tempfile, hashlib
from importlib import metadata
P=pathlib.Path(__file__).resolve().parent
SH=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(SH/'deps'))
os.environ['GX_ANALYTICS_ENABLED']='false'
import great_expectations as gx
import pandas as pd
import sqlalchemy
logging.disable(logging.CRITICAL)
plan=json.loads((P/'PLAN.json').read_text())
assert gx.__version__==plan['version']
examples=[(f"{kind}_{i}", s) for kind, ss in plan['controls'].items() for i,s in enumerate(ss)]
def valid(s):
    return len(s)==6 and all('A'<=c<='Z' for c in s[:3]) and s[3]=='-' and all('0'<=c<='9' for c in s[4:])
bad={i for i,s in examples if not valid(s)}
assert bad=={i for i,s in examples if not i.startswith('legal_')}
def run(b):
    out=[]
    for regex in plan['patterns']:
        ev=b.validate(gx.expectations.ExpectColumnValuesToMatchRegex(column='token',regex=regex,result_format={'result_format':'COMPLETE','unexpected_index_column_names':['rid'],'return_unexpected_index_query':False}))
        assert ev.exception_info.get('raised_exception',False)==False, ev.exception_info
        r=ev.result
        vals=set(r.get('partial_unexpected_list',[])); ids={i for i,s in examples if s in vals}
        assert len(ids)==r['unexpected_count'] and r['element_count']==len(examples), (r,ids)
        out.append({'pattern':regex,'success':ev.success,'elements':r['element_count'],'unexpected_ids':sorted(ids),'faults_accepted':sorted(bad-ids),'legal_rejected':sorted(ids-bad)})
    return out
with tempfile.TemporaryDirectory(dir=SH) as td:
    p=pathlib.Path(td)/'gx.db'
    with sqlite3.connect(p) as c:
        c.execute('CREATE TABLE tokens(rid TEXT NOT NULL PRIMARY KEY, token TEXT NOT NULL)')
        c.executemany('INSERT INTO tokens VALUES (?,?)', examples)
        assert c.execute('SELECT * FROM tokens ORDER BY rowid').fetchall()==examples
    ctx=gx.get_context(mode='ephemeral')
    pa=ctx.data_sources.add_pandas('pd').add_dataframe_asset('tokens').add_batch_definition_whole_dataframe('whole')
    sq=ctx.data_sources.add_sqlite(name='sq', connection_string=f'sqlite:///{p}').add_table_asset(name='tokens',table_name='tokens').add_batch_definition_whole_table('whole')
    result={k:run(b) for k,b in [('pandas',pa.get_batch(batch_parameters={'dataframe':pd.DataFrame(examples,columns=['rid','token'])})),('sqlite',sq.get_batch())]}
    wa=ctx.data_sources.get('pd').assets[0].batch_definitions[0]
    arms=[]
    for id,t in examples[:2]+[next(e for e in examples if e[0]=='newline_0')]:
        controls=examples[:2] if id=='legal_0' else None
        if id=='legal_1': continue
        if id=='newline_0': controls=examples[:2]+[(id,t)]
        statuses=[]
        for regex in plan['patterns']:
            b=wa.get_batch(batch_parameters={'dataframe':pd.DataFrame(controls,columns=['rid','token'])})
            ev=b.validate(gx.expectations.ExpectColumnValuesToMatchRegex(column='token',regex=regex))
            statuses.append(ev.success)
        arms.append({'arm':'legal_only' if id=='legal_0' else 'add_final_LF','stock_results':statuses,'ground_truth':all(valid(t) for _,t in controls)})
print(json.dumps({'engines':{'python':sys.version.split()[0],'great_expectations':gx.__version__,'sqlite':sqlite3.sqlite_version,'sqlalchemy':sqlalchemy.__version__,'pandas':pd.__version__},'oracle_bad':sorted(bad),'native':result,'batch_decision_pandas':arms},indent=2,sort_keys=True))
