"""Deterministic engineering candidate builder, not a publication/license gate.
python public_source/build.py --output /separate/new/candidate
python public_source/build.py --verify /separate/pristine/candidate
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import struct
import zlib
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
PROFILE='source-only-engineering-candidate'
IGNORED_DIRS={'.git','__pycache__','.pytest_cache','.venv','data','datasets','exports','reports','training','backups','checkpoints'}

def digest(data):return hashlib.sha256(data).hexdigest()

def canonical_text(data):
    data.decode('utf-8')
    if b'\0' in data:raise ValueError('Binary source is not approved')
    return data.replace(b'\r\n',b'\n')

def canonical_file(name, data):
    if name.lower().endswith('.png'):
        if PurePosixPath(name).parts[:2] != ('docs','images'):
            raise ValueError('PNG assets require the reviewed documentation image directory')
        return data
    return canonical_text(data)


def validate_png(data):
    if len(data)>16*1024*1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid or oversized PNG')
    offset=8;chunks=[];compressed=[];dimensions=None
    while offset+12<=len(data):
        size=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8]
        if size>16*1024*1024 or offset+size+12>len(data):raise ValueError('Truncated PNG')
        payload=data[offset+8:offset+8+size];crc=struct.unpack('>I',data[offset+8+size:offset+12+size])[0]
        if crc!=(zlib.crc32(kind+payload)&0xffffffff) or kind not in {b'IHDR',b'IDAT',b'IEND',b'sRGB',b'gAMA',b'cHRM',b'pHYs'}:
            raise ValueError('PNG metadata, unsupported chunk or CRC mismatch')
        sizes={b'sRGB':1,b'gAMA':4,b'cHRM':32,b'pHYs':9}
        if kind in sizes and (size!=sizes[kind] or kind in chunks):raise ValueError('Invalid PNG ancillary data')
        chunks.append(kind)
        if kind==b'IHDR':
            if len(chunks)!=1 or size!=13:raise ValueError('Invalid PNG header')
            width,height,depth,color,compression,filter_method,interlace=struct.unpack('>IIBBBBB',payload)
            if not (1<=width<=4096 and 1<=height<=4096 and depth==8 and color in (2,6) and compression==0 and filter_method==0 and interlace==0):raise ValueError('Unsupported PNG dimensions/format')
            dimensions=(width,height,3 if color==2 else 4)
        if kind==b'IDAT':compressed.append(payload)
        offset+=size+12
        if kind==b'IEND':
            if size or offset!=len(data):raise ValueError('Trailing PNG content')
            break
    if not dimensions or not compressed or chunks[-1:]!=[b'IEND'] or chunks.count(b'IHDR')!=1 or offset!=len(data):raise ValueError('Incomplete PNG')
    width,height,channels=dimensions;stride=1+width*channels;expected=height*stride
    decoder=zlib.decompressobj()
    try:raw=decoder.decompress(b''.join(compressed),expected+1)
    except zlib.error:raise ValueError('Invalid PNG pixels') from None
    if len(raw)!=expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data or any(raw[i]>4 for i in range(0,len(raw),stride)):
        raise ValueError('Invalid or excessive PNG pixels')


def validate_svg(data):
    # ElementTree omits processing instructions; reject resource instructions before parsing.
    if re.search(br'<\?(?!xml\s)',data,re.I):raise ValueError('SVG processing instructions rejected')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('SVG document entities rejected')
    try:root=ET.fromstring(data)
    except ET.ParseError:raise ValueError('Invalid SVG XML') from None
    allowed={'svg','g','rect','path','line','polyline','polygon','circle','text','tspan','defs','marker','title','desc','style'}
    for node in root.iter():
        if not node.tag.startswith('{http://www.w3.org/2000/svg}') or node.tag.split('}')[-1] not in allowed:raise ValueError('Active or foreign SVG content')
        for key,value in node.attrib.items():
            if key.startswith('{'):raise ValueError('SVG namespaced attributes rejected')
            local=key.lower()
            if local.startswith('on') or local=='href' and not value.startswith('#'):raise ValueError('SVG external/event resource')
        css=' '.join(node.attrib.values())+' '+(node.text or '')
        if '@' in css or '/*' in css or chr(92) in css or any(fn.lower()!='url' for fn in re.findall(r'([A-Za-z_-][A-Za-z0-9_-]*)\s*\(',css)):raise ValueError('SVG external style')
        for resource in re.findall(r'url\(\s*([^)]*)\)',css,re.I):
            if not re.fullmatch(r'#[A-Za-z_][A-Za-z0-9_.-]*',resource.strip('\"\' ')):raise ValueError('SVG external resource')


def safe_path(value):
    p=PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or ':' in value:raise ValueError('Unsafe manifest path')
    return p.as_posix()

def source_files(root):
    try:
        result=subprocess.run(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard','-z'],capture_output=True,check=True)
        return set(result.stdout.decode().split('\0'))-{''}
    except (subprocess.CalledProcessError,FileNotFoundError):
        return {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and not set(p.relative_to(root).parts)&IGNORED_DIRS}

def check_imports(files):
    modules={p[:-3].replace('/','.') for p in files if p.endswith('.py')}
    modules|={p[:-12].replace('/','.') for p in files if p.endswith('/__init__.py')}
    packages={m.rsplit('.',1)[0] for m in modules if '.' in m}
    allowed_std=sys.stdlib_module_names  # pytest is test-only, installed separately.
    for name,data in files.items():
        if not name.endswith('.py'):continue
        tree=ast.parse(data,filename=name)
        package=name.rsplit('/',1)[0].replace('/','.') if '/' in name else ''
        for node in ast.walk(tree):
            targets=[]
            if isinstance(node,ast.Import):
                targets=[a.name for a in node.names]
                if any(t.split('.')[0]=='importlib' for t in targets):
                    raise ValueError('Dynamic import helpers are not candidate dependencies')
            elif isinstance(node,ast.ImportFrom):
                if node.level:
                    base=package.split('.')[:len(package.split('.'))-node.level+1]
                    prefix='.'.join(base)
                    targets=[prefix+'.'+node.module] if node.module else [prefix+'.'+a.name for a in node.names]
                else:
                    if node.module and node.module.split('.')[0] in {'importlib','runpy'}:
                        raise ValueError('Imported dynamic execution helpers rejected')
                    if node.module in packages:
                        targets=[node.module+'.'+a.name for a in node.names]
                    else:targets=[node.module]
            elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'exec','eval','__import__'}:
                raise ValueError('Unresolved dynamic execution dependency')
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                if node.func.attr in {'import_module','exec_module','run_path'}:
                    raise ValueError('Unresolved dynamic import/execution')
                if node.func.attr=='run_module':
                    if not node.args or not isinstance(node.args[0],ast.Constant) or node.args[0].value not in modules:
                        raise ValueError('Unresolved module entry point')
            for target in targets:
                if not target:raise ValueError('Unresolved import')
                top=target.split('.')[0]
                if top in allowed_std or top=='pytest' and name.startswith('tests/'):continue
                # Existing wrappers import local_runtime / generate_api_reference as top-level scripts.
                if target in modules or 'scripts.'+target in modules:continue
                raise ValueError('Unresolved candidate import: '+target)

def validate_content(files):
    forbidden_parts={'phase38_dataset.py','phase39_edits.py','complete_review_queue.py'}
    for name,data in files.items():
        parts=PurePosixPath(name).parts
        if (set(parts)&{'data','datasets','exports','reports','backups','training','checkpoints','.git','__pycache__'}
                or PurePosixPath(name).suffix.lower() in {'.db','.sqlite','.sqlite3','.log','.bin','.pt','.pth','.ckpt','.safetensors','.gguf','.zip','.pyc'}
                or name.startswith(('app/phase','app/training_control','app/runtime_control','app/platform_state'))):
            raise ValueError('Private/operational artifact cannot be a candidate file')
        if set(PurePosixPath(name).parts)&forbidden_parts:raise ValueError('Protected source in candidate')
        if name.lower().endswith('.png'):
            if PurePosixPath(name).parts[:2]!=('docs','images'):raise ValueError('PNG documentation asset location required')
            validate_png(data)
        if name.lower().endswith('.svg'):validate_svg(data)
        if name.endswith(('.svg','.py','.js','.html','.css','.json','.md','.txt','.sh','.ps1','.cmd')):
            text=data.decode('utf-8-sig')
            if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----|[A-Za-z]:[\\/]Users[\\/]|/home/(?!<)[^\s/]+/',text):
                raise ValueError('Sensitive path/credential candidate requires review')
    check_imports(files)

def build(root,output):
    root=Path(root).resolve();output=Path(output).absolute()
    # Never stage inside source/live application state or through symlink parents.
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(root):raise ValueError('Separate nonexistent output directory required')
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in output.parents):raise ValueError('Symlink output parent rejected')
    policy=json.loads((root/'public_source/policy.json').read_text())
    selected=policy['files'];excluded=set(policy['excluded'])
    if set(selected)&excluded:raise ValueError('Conflicting source classification')
    if source_files(root)!=(set(selected)|excluded|{'public_source/policy.json'}):raise ValueError('Unclassified or missing source files; review policy explicitly')
    files={}
    for src,entry in sorted(selected.items()):
        src=safe_path(src);dst=safe_path(entry['destination']);p=root/src
        if p.is_symlink() or not p.resolve().is_relative_to(root) or dst in files:raise ValueError('Unsafe source or duplicate destination')
        data=canonical_file(dst,p.read_bytes())
        if digest(data)!=entry['sha256']:raise ValueError('Selected source changed; review and repin required')
        files[dst]=data
    validate_content(files)
    manifest={'profile':PROFILE,'publication_approved':False,'files':{p:digest(b) for p,b in sorted(files.items())},
              'blocked_components':['private historical research','model execution','publication and redistribution approval']}
    output.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.candidate-stage-',dir=output.parent))
    try:
        for name,data in sorted(files.items()):
            p=temp/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        (temp/'MANIFEST.json').write_bytes((json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf-8'))
        verify(temp);temp.rename(output)
    finally:
        if temp.exists():shutil.rmtree(temp)  # Only this builder's newly created staging directory.
    return manifest

def verify(root):
    root=Path(root)
    if root.is_symlink() or (root/'MANIFEST.json').is_symlink():raise ValueError('Symlink manifest/root rejected')
    manifest=json.loads((root/'MANIFEST.json').read_text())
    if manifest.get('profile')!=PROFILE or manifest.get('publication_approved') is not False:raise ValueError('Invalid candidate profile')
    expected=manifest['files'];actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual!=set(expected)|{'MANIFEST.json'}:raise ValueError('Unexpected or missing candidate files')
    files={}
    for name,value in expected.items():
        p=root/safe_path(name)
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):raise ValueError('Unsafe candidate path')
        data=p.read_bytes()
        if digest(data)!=value:raise ValueError('Candidate file hash mismatch')
        files[name]=data
    validate_content(files)
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);g=parser.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--verify',type=Path);args=parser.parse_args()
    try:
        result=verify(args.verify) if args.verify else build(ROOT,args.output)
        print('PASS:',len(result['files']),'candidate files; private/model extensions blocked; PUBLICATION NOT APPROVED')
    except (ValueError,OSError,KeyError,SyntaxError) as exc:
        raise SystemExit('CANDIDATE_BLOCKED: '+type(exc).__name__+'; inspect source policy privately.') from None
