"""Migration 010 (language metadata) on a disposable V2.1.0-shaped database: lossless, ids and counters kept."""
from __future__ import annotations

import sqlite3

import pytest

import app.db as db

LAYERS = ['najdi_riyadh', 'saudi_neutral', 'msa', 'technical_arabic', 'formal_arabic']
EXPECTED = {'najdi_riyadh': ('ar', 'najdi_riyadh', None), 'saudi_neutral': ('ar', 'saudi_neutral', None), 'msa': ('ar', 'msa', None),
            'technical_arabic': ('ar', None, 'technical'), 'formal_arabic': ('ar', None, 'formal')}


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    path = tmp_path / 'v210.db'
    sources = db._approved_migration_sources()
    assert list(sources)[-1] == '010_language_metadata.sql'
    before = {name: sql for name, sql in sources.items() if name != '010_language_metadata.sql'}
    monkeypatch.setattr(db, '_approved_migration_sources', lambda: before)
    db.apply_migrations(path)
    conn = sqlite3.connect(path)
    now = '2026-11-01T00:00:00Z'
    for i, layer in enumerate(LAYERS + ['legacy_custom_layer'], 1):
        conn.execute("INSERT INTO manual_sft_items(id, messages_json, language_layer, domain, origin, created_at, updated_at, notes) "
                     "VALUES (?, ?, ?, ?, 'manual', ?, ?, ?)", (i * 10, f'[{{"role":"user","content":"q{i}"}},{{"role":"assistant","content":"a{i}"}}]',
                                                              layer, f'domain {i}', now, now, f'note {i}'))
    for i, layer in enumerate(LAYERS, 1):
        conn.execute("INSERT INTO direct_language_texts(id, text, language_layer, source_type, origin, created_at, updated_at) "
                     "VALUES (?, ?, ?, 'human_written', 'manual', ?, ?)", (i * 10, f'text {i}', layer, now, now))
        conn.execute("INSERT INTO preference_pairs(prompt_context_json, rejected_response, preferred_response, language_layer, origin, created_at) "
                     "VALUES ('[]', ?, ?, ?, 'manual', ?)", (f'bad {i}', f'good {i}', layer, now))
    # Records with higher ids were created and deleted: their ids must never be reused.
    conn.execute("INSERT INTO manual_sft_items(id, messages_json, language_layer, origin, created_at) VALUES (900, '[]', 'msa', 'manual', ?)", (now,))
    conn.execute("DELETE FROM manual_sft_items WHERE id = 900")
    conn.execute("INSERT INTO direct_language_texts(id, text, language_layer, source_type, origin, created_at, updated_at) VALUES (700, 't', 'msa', 'human_written', 'manual', ?, ?)", (now, now))
    conn.execute("DELETE FROM direct_language_texts WHERE id = 700")
    conn.commit()
    snapshot = {table: [tuple(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY id')]
                for table in ('manual_sft_items', 'direct_language_texts', 'preference_pairs')}
    columns = {table: [r[1] for r in conn.execute(f'PRAGMA table_info({table})')] for table in snapshot}
    conn.close()
    monkeypatch.setattr(db, '_approved_migration_sources', lambda: sources)
    return path, snapshot, columns


def test_migration_010_keeps_every_row_value_id_and_counter(legacy_db):
    path, snapshot, columns = legacy_db
    db.apply_migrations(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    for table, rows in snapshot.items():
        after = conn.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
        assert len(after) == len(rows), table
        for old, new in zip(rows, after):
            assert tuple(new[c] for c in columns[table]) == old, f'{table} row {old[0]} changed'
    for table in ('manual_sft_items', 'direct_language_texts', 'preference_pairs'):
        for row in conn.execute(f'SELECT language_layer, language, dialect, style FROM {table}'):
            if row['language_layer'] in EXPECTED:
                assert (row['language'], row['dialect'], row['style']) == EXPECTED[row['language_layer']]
            else:
                assert (row['language'], row['dialect'], row['style']) == (None, None, None), 'unknown layers are never guessed'
    seq = dict(conn.execute('SELECT name, seq FROM sqlite_sequence').fetchall())
    assert seq['manual_sft_items'] >= 900 and seq['direct_language_texts'] >= 700
    assert not [name for name in seq if name.endswith('_legacy_010')]
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {'idx_manual_sft_manager', 'idx_manual_sft_lifecycle', 'idx_direct_manager', 'idx_direct_lifecycle'} <= indexes
    conn.execute("INSERT INTO direct_language_texts(text, source_type, origin, created_at, updated_at, language) VALUES ('English text', 'human_written', 'manual', 'x', 'x', 'en')")
    assert conn.execute('SELECT MAX(id) FROM direct_language_texts').fetchone()[0] > 700, 'a deleted id is not reused'
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO direct_language_texts(text, language_layer, source_type, origin, created_at, updated_at) VALUES ('x', 'not_a_layer', 'human_written', 'manual', 'x', 'x')")
    conn.close()
    db.apply_migrations(path)  # idempotent


def test_an_existing_database_is_copied_before_its_schema_changes(legacy_db, tmp_path):
    path, snapshot, _ = legacy_db
    db.apply_migrations(path)
    copies = list((path.parent / 'backups').glob('v210-before-010_language_metadata-*.db'))
    assert len(copies) == 1
    conn = sqlite3.connect(copies[0])
    assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'delete', 'a single self-contained file'
    applied = [r[0] for r in conn.execute('SELECT version FROM schema_migrations ORDER BY version')]
    assert applied[-1] == '009_managed_models.sql', 'the copy is the database as it was before 010'
    assert [tuple(r) for r in conn.execute('SELECT * FROM manual_sft_items ORDER BY id')] == snapshot['manual_sft_items']
    conn.close()
    fresh = tmp_path / 'fresh' / 'new.db'
    db.apply_migrations(fresh)
    assert not (fresh.parent / 'backups').exists(), 'a new installation has nothing to back up'
