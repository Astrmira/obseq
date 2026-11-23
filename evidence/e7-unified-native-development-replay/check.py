from pathlib import Path
import subprocess,sys
p=Path(__file__).resolve().parent
subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=p,check=True,stdout=subprocess.DEVNULL)
r=subprocess.check_output([sys.executable,'-IB','replay.py'],cwd=p)
assert r==(p/'REPLAY.tsv').read_bytes()
rows=[line.split(b'\t') for line in r.splitlines()]
ids=[i for i,_,_ in rows]
assert len(set(ids))==len(ids)==26 and sum(kind==b'receipt_only' for _,kind,_ in rows)==1
assert all(status==b'PASS' for _,_,status in rows)
sys.stdout.buffer.write(r)
