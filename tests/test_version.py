"""Product version V2.1.0: one source, served to the interface, never hard-coded elsewhere."""
import http.client
import json
from pathlib import Path
import re
import threading

from app import server
from app.version import APP_VERSION, DISPLAY_VERSION, RELEASE_STATUS

ROOT = Path(__file__).resolve().parents[1]


def test_version_source_is_v2_1_0_and_a_development_candidate():
    assert APP_VERSION == '2.1.0'
    assert DISPLAY_VERSION == 'V2.1.0'
    assert RELEASE_STATUS == 'development-candidate', 'the label is not a release or production approval'


def test_server_and_config_report_the_same_version(tmp_path, monkeypatch):
    from app.db import apply_migrations
    db = tmp_path / 'v.db'
    apply_migrations(db)
    monkeypatch.setattr(server, 'DB_PATH', db)
    http_server = server.NajdiLabHTTPServer(('127.0.0.1', 0), server.NajdiLabHandler)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection('127.0.0.1', http_server.server_port, timeout=10)
        connection.request('GET', '/api/v1/health', headers={'Host': f'127.0.0.1:{http_server.server_port}'})
        assert json.loads(connection.getresponse().read())['version'] == APP_VERSION, 'health reports the same version'
        connection.request('GET', '/api/v1/config', headers={'Host': f'127.0.0.1:{http_server.server_port}'})
        response = connection.getresponse()
        config = json.loads(response.read())
        assert response.getheader('Server').startswith(f'NajdiLab/{APP_VERSION}')
        assert (config['app_version'], config['app_version_display'], config['release_status']) == ('2.1.0', 'V2.1.0', 'development-candidate')
    finally:
        http_server.shutdown()
        http_server.server_close()


def test_no_other_product_version_is_hard_coded():
    # The interface fills the label from /api/v1/config; the server reads app/version.py.
    # Also any quoted product version field ("version": "1.1"), which is how /api/v1/health once disagreed.
    pattern = re.compile(r'''\bV2\.[01]\.0\b|NajdiLab v1\.1|NajdiLab/1\.1|["']version["']:\s*["']\d+\.\d+(?:\.\d+)?["']''')
    sources = [*ROOT.glob('static/*.html'), *ROOT.glob('static/*.js'), *ROOT.glob('static/*.css'),
               *[p for p in ROOT.glob('app/*.py') if p.name != 'version.py']]
    offenders = [p.relative_to(ROOT).as_posix() for p in sources if pattern.search(p.read_text(encoding='utf-8'))]
    assert offenders == []
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    assert '<span id="app-version" class="brand-version" translate="no" data-i18n-skip></span>' in html
    assert 'id="settings-version"' in html
