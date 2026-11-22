"""Check repository Markdown/MDX links, anchors, images and generated API inventory."""
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit
from generate_api_reference import render

ROOT = Path(__file__).resolve().parents[1]


def markdown_paths(root):
    try:
        result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root, capture_output=True, check=True)
        paths = [root / name for name in result.stdout.decode('utf-8').split('\0') if name.lower().endswith(('.md', '.mdx'))]
    except (OSError, subprocess.CalledProcessError):
        paths = [path for path in root.rglob('*') if path.suffix.lower() in {'.md', '.mdx'} and not set(path.relative_to(root).parts) & {'.git', '.venv', '.test-tmp', 'node_modules'}]
    return sorted({path for path in paths if path.is_file()})


def prose(source):
    source = re.sub(r'(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$', '', source)
    return re.sub(r'<!--.*?-->', '', source, flags=re.S)


class HtmlReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for name in ('href', 'src'):
            if values.get(name):
                self.targets.append(values[name])
        if values.get('id'):
            self.ids.add(values['id'])
        if tag == 'a' and values.get('name'):
            self.ids.add(values['name'])


def links(source):
    source = prose(source)
    html = HtmlReferences()
    html.feed(source)
    targets = re.findall(r'!?\[[^\]]*\]\((<[^>]+>|[^)\s]+)(?:\s+"[^"]*")?\)', source)
    definitions = dict(re.findall(r'(?m)^\[([^\]]+)\]:\s*(\S+)', source))
    targets.extend(definitions.values())
    targets.extend(definitions.get(key or label, '') for label, key in re.findall(r'!?\[([^\]]+)\]\[([^\]]*)\]', source))
    return [unescape(target.strip().strip('<>')) for target in targets + html.targets if target]


def anchors(source):
    source = prose(source)
    html = HtmlReferences()
    html.feed(source)
    result = set(html.ids)
    headings = re.findall(r'(?m)^#{1,6}\s+(.+?)\s*#*$', source)
    headings += re.findall(r'(?m)^([^\n]+)\n(?:={3,}|-{3,})\s*$', source)
    for text in headings:
        text = unescape(re.sub(r'<[^>]*>', '', text)).lower()
        slug = ''.join(char for char in text if not unicodedata.category(char).startswith(('P', 'S')) or char in '_-')
        slug = slug.strip().replace(' ', '-')
        unique, number = slug, 0
        while unique in result:
            number += 1
            unique = f'{slug}-{number}'
        result.add(unique)
    return result


def main():
    errors = []
    paths = markdown_paths(ROOT)
    checked = 0
    for path in paths:
        for target in links(path.read_text(encoding='utf-8-sig')):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            checked += 1
            resolved = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            label = str(path.relative_to(ROOT))
            if '.test-tmp' in resolved.parts:
                errors.append(f'{label} links a temporary artifact {target}')
                continue
            if not resolved.exists():
                errors.append(f'{label} missing {target}')
                continue
            fragment = unquote(parsed.fragment)
            if fragment and resolved.suffix.lower() in {'.md', '.mdx'} and fragment not in anchors(resolved.read_text(encoding='utf-8-sig')):
                errors.append(f'{label} missing anchor {target}')
    api = ROOT / 'docs/api-routes.md'
    if not api.exists() or api.read_text(encoding='utf-8') != render():
        errors.append('API route inventory is stale')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(paths)} Markdown/MDX files, {checked} local references, anchors, images and API inventory.')


if __name__ == '__main__':
    main()
