"""Copy selected, version-attested synthetic Chromium captures without changing pixels."""
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
SELECTION = {
    'dashboard.png': 'en-start-light-1440.png',
    'wizard-data.png': 'en-data-selected-light-1440.png',
    'wizard-check-problem.png': 'ar-check-problem-light-1440.png',
    'wizard-check-ready.png': 'en-check-ready-light-1440.png',
    'wizard-approve.png': 'en-approve-light-1440.png',
    'wizard-export.png': 'en-export-light-1440.png',
    'manual-edit.png': 'en-record-edit-light-1440.png',
    'gold-versions.png': 'ar-versions-light-1440.png',
    'gold-delete-confirm.png': 'ar-delete-confirm-light-1440.png',
    'mobile-data.png': 'ar-data-selected-light-390.png',
    'mobile-version.png': 'en-mobile-version-light-390.png',
    'dark-export.png': 'ar-export-dark-390.png',
}


def main():
    source = ROOT / '.test-tmp/guided-acceptance'
    shots = json.loads((source / 'screenshots.json').read_text(encoding='utf-8'))
    destination = ROOT / 'docs/assets/screenshots/v2.3.0'
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for name, original in SELECTION.items():
        shot = next(item for item in reversed(shots) if item['name'] == original)
        if shot.get('displayVersion') != 'V2.3.0':
            raise ValueError('Regenerate current V2.3.0 browser captures before publishing documentation images.')
        data = (source / original).read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Expected an actual PNG capture.')
        width, height = struct.unpack('>II', data[16:24])
        if width != shot['width']:
            raise ValueError('Capture width differs from the browser evidence.')
        shutil.copyfile(source / original, destination / name)
        records.append({'file': name, 'sha256': hashlib.sha256(data).hexdigest(),
                        'display_version': shot['displayVersion'], 'captured_at': shot['capturedAt'],
                        'language': shot['language'], 'theme': shot['theme'], 'width': width, 'height': height,
                        'generator': 'tests/guided-workspace-browser.cjs', 'synthetic': True,
                        'pixel_processing': 'none', 'source_capture': original})
    (destination / 'provenance.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    print(f'Published {len(records)} unmodified synthetic V2.3.0 PNG captures.')


if __name__ == '__main__':
    main()
