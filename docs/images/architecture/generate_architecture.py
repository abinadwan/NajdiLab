"""Generate the editable, dependency-free NajdiLab architecture SVG.
Run from any directory: python docs/images/architecture/generate_architecture.py
Only writes the sibling SVG; does not import or operate NajdiLab.
"""
from pathlib import Path
from html import escape

parts=['''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1530" viewBox="0 0 1200 1530" role="img" aria-labelledby="title desc">
<title id="title">NajdiLab — local platform and optional training architecture</title>
<desc id="desc">Clients pass loopback Host, Origin, CSRF, Ingest authentication and JSON checks. Python service and review overlays preserve originals in SQLite; dataset files and manifests are separate. Model configuration and preflight govern optional registered WSL training. Artifacts return for evaluation; model export and deployment remain separately blocked. Core operation needs no GPU, Hermes, Ollama or weights.</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="#456479"/></marker><marker id="blockedArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="#9a4c32"/></marker></defs>
<rect width="1200" height="1530" fill="#fbfcfe"/>
<style>text{font-family:Arial,Helvetica,sans-serif;fill:#172d43} .heading{font-size:22px;font-weight:700}.body{font-size:17px}.small{font-size:15px;fill:#42586d}.zone{fill:#f0f5fa;stroke:#c4d2df;stroke-width:1.3}.card{fill:#fff;stroke:#a9bfce;stroke-width:1.4}.line{fill:none;stroke:#456479;stroke-width:2;marker-end:url(#arrow)}.optional{stroke-dasharray:8 6}.blocked{stroke:#9a4c32;stroke-dasharray:2 6;marker-end:url(#blockedArrow)}</style>''']
def text(x,y,value,cls='body'):
 parts.append(f'<text x="{x}" y="{y}" class="{cls}">{escape(value)}</text>')
def zone(y,h,title,optional=False):
 parts.append(f'<rect x="28" y="{y}" width="1144" height="{h}" rx="14" class="zone"'+(' style="fill:#eff8f6;stroke:#80aaa4;stroke-dasharray:8 6"' if optional else '')+'/>');text(48,y+31,title,'heading')
def card(x,y,w,title,lines):
 parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="94" rx="10" class="card"/>');text(x+17,y+28,title,'heading')
 for i,line in enumerate(lines):text(x+17,y+55+i*23,line,'body')
def line(d,kind=''):parts.append(f'<path d="{d}" class="line {kind}"/>')
text(32,45,'NajdiLab','heading');text(180,45,'System architecture · verified source relationships','heading');text(32,76,'Local web platform works without GPU, models, Hermes or Ollama.','body')
zone(100,158,'A  Clients and external sources')
card(52,148,340,'Local browser',['English UI · Arabic RTL content','static/index.html + app.js'])
card(430,148,340,'Authorized clients',['AI clients and data collectors','Completed-turn JSON ingestion'])
card(808,148,340,'Optional Hermes',['Outbound webhook integration','Separate external installation'])
line('M222 242 V275');line('M600 242 V275');line('M978 242 V275','optional')
zone(278,154,'B  Loopback security and HTTP interface · 127.0.0.1')
card(52,326,340,'Request boundary',['Host / Origin / Fetch Metadata','CSRF for browser mutations'])
card(430,326,340,'Python HTTP API',['JSON and body framing limits','app/server.py · http_security.py'])
card(808,326,340,'Authenticated Ingest',['Bearer or raw-body HMAC','No HMAC replay freshness'])
line('M222 420 V465');line('M600 420 V452 H222 V465');line('M978 420 V458 H222 V465')
zone(468,172,'C  Core application · Python standard-library backend')
card(52,516,340,'Service operations',['Ingest, validate, transact','app/service.py · app/db.py'])
card(430,516,340,'Human review',['Decisions and correction overlays','Original response stays preserved'])
card(808,516,340,'Dataset platform',['Registry · privacy / eligibility','Quality · dedup / holdout logic'])
line('M392 563 H430');line('M770 563 H808')
line('M222 610 V665');line('M600 610 V650 H300 V665');line('M978 610 V665')
zone(668,172,'D  Persistent data · database records and dataset files are distinct')
card(52,716,530,'SQLite WAL database',['Original conversations / messages + review decisions','Foreign keys · transactions · export-version metadata'])
card(618,716,530,'Filesystem dataset versions',['Gold data files · manifests · integrity hashes','Discovery / freeze gates; private artifacts omitted'])
line('M978 810 V850 H222 V865')
zone(868,172,'E  Training and evaluation control · evidence and explicit gates')
card(52,916,340,'Model and job registry',['Identity / revision · configuration','app/training_control.py'])
card(430,916,340,'Preflight and approval',['Dataset / model / runtime checks','Dry Run ≠ optimizer training'])
card(808,916,340,'Evaluation and decision',['Adapter evidence · human review','No automatic release on success'])
line('M392 963 H430');line('M600 1010 V1065','optional')
zone(1068,172,'F  Optional external training runtime · separately configured',True)
card(52,1116,340,'Private runtime inputs',['Model weights and tokenizers','Frozen dataset staging'])
card(430,1116,340,'Registered WSL2 runtime',['GPU-dependent approved training','Distinct Smoke / Full approvals'])
card(808,1116,340,'Artifacts and adapters',['Private outputs / checkpoints','Validation before evaluation'])
line('M392 1163 H430','optional');line('M770 1163 H808','optional');line('M978 1116 V1010','optional')
line('M978 1010 H1185 V1267 H1148','blocked')
zone(1270,142,'G  Future / blocked model operations · separate rights and owner approval')
card(52,1318,1096,'Model merge · quantization / GGUF · export · deployment',['Scripts or designs do not establish approved model release. Rejected adapters remain preserved evidence.'])
text(40,1450,'Legend','heading');line('M140 1444 H205');text(220,1450,'Implemented relationship','small');line('M460 1444 H525','optional');text(540,1450,'Optional runtime / integration','small');line('M845 1444 H910','blocked');text(925,1450,'Blocked progression','small')
text(40,1488,'Scope: source behavior, not production deployment approval. See docs/architecture-diagrams.md for evidence and limits.','small')
parts.append('</svg>');Path(__file__).with_name('najdilab-system-architecture.svg').write_text('\n'.join(parts)+'\n',encoding='utf-8')
