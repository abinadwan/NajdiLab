"""Lazily created services on the real server (V2.2.0 regression).

The training-model manager is created on first use from the Model library's hub. Creating it while holding
the Model library lock, then asking the Model library for its hub, deadlocked the server: the first request
to /api/v1/checkpoints never answered and Model library stopped responding. The browser fixture pre-creates
the manager, so only a test on a fresh server reaches this path.
"""
from __future__ import annotations

import http.client
import json
import threading

import app.server as server
from app.db import apply_migrations
from app.training_models import TrainingModels


def test_first_checkpoint_request_creates_the_manager_without_deadlock(tmp_path, monkeypatch):
    monkeypatch.setattr(TrainingModels, '_cache_roots', lambda self: [])  # never read this computer's cache
    monkeypatch.setattr(server, 'TrainingModels', lambda hub: TrainingModels(hub, tmp_path / 'training-models', cache_roots=[]))
    db = tmp_path / 'najdilab.db'
    apply_migrations(db)  # what run() does before serving
    monkeypatch.setattr(server, 'DB_PATH', db)
    http_server = server.NajdiLabHTTPServer(('127.0.0.1', 0), server.NajdiLabHandler)
    http_server.native.models_dir = tmp_path / 'models'
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    try:
        port = http_server.server_address[1]
        for path in ('/api/v1/checkpoints', '/api/v1/models/library'):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            connection.request('GET', path, headers={'Host': f'127.0.0.1:{port}'})
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
            assert response.status == 200, (path, body)
        assert http_server._training is not None and http_server._training.hub is http_server.models().hub
    finally:
        http_server.shutdown()
        http_server.server_close()
