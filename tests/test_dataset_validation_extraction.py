"""Synthetic regressions for dataset-only checks retained after runtime removal."""
from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import dataset_validation as gates
from app.dataset_masks import (
    DatasetMaskError, IGNORE_INDEX, encode_masked_sft_record,
    load_masked_dataset_records,
)
from app.dataset_tools import load_registry
from scripts import build_gold_v007_balanced as builder
from scripts import validate_dataset_masks as validator
from tests.test_native_dataset import record as native_record


class CharacterTokenizer:
    chat_template = "plain character fixture"

    def apply_chat_template(self, messages, tokenize=False, **kwargs):
        text = "".join(f"<{m['role']}>{m['content']}</{m['role']}>" for m in messages)
        return [ord(char) for char in text] if tokenize else text

    def __call__(self, text, **kwargs):
        return {"input_ids": [ord(char) for char in text],
                "offset_mapping": [(i, i + 1) for i in range(len(text))]}

    def decode(self, ids, **kwargs):
        return "".join(chr(token) for token in ids)

    def convert_ids_to_tokens(self, token):
        return chr(token)


def sft_record():
    return {"id": "synthetic-final", "messages": [
        {"role": "user", "content": "old prompt"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "new prompt"},
        {"role": "assistant", "content": "أول جواب"},
    ], "target_message_index": 3, "train_on_last_assistant_only": True,
        "message_loss_mask": [0, 0, 0, 1]}


class DatasetMaskExtractionTests(unittest.TestCase):
    def test_import_does_not_load_or_require_runtime_dependencies(self):
        code = """import builtins, importlib
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'torch', 'transformers', 'unsloth', 'peft'}:
        raise AssertionError('runtime dependency imported: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
importlib.import_module('app.dataset_masks')
importlib.import_module('app.dataset_validation')
"""
        result = subprocess.run([sys.executable, "-c", code],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_only_exact_final_response_is_supervised_and_schema_is_unchanged(self):
        row = sft_record()
        before = copy.deepcopy(row)
        tokenizer = CharacterTokenizer()
        encoded = encode_masked_sft_record(row, tokenizer)
        self.assertEqual(set(encoded), {"input_ids", "attention_mask", "labels", "record_id",
                                      "target_token_start", "target_token_end", "mask_strategy"})
        supervised = [token for token, label in zip(encoded["input_ids"], encoded["labels"])
                      if label != IGNORE_INDEX]
        self.assertEqual(tokenizer.decode(supervised), "أول جواب")
        self.assertEqual(row, before)
        start, end = encoded["target_token_start"], encoded["target_token_end"]
        self.assertTrue(all(label == IGNORE_INDEX for label in encoded["labels"][:start]))
        self.assertTrue(all(label == IGNORE_INDEX for label in encoded["labels"][end:]))

    def test_ambiguous_mask_and_partial_target_truncation_are_rejected(self):
        row = sft_record()
        row["message_loss_mask"][1] = 1
        with self.assertRaisesRegex(DatasetMaskError, "exactly one message"):
            encode_masked_sft_record(row, CharacterTokenizer())
        with self.assertRaisesRegex(DatasetMaskError, "truncation removed part"):
            encode_masked_sft_record(sft_record(), CharacterTokenizer(), max_length=15)

    def test_official_generation_mask_cannot_expand_or_omit_the_final_target(self):
        class OfficialTokenizer(CharacterTokenizer):
            chat_template = "{% generation %}fixture{% endgeneration %}"
            omit_target = False

            def apply_chat_template(self, messages, tokenize=False, **kwargs):
                value = super().apply_chat_template(messages, tokenize=tokenize, **kwargs)
                if kwargs.get("return_assistant_tokens_mask"):
                    return {"input_ids": value,
                            "assistant_masks": [0 if self.omit_target else 1] * len(value)}
                return value

        tokenizer = OfficialTokenizer()
        encoded = encode_masked_sft_record(sft_record(), tokenizer)
        supervised = [token for token, label in zip(encoded["input_ids"], encoded["labels"])
                      if label != IGNORE_INDEX]
        self.assertEqual(tokenizer.decode(supervised), sft_record()["messages"][-1]["content"])
        tokenizer.omit_target = True
        with self.assertRaisesRegex(DatasetMaskError, "omitted part"):
            encode_masked_sft_record(sft_record(), tokenizer)

    def test_dataset_loader_includes_only_supported_files_and_reports_source_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sft.jsonl").write_text(json.dumps(sft_record()) + "\n", encoding="utf-8")
            (root / "multi_turn.jsonl").write_text("", encoding="utf-8")
            (root / "evaluation_holdout.jsonl").write_text("not a dataset target", encoding="utf-8")
            self.assertEqual(len(load_masked_dataset_records(root, CharacterTokenizer())), 1)
            (root / "multi_turn.jsonl").write_text("\n{bad json}\n", encoding="utf-8")
            with self.assertRaisesRegex(DatasetMaskError, "multi_turn.jsonl:2:"):
                load_masked_dataset_records(root, CharacterTokenizer())

    def test_validator_loads_only_explicit_local_tokenizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tokenizer_dir = Path(tmp)
            factory = Mock(return_value=CharacterTokenizer())
            fake_transformers = SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=factory))
            result = {"passed": 1, "total": 1, "failures": []}
            argv = ["validate_dataset_masks.py", "--export-dir", tmp,
                    "--tokenizer-path", tmp, "--review-id", "synthetic-final"]
            with patch.dict(sys.modules, {"transformers": fake_transformers}), \
                    patch.object(sys, "argv", argv), patch.object(validator, "validate", return_value=result), \
                    patch("builtins.print"):
                validator.main()
            factory.assert_called_once_with(str(tokenizer_dir.resolve()),
                                            local_files_only=True, trust_remote_code=False)
            factory.reset_mock()
            argv[4] = str(tokenizer_dir / "missing")
            with patch.dict(sys.modules, {"transformers": fake_transformers}), \
                    patch.object(sys, "argv", argv), patch.object(sys, "stderr"), \
                    self.assertRaises(SystemExit) as caught:
                validator.main()
            self.assertEqual(caught.exception.code, 2)
            factory.assert_not_called()

    def test_script_is_importable_outside_project_and_builder_rejects_missing_tokenizer(self):
        script = Path(validator.__file__).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--tokenizer-path", result.stdout)
            self.assertNotIn("--model", result.stdout)
            with self.assertRaisesRegex(ValueError, "existing local directory"):
                builder.build(SimpleNamespace(tokenizer_path=Path(tmp) / "missing", root=Path(tmp)))

    def test_validator_preserves_exact_target_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sft.jsonl").write_text(json.dumps(sft_record()) + "\n", encoding="utf-8")
            (root / "multi_turn.jsonl").write_text("", encoding="utf-8")
            result = validator.validate(root, CharacterTokenizer(), "synthetic-final")
            self.assertEqual((result["passed"], result["total"], result["failures"]), (1, 1, []))
            self.assertEqual(result["diagnostic"]["trainable_text"], "أول جواب")


class DatasetGateExtractionTests(unittest.TestCase):
    def test_native_registry_binding_and_complete_masks_are_required(self):
        registry = load_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "capability-registry.json").write_text(
                json.dumps({k: v for k, v in registry.items() if k != "fingerprint"}), encoding="utf-8")
            (root / "native_tool_use.jsonl").write_text(json.dumps(native_record(registry)) + "\n", encoding="utf-8")
            mask = {"passed": 1, "total": 1, "failures": [],
                    "capability_registry_fingerprint": registry["fingerprint"]}
            path = root / "native-tool-loss-mask-validation.json"
            path.write_text(json.dumps(mask), encoding="utf-8")
            self.assertEqual(gates.validate_native_dataset(root)["status"], "PASS")
            mask["capability_registry_fingerprint"] = "stale"
            path.write_text(json.dumps(mask), encoding="utf-8")
            report = gates.validate_native_dataset(root)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertIn("NATIVE_TOOL_REGISTRY_MISMATCH", {item["code"] for item in report["blocking_issues"]})

    def test_freeze_removes_only_draft_blocker_and_retains_integrity_failures(self):
        sample = {"status": "BLOCKED", "blocking_issues": [
            {"code": "DATASET_NOT_FROZEN"}, {"code": "LOSS_MASK_FAILURE"},
            {"code": "CONVERSATION_LEAKAGE"}], "warnings": []}
        with patch.object(gates, "quality_gate", return_value=sample):
            result = gates.freeze_readiness_gate("synthetic-draft")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["gate"], "FREEZE_READINESS")
        self.assertEqual([item["code"] for item in result["blocking_issues"]],
                         ["LOSS_MASK_FAILURE", "CONVERSATION_LEAKAGE"])

    def test_quality_gate_preserves_checksums_diagnostics_and_mask_count_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("sft.jsonl", "multi_turn.jsonl"):
                (root / name).write_text(json.dumps(sft_record()) + "\n", encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({"state": "Frozen",
                "sha256": {"sft.jsonl": "wrong"}, "diagnostics": {"training_fingerprint": "dataset-contract"}}), encoding="utf-8")
            health = {"loss_mask_validation": {"passed": 1, "total": 1, "failures": []},
                "training_count": 2, "training_readiness": {"status": "READY"},
                "evaluation_integrity": {"status": "CLEAN", "conversation_overlap_count": 0,
                                         "exact_target_overlap_count": 0},
                "exact_duplicate_extra": 0, "counts": {"sft.jsonl": 1, "multi_turn.jsonl": 1}, "warnings": []}
            quality = {"status": "PASS", "counts": {}, "dataset_fingerprint": "synthetic", "findings": []}
            with ExitStack() as stack:
                stack.enter_context(patch.object(gates, "_version_dir", return_value=root))
                stack.enter_context(patch.object(gates, "dataset_quality", return_value=quality))
                stack.enter_context(patch.object(gates, "dataset_health", return_value=health))
                stack.enter_context(patch.object(gates, "_diagnostics_status", return_value=(False, "stale source")))
                result = gates.quality_gate("synthetic-frozen")
            codes = {item["code"] for item in result["blocking_issues"]}
            self.assertTrue({"STALE_CHECKSUM", "STALE_DIAGNOSTICS", "LOSS_MASK_COUNT_MISMATCH"} <= codes)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["training_fingerprint"], "dataset-contract")
            self.assertEqual(result["dataset_counts"]["training"], 2)


if __name__ == "__main__":
    unittest.main()


def test_candidate_registers_only_dataset_routes_without_extension_shims():
    root = Path(__file__).resolve().parents[1]
    server = root / "public_source/server.py"
    tree = ast.parse(server.read_text(encoding="utf-8"))
    routes = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
              and isinstance(node.value, str) and node.value.startswith("/api/")]
    assert "/api/v1/dataset-records" in routes
    assert not any(route.startswith(("/api/v1/training", "/api/v1/evaluation", "/api/v1/phase"))
                   for route in routes)
    assert not any(isinstance(node, ast.ImportFrom) and node.module == "extensions"
                   for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Attribute) and node.attr == "extension"
                   for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Constant) and node.value == "training_actions"
                   for node in ast.walk(tree))
    assert not (root / "public_source/extensions.py").exists()
