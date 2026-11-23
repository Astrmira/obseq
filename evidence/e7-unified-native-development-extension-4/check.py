from collections import Counter
from pathlib import Path
import subprocess,sys
p=Path(__file__).resolve().parent
subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=p,check=True,stdout=subprocess.DEVNULL)
ids=(p/'NEW-IDS.txt').read_text().split()
assert len(ids)==len(set(ids))==14
res=subprocess.check_output([sys.executable,'-IB','replay.py',*ids],cwd=p)
assert res==(p/'NEW-REPLAY.tsv').read_bytes()
rows=(p/'REPLAY.tsv').read_text().splitlines()
assert len({r.split()[0] for r in rows})==len(rows)==40
assert Counter(r.split()[1] for r in rows)=={'native_authored_development':36,'native_external_transfer':3,'receipt_only':1}
sys.stdout.buffer.write(res)
