"""Check local Markdown file links and generated API inventory without app imports."""
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from generate_api_reference import render

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    try:
        result = subprocess.run(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', '*.md'],
            cwd=ROOT, capture_output=True, check=True,
        )
        paths = [ROOT / name for name in result.stdout.decode('utf-8').split('\0') if name]
    except (OSError, subprocess.CalledProcessError):
        paths = [path for path in ROOT.rglob('*.md')
                 if not set(path.relative_to(ROOT).parts) & {'.git', '.venv', '.pytest_cache', 'node_modules'}]
    paths = sorted({path for path in paths if path.is_file()})
    for path in paths:
        source = path.read_text(encoding='utf-8-sig')
        source = re.sub(r'```.*?```', '', source, flags=re.S)
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', source):
            target = target.strip().strip('<>').split('#',1)[0]
            if not target or re.match(r'[a-zA-Z]+:',target) or target.startswith('/'):
                continue
            resolved = (path.parent / unquote(target)).resolve()
            if not resolved.exists():
                errors.append(str(path.relative_to(ROOT))+': missing '+target)
    api = ROOT / 'docs/api-routes.md'
    if not api.exists() or api.read_text(encoding='utf-8') != render():
        errors.append('API route inventory is stale')
    if errors:
        raise SystemExit('\n'.join(errors))
    print('PASS: '+str(len(paths))+' source Markdown files checked recursively; local file links and API inventory resolve.')


if __name__ == '__main__':
    main()
