"""Current documentation, screenshot provenance and executable synthetic API examples."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

from app.version import APP_VERSION, DISPLAY_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_current_version_guides_and_readme_have_consistent_scope():
    for name in ('README.md', 'docs/user-guide.md', 'docs/installation.md', 'docs/development/RELEASE_NOTES_V2.3.0.md'):
        text = (ROOT / name).read_text(encoding='utf-8')
        assert DISPLAY_VERSION in text, name
        assert not re.search(r'Settings\s*→\s*Advanced Mode|Enable Advanced Mode|Show specialist tools in Settings', text), name
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert '.test-tmp' not in readme
    assert not re.search(r'[A-Za-z]:[\\/]Users[\\/]|/home/[^<\s]+', readme)
    assert 'development candidate' in readme
    assert 'external' in readme and 'Direct Language' in readme and 'DPO' in readme and 'Evaluation' in readme


def test_official_screenshots_have_current_version_and_unmodified_png_provenance():
    directory = ROOT / 'docs/assets/screenshots/v2.3.0'
    records = json.loads((directory / 'provenance.json').read_text(encoding='utf-8'))
    assert len(records) >= 10
    assert {item['language'] for item in records} == {'en', 'ar'}
    assert {item['theme'] for item in records} == {'light', 'dark'}
    for item in records:
        assert item['display_version'] == DISPLAY_VERSION
        assert item['synthetic'] is True and item['pixel_processing'] == 'none'
        data = (directory / item['file']).read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n'
        assert hashlib.sha256(data).hexdigest() == item['sha256']
        assert struct.unpack('>II', data[16:24]) == (item['width'], item['height'])


def test_documented_setup_check_is_side_effect_free():
    result = subprocess.run([sys.executable, 'scripts/install.py', '--check'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'PASS' in result.stdout
    assert APP_VERSION == '2.3.0'


def test_documented_record_examples_preserve_formats_hashes_and_evaluation(tmp_path, monkeypatch):
    from app import dataset_platform as platform, unsloth_export
    from app.db import apply_migrations
    from app.service import add_manual_sft, add_direct_text, add_preference_pair, create_export
    db, exports = tmp_path / 'documentation.db', tmp_path / 'exports'
    apply_migrations(db)
    monkeypatch.setattr(platform, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(platform, 'EXPORTS_ROOT', exports)
    monkeypatch.setattr(platform, 'EXPORTS_DIR', exports)
    monkeypatch.setattr(platform, 'DATASETS_ROOT', tmp_path / 'datasets')
    monkeypatch.setattr(unsloth_export, 'HANDOFFS', tmp_path / 'handoffs')
    examples = json.loads((ROOT / 'docs/examples/v230-records.json').read_text(encoding='utf-8'))
    handlers = {'sft': add_manual_sft, 'direct': add_direct_text, 'preference': add_preference_pair}
    for record in examples['records']:
        handlers[record['type']](record['payload'], db)
    result = create_export(db, exports)
    manifest, directory = result['manifest'], Path(result['path'])
    for name in ('sft.jsonl', 'multi_turn.jsonl', 'direct_language.jsonl', 'preference_pairs.jsonl', 'evaluation_holdout.jsonl'):
        assert manifest['files'][name] == 1
    for name, digest in manifest['sha256'].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    handoff = unsloth_export.create_handoff(result['version'], profile='studio_chat', output_root=tmp_path / 'handoffs')
    text = (Path(handoff['directory']) / 'dataset.jsonl').read_text(encoding='utf-8')
    assert handoff['record_count'] == 2
    assert 'turquoise' not in text and 'synthetic cards' not in text
