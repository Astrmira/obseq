from pathlib import Path
from collections import Counter
import argparse,subprocess,sys
p=Path(__file__).resolve().parent
a=argparse.ArgumentParser();a.add_argument('inputs',type=Path);opts=a.parse_args()
subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=p,check=True,stdout=subprocess.DEVNULL)
rows=(p/'REPLAY.tsv').read_text().splitlines()
assert len({r.split()[0] for r in rows})==len(rows)==66
assert Counter(r.split()[1] for r in rows)=={'native_authored_development':47,'native_external_transfer':18,'receipt_only':1}
r=subprocess.check_output([sys.executable,'-IB','replay.py','--inputs',str(opts.inputs.resolve())],cwd=p)
assert r==(p/'NEW-REPLAY.tsv').read_bytes()
sys.stdout.buffer.write(r)
