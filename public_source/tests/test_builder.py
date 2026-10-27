"""Builder adversarial cases; changes in validation must fail these tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class BuilderTests(unittest.TestCase):
    def test_builder_exists(self):
        self.assertTrue((ROOT / 'public_source/build.py').is_file(), 'deterministic candidate builder missing')

    def test_deterministic_and_tamper_detection(self):
        if not (ROOT / 'public_source/build.py').exists(): self.fail('builder missing')
        spec = importlib.util.spec_from_file_location('candidate_builder', ROOT / 'public_source/build.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp)/'a'; b = Path(temp)/'b'
            mod.build(ROOT,a); mod.build(ROOT,b)
            self.assertEqual((a/'MANIFEST.json').read_bytes(),(b/'MANIFEST.json').read_bytes())
            mod.verify(a)
            (a/'unexpected.txt').write_text('unexpected')
            with self.assertRaises(ValueError): mod.verify(a)
            (a/'unexpected.txt').unlink()
            (a/'app/service.py').write_text('changed')
            with self.assertRaises(ValueError): mod.verify(a)

    def test_policy_rejects_unclassified_sources_and_dependency_changes(self):
        if not (ROOT/'public_source/build.py').exists(): self.fail('builder missing')
        spec=importlib.util.spec_from_file_location('candidate_builder',ROOT/'public_source/build.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as temp:
            clone=Path(temp)/'source';shutil.copytree(ROOT,clone,ignore=shutil.ignore_patterns('.git','.venv','__pycache__','data','datasets','exports','reports','training','backups','checkpoints'))
            (clone/'unclassified.py').write_text('print("unexpected")')
            with self.assertRaises(ValueError):mod.build(clone,Path(temp)/'out')
            (clone/'unclassified.py').unlink()
            (clone/'app/service.py').write_text('import undisclosed_package')
            with self.assertRaises(ValueError):mod.build(clone,Path(temp)/'out')
            with self.assertRaises(ValueError):mod.build(ROOT,ROOT/'candidate-forbidden')

    def test_forbidden_artifacts_and_imports_fail_closed(self):
        if not (ROOT/'public_source/build.py').exists():self.fail('builder missing')
        spec=importlib.util.spec_from_file_location('candidate_builder',ROOT/'public_source/build.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        for name in ['weights.bin','data/private.db','app/phase3_review.py']:
            with self.subTest(name=name),self.assertRaises(ValueError):mod.validate_content({name:b'pass'})
        with self.assertRaises(ValueError):mod.check_imports({'app/example.py':b'import app.phase38_dataset'})

    def test_dynamic_import_rejected(self):
        spec=importlib.util.spec_from_file_location('candidate_builder',ROOT/'public_source/build.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with self.assertRaises(ValueError):mod.check_imports({'app/example.py':b'import importlib; importlib.import_module("app.phase38_dataset")'})

    def test_platform_newlines_do_not_change_candidate(self):
        spec=importlib.util.spec_from_file_location('candidate_builder',ROOT/'public_source/build.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as temp:
            clone=Path(temp)/'source';shutil.copytree(ROOT,clone,ignore=shutil.ignore_patterns('.git','.venv','__pycache__','data','datasets','exports','reports','training','backups','checkpoints'))
            policy=json.loads((clone/'public_source/policy.json').read_text())
            for name in policy['files']:
                p=clone/name;p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
            mod.build(ROOT,Path(temp)/'a');mod.build(clone,Path(temp)/'b')
            self.assertEqual((Path(temp)/'a/MANIFEST.json').read_bytes(),(Path(temp)/'b/MANIFEST.json').read_bytes())

    def test_import_bindings_cannot_hide_private_modules(self):
        spec=importlib.util.spec_from_file_location('candidate_builder',ROOT/'public_source/build.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        for source in ['from app import phase38_dataset',
                       'from importlib import import_module; import_module("app.phase38_dataset")',
                       'from importlib import import_module as load; load("app.phase38_dataset")',
                       'from runpy import run_path; run_path("private.py")']:
            with self.subTest(source=source),self.assertRaises(ValueError):
                mod.check_imports({'app/__init__.py':b'', 'app/example.py':source.encode()})
