"""Opt-in synthetic setup, staged as scripts/synthetic_demo.py. Never auto-run."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-disposable',action='store_true')
    args=parser.parse_args()
    if not args.confirm_disposable:raise SystemExit('Explicit --confirm-disposable required; no state changed.')
    marker=ROOT/'MANIFEST.json'
    if not marker.is_file() or json.loads(marker.read_text()).get('profile')!='source-only-engineering-candidate':raise SystemExit('Built candidate marker required.')
    if (ROOT/'data/najdilab.db').exists():raise SystemExit('Fresh disposable candidate required; existing database preserved.')
    sys.path.insert(0,str(ROOT))
    from app.db import apply_migrations
    from app.service import ingest_turn
    fixture=json.loads((ROOT/'synthetic.json').read_text(encoding='utf-8'))
    if fixture.get('synthetic') is not True:raise SystemExit('Synthetic fixture marker required.')
    apply_migrations()
    for turn in fixture['turns']:ingest_turn(turn)
    print('Fictional demo created in candidate-local storage. No research data or training used.')

if __name__=='__main__':main()
