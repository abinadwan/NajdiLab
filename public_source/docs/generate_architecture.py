"""Regenerate the editable Core architecture SVG; standard library only."""
from html import escape
from pathlib import Path


def render():
    parts=['''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1000" viewBox="0 0 1200 1000" role="img" aria-labelledby="title desc">
<title id="title">NajdiLab Core — verified source-only architecture</title>
<desc id="desc">Local browser and credentialed ingestion enter loopback request checks. Atomic review and read-only dataset diagnostics use SQLite and private version files. Explicit downloads are restricted to verified JSONL. Coherent backup and separate restore are offline. Models are external; no extension interface is packaged.</desc>
<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="none" stroke="#35647a" stroke-width="1.4"/></marker></defs>
<style>text{font-family:system-ui,sans-serif;fill:#15394c}.title{font-size:28px;font-weight:700}.subtitle{font-size:15px;fill:#476477}.heading{font-size:18px;font-weight:650}.body{font-size:14px}.zone{font-size:12px;font-weight:700;letter-spacing:1px;fill:#476477}.line{fill:none;stroke:#35647a;stroke-width:2;marker-end:url(#arrow)}</style>
<rect width="1200" height="1000" fill="#f7fafb"/>
<text x="48" y="52" class="title">NajdiLab Core</text><text x="48" y="80" class="subtitle">Local conversation review and dataset preparation · no model execution</text>
<rect x="28" y="204" width="1144" height="560" rx="18" fill="#ffffff" stroke="#b5cbd6"/>
<text x="48" y="228" class="zone">CANDIDATE-LOCAL APPLICATION AND STORAGE</text>''']
    def card(x,y,w,h,title,lines,fill='#edf5f8'):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="#b5cbd6"/>')
        parts.append(f'<text x="{x+18}" y="{y+30}" class="heading">{escape(title)}</text>')
        for i,line in enumerate(lines):parts.append(f'<text x="{x+18}" y="{y+56+i*22}" class="body">{escape(line)}</text>')
    def arrow(points):parts.append(f'<path d="{points}" class="line"/>')
    card(48,108,520,74,'Local browser',['English controls · Arabic content · explicit saved decisions'])
    card(632,108,520,74,'Authorized native ingestion',['Bearer / HMAC · completed turns · no live integration discovery'])
    arrow('M308 182 V250');arrow('M892 182 V250')
    card(48,250,1104,100,'Loopback HTTP and request boundary',['Host / Origin / Fetch Metadata · browser CSRF · native credential checks','JSON framing and 2 MiB limit · safe DOM/CSP · candidate server + http_security'])
    arrow('M308 350 V388');arrow('M892 350 V388')
    card(48,388,520,134,'Contextual review',['core_reviews + service + read-only core_views','BEGIN IMMEDIATE · required revision · preserve flags / notes','Immutable originals · separate corrections · explicit eligibility'],'#e9f4f1')
    card(632,388,520,134,'Dataset preparation and inspection',['core_datasets + snapshot + generic quality helpers','Context privacy · split / dedup / holdout / strict masks','Registered manifest + exact filenames, counts and SHA256'],'#e9f4f1')
    arrow('M308 522 V560');arrow('M892 522 V560');arrow('M780 522 V540 H520 V560')
    card(48,560,520,124,'SQLite: local state',['Conversations / original messages / review overlays','Eligibility and privacy decisions · registered version metadata','Existing schema 001–004 only · no proposed SQL'])
    card(632,560,520,124,'Filesystem: local version evidence',['JSONL files + manifest + hashes · never a public upload','Private full_archive.json retains recovery evidence','Verified snapshots feed diagnostics and selected downloads'])
    parts.append('<text x="408" y="718" class="body">One server per storage root</text><text x="408" y="740" class="body">OS lock + serialized mutations</text>')
    arrow('M892 684 V788');arrow('M308 684 V788');arrow('M892 684 V764 H520 V788')
    card(48,788,520,122,'Private backup and separate restore',['Local CLI · SQLite snapshot + its registered version bytes','ZIP / database / manifest integrity · exclusive new destination','Full archives remain private; no model/runtime recovery'],'#f0f4f7')
    card(632,788,520,122,'Explicit artifact access',['HTTP attachment · selected manifest-authorized JSONL only','No archive, DB, credentials, model or arbitrary path access','Local file retrieval is not permission to redistribute'],'#f0f4f7')
    parts.append('''<rect x="48" y="938" width="1104" height="42" rx="8" fill="#fff5ed" stroke="#c2a68c" stroke-dasharray="5 4"/><text x="66" y="965" class="body">Boundary: local dataset preparation only · external model services · unknown removed routes return 404</text></svg>''')
    return '\n'.join(parts)+'\n'

if __name__=='__main__':
    Path(__file__).with_name('images').joinpath('core-architecture.svg').write_text(render(),encoding='utf-8',newline='\n')
