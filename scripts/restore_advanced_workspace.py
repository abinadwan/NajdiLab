"""Build an explicitly synthetic static tree with the preserved workspace enabled."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'NAJDILAB_LEGACY_RESTORE_TEST'


def restore(output: Path) -> Path:
    output = output.resolve()
    allowed = (ROOT / '.test-tmp').resolve()
    if output == allowed or not output.is_relative_to(allowed) or output.exists():
        raise ValueError('Use a new child directory of this checkout\'s .test-tmp folder.')
    source = ROOT / 'static'
    app = (source / 'app.js').read_text(encoding='utf-8')
    original = 'initGuidedWorkspace();'
    if app.count(original) != 1:
        raise ValueError('The official initialization changed. Review the restore guide before proceeding.')
    restored = app.replace(original, "await import('/advanced-workspace.js').then(module=>module.restoreWorkspace());")
    shutil.copytree(source, output)
    (output / 'app.js').write_text(restored, encoding='utf-8', newline='\n')
    (output / MARKER).write_text('Synthetic static restoration only.\n', encoding='utf-8')
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = restore(args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({'static_root': str(result), 'official_tree_modified': False}))


if __name__ == '__main__':
    main()
