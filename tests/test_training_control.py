from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import dataset_platform as platform
from app import training_control as control


def row(record_id: str, conversation: str, target: str) -> dict:
    return {"id": record_id, "conversation_id": conversation, "messages": [{"role": "user", "content": f"سؤال {record_id}"}, {"role": "assistant", "content": target}], "target_message_index": 1, "message_loss_mask": [0, 1]}


class TrainingControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.exports = self.root / "exports"; self.exports.mkdir(); self.version = self.exports / "gold-v008-split-clean"; self.version.mkdir()
        platform._write_jsonl(self.version / "sft.jsonl", [row("s1", "c1", "أبشر واحد"), row("s2", "c1", "أبشر اثنين")])
        platform._write_jsonl(self.version / "multi_turn.jsonl", [row("m1", "c2", "ثلاثة")])
        platform._write_jsonl(self.version / "text_sft_eval.jsonl", [row("e1", "e1", "تقييم")])
        manifest = {"version": "gold-v008-split-clean", "state": "Frozen", "files": {"sft.jsonl": 2, "multi_turn.jsonl": 1, "text_sft_eval.jsonl": 1}, "sha256": {name: platform._sha256(self.version / name) for name in ("sft.jsonl", "multi_turn.jsonl", "text_sft_eval.jsonl")}}
        platform._generate_training_diagnostics(self.version, manifest); platform._write_json(self.version / "manifest.json", manifest)
        self.training = self.root / "training"; self.jobs = self.training / "jobs"; self.models = self.training / "models.json"
        self.patches = [patch.object(platform, "EXPORTS_DIR", self.exports), patch.object(control, "JOBS_ROOT", self.jobs), patch.object(control, "TRAINING_ROOT", self.training), patch.object(control, "MODELS_FILE", self.models)]
        for item in self.patches: item.start()
        control.initialize_training_control()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def payload(self) -> dict:
        return {"dataset_version": "gold-v008-split-clean", "model_id": "ministral-3-3b-unsloth-bnb4", "training_config": {"epochs": 3, "batch_size": 2, "gradient_accumulation_steps": 4, "save_steps": 2}}

    def test_frozen_healthy_dataset_passes_with_warnings(self):
        gate = control.quality_gate("gold-v008-split-clean")
        self.assertEqual(gate["status"], "PASS_WITH_WARNINGS")
        self.assertEqual(gate["blocking_issues"], [])

    def test_draft_and_stale_diagnostics_block(self):
        manifest = platform._json(self.version / "manifest.json", {}); manifest["state"] = "Draft"; platform._write_json(self.version / "manifest.json", manifest)
        self.assertEqual(control.quality_gate("gold-v008-split-clean")["status"], "BLOCKED")
        manifest["state"] = "Frozen"; manifest["diagnostics"]["training_fingerprint"] = "bad"; platform._write_json(self.version / "manifest.json", manifest)
        codes = {x["code"] for x in control.quality_gate("gold-v008-split-clean")["blocking_issues"]}
        self.assertIn("STALE_DIAGNOSTICS", codes)

    def test_checksum_and_loss_count_mismatch_block(self):
        manifest = platform._json(self.version / "manifest.json", {}); manifest["sha256"]["sft.jsonl"] = "bad"; manifest["loss_mask_validation"]["total"] = 33; platform._write_json(self.version / "manifest.json", manifest)
        codes = {x["code"] for x in control.quality_gate("gold-v008-split-clean")["blocking_issues"]}
        self.assertIn("STALE_CHECKSUM", codes); self.assertIn("LOSS_MASK_COUNT_MISMATCH", codes)

    def test_leakage_and_target_overlap_block(self):
        platform._write_jsonl(self.version / "text_sft_eval.jsonl", [row("e1", "c1", "أبشر واحد")])
        gate = control.quality_gate("gold-v008-split-clean"); codes = {x["code"] for x in gate["blocking_issues"]}
        self.assertIn("CONVERSATION_LEAKAGE", codes); self.assertIn("EXACT_TARGET_OVERLAP", codes)

    def test_optimizer_steps_include_gradient_accumulation(self):
        plan = control.calculate_plan(30, {"epochs": 3, "batch_size": 2, "gradient_accumulation_steps": 4})
        self.assertEqual(plan["batches_per_epoch"], 15); self.assertEqual(plan["optimizer_steps_per_epoch"], 4); self.assertEqual(plan["estimated_total_optimizer_steps"], 12); self.assertEqual(plan["effective_batch_size"], 8)

    def test_max_steps_override_and_invalid_config(self):
        self.assertEqual(control.calculate_plan(30, {"max_steps": 7})["estimated_total_optimizer_steps"], 7)
        with self.assertRaises(control.TrainingControlError): control.calculate_plan(30, {"batch_size": 0})

    def test_qlora_vram_uses_quantized_parameter_footprint_not_disk_size(self):
        model = {"model_size_gb": 9.573, "parameter_count": 5123178051, "minimum_vram_gb": 8}
        config = control.validate_training_config({"method": "QLoRA", "batch_size": 1, "max_seq_length": 2048})
        result = control.estimate_vram(model, config, {"gpu_vram_total_gb": 11.94, "gpu_vram_free_gb": 10.78})
        self.assertEqual(result["estimated_requirement_gb"], 8.0)
        self.assertEqual(result["status"], "LIKELY_SAFE")
        self.assertEqual(result["estimation_method"], "qlora_4bit_parameter_plus_adapter_activation_heuristic_v2")

    def test_create_persist_edit_ready_immutable_and_cancel(self):
        job = control.create_job(self.payload()); self.assertEqual(job["status"], "DRAFT"); self.assertTrue((self.jobs / job["job_id"] / "job.json").is_file())
        self.assertEqual(control.get_job(job["job_id"])["dataset_fingerprint"], job["dataset_fingerprint"])
        edited = control.update_job(job["job_id"], {"training_config": {**job["training_config"], "epochs": 2}}); self.assertEqual(edited["training_config"]["epochs"], 2)
        with self.assertRaises(control.TrainingControlError) as ack: control.mark_job_ready(job["job_id"], {})
        self.assertEqual(ack.exception.code, "WARNING_ACK_REQUIRED")
        ready = control.mark_job_ready(job["job_id"], {"acknowledge_warnings": True}); self.assertEqual(ready["status"], "READY")
        with self.assertRaises(control.TrainingControlError): control.update_job(job["job_id"], {"training_config": ready["training_config"]})
        self.assertEqual(control.cancel_job(job["job_id"])["status"], "CANCELLED")

    def test_stale_dataset_rejected_before_ready(self):
        job = control.create_job(self.payload()); saved = control.get_job(job["job_id"]); saved["dataset_fingerprint"] = "old"; control._atomic_json(control._job_path(job["job_id"]), saved)
        with self.assertRaises(control.TrainingControlError) as stale: control.mark_job_ready(job["job_id"], {"acknowledge_warnings": True})
        self.assertEqual(stale.exception.code, "STALE_DATASET_FINGERPRINT")

    def test_blocked_gate_cannot_become_ready(self):
        job = control.create_job(self.payload()); manifest = platform._json(self.version / "manifest.json", {}); manifest["state"] = "Draft"; platform._write_json(self.version / "manifest.json", manifest)
        with self.assertRaises(control.TrainingControlError) as blocked: control.mark_job_ready(job["job_id"], {"acknowledge_warnings": True})
        self.assertEqual(blocked.exception.code, "QUALITY_GATE_BLOCKED")

    def test_ids_and_model_paths_are_safe(self):
        first, second = control.create_job(self.payload()), control.create_job(self.payload()); self.assertNotEqual(first["job_id"], second["job_id"])
        with self.assertRaises(control.TrainingControlError): control.get_job("../escape")
        with self.assertRaises(control.TrainingControlError): control.register_model({"id": "bad-model", "path": "../../escape", "runtime": "wsl:NajdiTrain"})

    def test_remote_candidate_requires_validation_and_revision_is_fingerprinted(self):
        model = control.register_model({"id": "qwen-candidate", "source_type": "huggingface", "repository_id": "org/model", "revision": "abc123"})
        self.assertEqual(model["validation_status"], "NOT_CHECKED"); self.assertFalse(model["trainable"])
        checked = control.validate_model("qwen-candidate")
        self.assertEqual(checked["validation_status"], "INVALID"); self.assertEqual(checked["revision"], "abc123")
        job = control.create_job({**self.payload(), "model_id": "qwen-candidate"})
        self.assertEqual(job["model_config"]["repository_id"], "org/model"); self.assertEqual(job["model_config"]["revision"], "abc123")

    def test_ollama_is_visible_but_never_trainable(self):
        model = control.register_model({"id": "ollama-info", "source_type": "ollama", "repository_id": "qwen:latest"})
        self.assertTrue(model["excluded"]); self.assertFalse(model["trainable"])
        checked = control.validate_model("ollama-info")
        self.assertEqual(checked["repository_id"], "qwen:latest")
        self.assertEqual(checked["validation_status"], "INVALID")
        self.assertEqual(checked["availability"], "INFERENCE_ONLY")
        self.assertEqual(checked["validation"]["blockers"][0]["code"], "INFERENCE_ONLY")
        with self.assertRaises(control.TrainingControlError) as caught:
            control.create_job({**self.payload(), "model_id": "ollama-info"})
        self.assertEqual(caught.exception.code, "MODEL_UNAVAILABLE")

    def test_discovery_is_bounded_and_non_recursive(self):
        root = self.root / "models"; (root / "one").mkdir(parents=True); (root / "one" / "config.json").write_text("{}")
        (root / "nested" / "two").mkdir(parents=True); (root / "nested" / "two" / "config.json").write_text("{}")
        result = control.discover_models({"roots": [str(root)]})
        self.assertEqual(result["count"], 1); self.assertEqual(result["items"][0]["display_name"], "one")

    def test_acquisition_requires_exact_approval_and_registers_verified_local_model(self):
        probe = {"resolved_revision": control.OFFICIAL_MODEL_CATALOG[0]["revision"], "revision_matches": True,
            "license": "apache-2.0", "license_matches": True, "storage_ok": True, "actual_download_bytes": 10278849571}
        verified = {"status": "VERIFIED", "repository_id": "google/gemma-4-E2B-it",
            "revision": control.OFFICIAL_MODEL_CATALOG[0]["revision"], "target_path": control.OFFICIAL_MODEL_CATALOG[0]["target_path"],
            "architecture": "Gemma4ForConditionalGeneration", "tokenizer_available": True, "chat_template_available": True,
            "weight_files": ["model-00001-of-00003.safetensors"], "verified_lfs_files": 4, "hash_mismatches": [], "local_size_gib": 9.573}
        with patch.object(control, "_model_acquisition_probe", return_value=probe), patch.object(control, "_wsl_python", return_value=verified):
            with self.assertRaises(control.TrainingControlError) as denied:
                control.acquire_model({"candidate_id": "gemma4-e2b-it-official", "approval_text": "wrong"})
            self.assertEqual(denied.exception.code, "DOWNLOAD_AUTHORIZATION_MISMATCH")
            approval = control.prepare_model_acquisition({"candidate_id": "gemma4-e2b-it-official"})["approval_text"]
            result = control.acquire_model({"candidate_id": "gemma4-e2b-it-official", "approval_text": approval})
        self.assertEqual(result["status"], "COMPLETED"); self.assertFalse(result["training_started"]); self.assertEqual(result["optimizer_steps"], 0)
        model = control.get_model("gemma4-e2b-it-official")
        self.assertEqual(model["source_type"], "local"); self.assertEqual(model["validation_status"], "VALID")
        self.assertEqual(model["revision"], control.OFFICIAL_MODEL_CATALOG[0]["revision"]); self.assertEqual(model["native_tool_template"], "gemma4")

    def test_only_authorized_full_start_api_exists(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "server.py").read_text(encoding="utf-8")
        self.assertIn('/api/v1/training/jobs/(train-\\d{8}-\\d{3})/start-full-training', source)
        self.assertIn('authorization_token', source)
        self.assertNotIn('/api/v1/training/jobs/(train-\\d{8}-\\d{3})/start"', source)


if __name__ == "__main__": unittest.main()
