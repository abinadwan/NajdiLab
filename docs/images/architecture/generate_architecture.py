"""Generate the local dataset workflow SVG; no application imports or operations."""
from html import escape
from pathlib import Path


def render():
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1090" viewBox="0 0 1200 1090" role="img" aria-labelledby="title desc">',
             '<title id="title">NajdiLab: local Chat to reviewed dataset and external Unsloth export</title>',
             '<desc id="desc">Local inference (LM Studio, Ollama or NajdiLab Native) and authorized local inputs enter request checks. Completed consented Chat pairs enter human review, privacy, quality, deduplication and holdout gates. Immutable dataset versions provide a file handoff. SQLite records and file manifests remain distinct; recovery is private and uses a separate location.</desc>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10" fill="none" stroke="#35556e" stroke-width="1.5"/></marker></defs>',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#18334b}.title{font-size:27px;font-weight:700}.heading{font-size:21px;font-weight:700}.body{font-size:16px}.small{font-size:16px}.card{stroke:#a6bdcd;stroke-width:1.5}.line{fill:none;stroke:#35556e;stroke-width:2;marker-end:url(#arrow)}</style>',
             '<rect width="1200" height="1090" fill="#f6f9fc"/>',
             '<text x="40" y="48" class="title">NajdiLab · Chat → Review → Quality → Version → External export</text>',
             '<text x="40" y="80" class="body">Local dataset preparation · externally managed inference · no internal trainer</text>']
    def card(x,y,w,h,title,lines,fill='#ffffff'):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" class="card" fill="{fill}"/>')
        parts.append(f'<text x="{x+20}" y="{y+31}" class="heading">{escape(title)}</text>')
        for i,line in enumerate(lines):
            parts.append(f'<text x="{x+20}" y="{y+60+i*25}" class="body">{escape(line)}</text>')
    def arrow(d): parts.append(f'<path d="{d}" class="line"/>')
    card(40,110,540,116,'Local inference (no cloud models)',['LM Studio / Ollama, or NajdiLab Native (own llama-server)','Exact context admission · pinned model identity · streaming'])
    card(620,110,540,116,'Authorized local inputs',['Credentialed completed-turn ingestion / manual data','Hermes BLOCKED · no native application history capture'])
    arrow('M310 226V262'); arrow('M890 226V262')
    card(40,264,1120,108,'Loopback request boundary',['Host / Origin / Fetch Metadata · bounded JSON · CSRF for browser writes','Native ingestion: bearer OR raw-body HMAC · local trusted operator only'])
    arrow('M310 372V410'); arrow('M890 372V390H600V450H580')
    card(40,412,540,140,'Own Chat and pending human review',['Streamed replies; only verified complete turns are saved','Collection OFF by default / restart; complete pairs only','Correction and explicit eligibility; originals stay'],'#edf6f3')
    card(620,412,540,140,'Dataset quality and privacy',['Whole-context privacy / exclusions · review integrity','Dedup · balance · holdout / leakage · masks','PASS does not establish truth, rights or consent'],'#edf6f3')
    arrow('M580 490H620'); arrow('M890 552V592')
    card(40,594,540,140,'SQLite: records and provenance',['Original messages · separate corrections and flags','Chat receipts / consent · manual / version metadata','Startup migration caveats remain; no schema cleanup'])
    card(620,594,540,140,'Immutable dataset versions',['Filesystem JSONL + manifest / counts / SHA256','Verified privacy-attested source and holdout snapshot','New versions only; existing exports stay preserved'])
    arrow('M310 552V594'); arrow('M310 734V774'); arrow('M890 734V774')
    card(40,776,540,144,'Private backup and separate restore',['SQLite online snapshot + declared file inventory','Verify hashes / integrity / FKs / counts in a new location','Archive hides; permanent delete has a declared scope'],'#eef3f8')
    card(620,776,540,144,'External Unsloth file handoff',['Prompt/completion JSONL · provenance · manifest','Sole completion target; no packing or truncation','External operator owns training setup and rights'],'#eef3f8')
    parts += ['<text x="40" y="972" class="small">Arrows are data relationships, not network services. SQLite metadata and dataset files are distinct.</text>',
              '<text x="40" y="1002" class="small">Limits: no RBAC / HMAC freshness; same-user file access; installed-model acceptance remains separate.</text>',
              '<text x="40" y="1032" class="small">Source cleanup changes no private data or applied migration. Publication, retention and rights gates stay open.</text>',
              '</svg>']
    return chr(10).join(parts)+chr(10)


if __name__ == '__main__':
    Path(__file__).with_name('najdilab-system-architecture.svg').write_text(render(),encoding='utf-8')
