"""Copy only manifest-selected verified source; never discover original/private state.
The manifest is an integrity inventory, not an authenticity signature or rights grant.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def copy_candidate(source, destination):
    source=Path(source);destination=Path(destination)
    if source.is_symlink() or getattr(source,'is_junction',lambda:False)():raise ValueError('Candidate root link rejected')
    manifest_path=source/'MANIFEST.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size>256*1024:raise ValueError('Invalid source manifest')
    raw_manifest=manifest_path.read_bytes();manifest=json.loads(raw_manifest)
    files=manifest.get('files',{})
    if (manifest.get('profile')!='source-only-engineering-candidate' or manifest.get('publication_approved') is not False
        or not isinstance(files,dict) or not 1<=len(files)<=512
        or not {'app/server.py','scripts/install.py','tests/browser.cjs'}<=set(files)):
        raise ValueError('Build and verify an exact candidate before acceptance')
    verified={};total=0
    for name,expected in files.items():
        path=PurePosixPath(name)
        if (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',name) or path.is_absolute()
            or any(p in {'..','.git','data','exports','backups','training','datasets','checkpoints'} or p.startswith('.') and name not in {'.env.example','.gitignore'} for p in path.parts)
            or name!=path.as_posix() or name.startswith(('app/phase','app/training_control','app/runtime_control','app/platform_state'))
            or not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected)):
            raise ValueError('Invalid candidate source path/hash')
        file=source/path
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in [file,*file.parents]):raise ValueError('Linked candidate source rejected')
        stat=file.stat();total+=stat.st_size
        if not file.is_file() or stat.st_size>16*1024*1024 or total>64*1024*1024:raise ValueError('Candidate bounds exceeded')
        data=file.read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Candidate source hash mismatch')
        verified[name]=data
    if destination.exists() or destination.is_symlink():raise ValueError('New disposable destination required')
    destination.mkdir()
    for name,data in {**verified,'MANIFEST.json':raw_manifest}.items():
        file=destination/name;file.parent.mkdir(parents=True,exist_ok=True)
        with file.open('xb') as stream:stream.write(data)
    return manifest
