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


@pytest.mark.parametrize('markup', ['[section](guide.md#missing)', '<img src="missing.png" alt="synthetic">', '[guide](missing.mdx)'])
def test_documentation_checks_anchors_html_images_and_mdx(tmp_path, monkeypatch, markup):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / 'scripts'))
    spec = importlib.util.spec_from_file_location('source_docs_extended', root / 'scripts/check_docs.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker, 'ROOT', tmp_path)
    monkeypatch.setattr(checker, 'render', lambda: 'synthetic inventory')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/api-routes.md').write_text('synthetic inventory', encoding='utf-8')
    (tmp_path / 'guide.md').write_text('# Existing section\n', encoding='utf-8')
    (tmp_path / 'sample.mdx').write_text(markup, encoding='utf-8')
    with pytest.raises(SystemExit):
        checker.main()


def test_inline_code_is_not_treated_as_active_html_link(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / 'scripts'))
    spec = importlib.util.spec_from_file_location('source_docs_inline_code', root / 'scripts/check_docs.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    assert checker.links('`<source src="assets/river.webm">`') == []
    assert checker.links('<img src="actual.png">') == ['actual.png']
