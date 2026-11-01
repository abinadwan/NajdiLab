"""Documentation checks cover nested source trees, not only docs/."""
import importlib.util
import sys
from pathlib import Path

import pytest


def test_nested_public_and_github_markdown_links_are_checked(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / 'scripts'))
    spec = importlib.util.spec_from_file_location('source_docs_check', root / 'scripts/check_docs.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker, 'ROOT', tmp_path)
    monkeypatch.setattr(checker, 'render', lambda: 'synthetic inventory')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/api-routes.md').write_text('synthetic inventory', encoding='utf-8')
    for folder in ('public_source/docs/nested', '.github/ISSUE_TEMPLATE'):
        directory = tmp_path / folder
        directory.mkdir(parents=True)
        (directory / 'example.md').write_text('[broken](missing.md)', encoding='utf-8')
    with pytest.raises(SystemExit) as error:
        checker.main()
    assert 'public_source' in str(error.value)
    assert '.github' in str(error.value)
