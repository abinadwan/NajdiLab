from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app import dataset_platform as platform
from app import runtime_control as runtime
from app import training_control as training


def row(record_id: str, conversation: str, target: str) -> dict:
    return {"id": record_id, "conversation_id": conversation, "messages": [{"role":"user","content":"سؤال"},{"role":"assistant","content":target}], "target_message_index":1, "message_loss_mask":[0,1], "train_on_last_assistant_only":True}


class RuntimeControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.exports = self.root / "exports"; self.exports.mkdir(); version = self.exports / "gold-v008-split-clean"; version.mkdir()
        platform._write_jsonl(version / "sft.jsonl", [row("s1","c1","واحد")]); platform._write_jsonl(version / "multi_turn.jsonl", [row("m1","c2","اثنين")]); platform._write_jsonl(version / "text_sft_eval.jsonl", [row("e1","e1","تقييم")])
        manifest = {"version":"gold-v008-split-clean","state":"Frozen","files":{"sft.jsonl":1,"multi_turn.jsonl":1,"text_sft_eval.jsonl":1},"sha256":{name:platform._sha256(version/name) for name in ("sft.jsonl","multi_turn.jsonl","text_sft_eval.jsonl")}}
        platform._generate_training_diagnostics(version, manifest); platform._write_json(version / "manifest.json", manifest)
        self.training_root = self.root / "training"; self.jobs = self.training_root / "jobs"; self.models = self.training_root / "models.json"; self.runtimes = self.training_root / "runtimes.json"; self.runtime_root = self.training_root / "runtime"
        self.original_live_probe = runtime.probe_live_gpu
        self.patches = [patch.object(platform,"EXPORTS_DIR",self.exports), patch.object(training,"TRAINING_ROOT",self.training_root), patch.object(training,"JOBS_ROOT",self.jobs), patch.object(training,"MODELS_FILE",self.models), patch.object(runtime,"RUNTIMES_FILE",self.runtimes), patch.object(runtime,"RUNTIME_ROOT",self.runtime_root), patch.object(runtime,"staging_status",return_value={"status":"PASS","dataset_fingerprint":"staged-fp","files":{},"manifest":{"source_fingerprint":"staged-fp"}}), patch.object(runtime,"probe_live_gpu",side_effect=lambda rt: self.live_gpu())]
        for item in self.patches: item.start()
        runtime.initialize_runtime_control(); models=json.loads(self.models.read_text(encoding="utf-8")); models["models"][0]["model_size_gb"]=4; training._atomic_json(self.models,models)
        draft=training.create_job({"dataset_version":"gold-v008-split-clean","model_id":"ministral-3-3b-unsloth-bnb4","training_config":{"epochs":2}}); self.job_id=draft["job_id"]; training.mark_job_ready(self.job_id,{"acknowledge_warnings":True})

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def success_result(self, *, status="AVAILABLE", free=10.0, checked_at=None):
        result={"runtime_id":"najditrain-wsl","status":status,"checks":[],"blockers":[],"warnings":[],"checked_at":checked_at or training._now(),"runtime_fingerprint":"runtime-fp","detected":{"cuda_available":True,"packages":{"torch":{"available":True,"version":"2"},"unsloth":{"available":True,"version":"1"}},"gpu":{"name":"Test GPU","total_vram_mb":12288,"used_vram_mb":2048,"free_vram_mb":free*1024,"driver":"1"},"paths":{"script":{"exists":True},"dataset_root":{"exists":True},"model":{"exists":True},"output":{"writable":True},"checkpoint":{"writable":True},"logs":{"writable":True}}}}
        training._atomic_json(runtime._runtime_result_path("najditrain-wsl"),result); runtime.set_worker_state("najditrain-wsl","IDLE"); return result

    def live_gpu(self, *, free=10.0, total=12.0, success=True):
        return {"measurement":"LIVE","probe_source":"torch.cuda.mem_get_info","observed_at":training._now(),"success":success,"gpu_name":"Test GPU",
            "total_gib":total,"used_gib":round(total-free,2),"free_gib":free,"total_bytes":int(total*1024**3),"used_bytes":int((total-free)*1024**3),"free_bytes":int(free*1024**3),"units":{"bytes":"bytes","mib":"MiB","gib":"GiB"}}

    def fake_runner(self, missing=()):
        missing=set(missing)
        def run(command, timeout):
            if command[:3]==["wsl.exe","--list","--verbose"]:
                if "wsl" in missing: raise FileNotFoundError
                name="Other" if "distro" in missing else "NajdiTrain"; return subprocess.CompletedProcess(command,0,f"  NAME STATE VERSION\n* {name} Running 2\n","")
            if "nvidia-smi" in command:
                return subprocess.CompletedProcess(command,1,"","missing") if "gpu" in missing else subprocess.CompletedProcess(command,0,"Test GPU, 12288, 1024, 11264, 999.1\n","")
            script=command[command.index("-c")+1]
            if "import importlib" in script:
                packages={name:{"available":name not in missing,"version":"1"} for name in ("pip",*runtime.REQUIRED_PACKAGES)}
                info={"user":"najdi","python":None if "python" in missing else "3.12","packages":packages,"cuda_available":"cuda" not in missing,"torch_cuda_version":"12.8","platform":"Linux"}
                return subprocess.CompletedProcess(command,1,"","python missing") if "python" in missing else subprocess.CompletedProcess(command,0,json.dumps(info)+"\n","")
            paths={key:{"exists":True,"is_file":key in {"python","script"},"writable":True} for key in ("project","python","venv","script","dataset_root","model","output","checkpoint","logs")}
            if "output" in missing: paths["output"]["writable"]=False
            return subprocess.CompletedProcess(command,0,json.dumps(paths)+"\n","")
        return run

    def test_runtime_registry_and_successful_check(self):
        result=runtime.check_runtime("najditrain-wsl",runner=self.fake_runner()); self.assertEqual(result["status"],"AVAILABLE"); self.assertEqual(result["detected"]["gpu"]["name"],"Test GPU"); self.assertEqual(runtime.get_worker_state("najditrain-wsl")["state"],"IDLE")

    def test_runtime_failure_matrix(self):
        cases={"wsl":"WSL_NOT_AVAILABLE","distro":"WSL_DISTRO_NOT_FOUND","python":"PYTHON_NOT_FOUND","torch":"TORCH_NOT_AVAILABLE","cuda":"CUDA_NOT_AVAILABLE","gpu":"GPU_NOT_FOUND","unsloth":"UNSLOTH_NOT_AVAILABLE","output":"OUTPUT_NOT_WRITABLE"}
        for missing,code in cases.items():
            with self.subTest(missing=missing): self.assertIn(code,runtime.check_runtime("najditrain-wsl",runner=self.fake_runner({missing}))["blockers"])

    def test_runtime_freshness(self):
        self.success_result(); self.assertNotIn("RUNTIME_CHECK_STALE",{x["code"] for x in runtime.execution_gate(self.job_id)["blockers"]})
        old=(datetime.now(timezone.utc)-timedelta(seconds=runtime.RUNTIME_CHECK_MAX_AGE_SECONDS+1)).isoformat(); self.success_result(checked_at=old)
        self.assertIn("RUNTIME_CHECK_STALE",{x["code"] for x in runtime.execution_gate(self.job_id)["blockers"]})

    def test_worker_states_and_heartbeat(self):
        for state in ("OFFLINE","IDLE","BUSY","ERROR"):
            self.assertEqual(runtime.set_worker_state("najditrain-wsl",state)["state"],state)
        worker=runtime.set_worker_state("najditrain-wsl","IDLE"); self.assertEqual(worker["heartbeat_freshness"],"FRESH")
        saved=json.loads(runtime._worker_path("najditrain-wsl").read_text()); saved["heartbeat_at"]=(datetime.now(timezone.utc)-timedelta(seconds=91)).isoformat(); training._atomic_json(runtime._worker_path("najditrain-wsl"),saved)
        self.assertEqual(runtime.get_worker_state("najditrain-wsl")["heartbeat_freshness"],"STALE")

    def test_execution_gate_ready_passes(self):
        self.success_result(); gate=runtime.execution_gate(self.job_id); self.assertIn(gate["status"],{"PASS","PASS_WITH_WARNINGS"}); self.assertFalse(gate["blockers"])

    def test_execution_gate_draft_and_dataset_change(self):
        self.success_result(); job=training.get_job(self.job_id); job["status"]="DRAFT"; job["dataset_fingerprint"]="old"; training._atomic_json(training._job_path(self.job_id),job)
        codes={x["code"] for x in runtime.execution_gate(self.job_id)["blockers"]}; self.assertIn("JOB_NOT_READY",codes); self.assertIn("STALE_DATASET_FINGERPRINT",codes)

    def test_execution_gate_model_worker_cuda_and_unsloth_blocks(self):
        self.success_result(); job=training.get_job(self.job_id); job["model_config"]["id"]="missing"; training._atomic_json(training._job_path(self.job_id),job); self.assertIn("MODEL_NOT_FOUND",{x["code"] for x in runtime.execution_gate(self.job_id)["blockers"]})
        job["model_config"]["id"]="ministral-3-3b-unsloth-bnb4"; training._atomic_json(training._job_path(self.job_id),job); runtime.set_worker_state("najditrain-wsl","BUSY"); self.assertIn("WORKER_NOT_IDLE",{x["code"] for x in runtime.execution_gate(self.job_id)["blockers"]})
        result=self.success_result(); result["detected"]["cuda_available"]=False; result["detected"]["packages"]["unsloth"]["available"]=False; training._atomic_json(runtime._runtime_result_path("najditrain-wsl"),result)
        codes={x["code"] for x in runtime.execution_gate(self.job_id)["blockers"]}; self.assertIn("CUDA_NOT_AVAILABLE",codes); self.assertIn("UNSLOTH_NOT_AVAILABLE",codes)

    def test_vram_oom_and_tight(self):
        self.success_result(free=10)
        gate=runtime.execution_gate(self.job_id,live_gpu_probe=lambda rt:self.live_gpu(free=1)); self.assertIn("LIKELY_OOM",{x["code"] for x in gate["blockers"]})
        gate=runtime.execution_gate(self.job_id,live_gpu_probe=lambda rt:self.live_gpu(free=7)); self.assertIn(gate["checks"]["vram"]["status"],{"TIGHT","LIKELY_SAFE"})

    def test_execution_gate_uses_live_vram_not_stale_cached_value(self):
        self.success_result(free=1)
        gate=runtime.execution_gate(self.job_id,live_gpu_probe=lambda rt:self.live_gpu(free=10))
        self.assertNotIn("LIKELY_OOM",{item["code"] for item in gate["blockers"]}); self.assertEqual(gate["checks"]["gpu_measurement"]["measurement"],"LIVE")
        self.success_result(free=10)
        gate=runtime.execution_gate(self.job_id,live_gpu_probe=lambda rt:self.live_gpu(free=1))
        self.assertIn("LIKELY_OOM",{item["code"] for item in gate["blockers"]})

    def test_live_probe_failure_never_falls_back_to_cached_vram(self):
        self.success_result(free=10)
        gate=runtime.execution_gate(self.job_id,live_gpu_probe=lambda rt:self.live_gpu(success=False))
        codes={item["code"] for item in gate["blockers"]}; self.assertIn("LIVE_GPU_PROBE_FAILED",codes); self.assertIn("VRAM_UNKNOWN",codes)

    def test_live_probe_is_fresh_each_gate_run_and_threshold_is_unchanged(self):
        self.success_result(); calls=[]
        def fresh(rt): calls.append(training._now()); return self.live_gpu(free=10)
        one=runtime.execution_gate(self.job_id,live_gpu_probe=fresh); two=runtime.execution_gate(self.job_id,live_gpu_probe=fresh)
        self.assertEqual(len(calls),2); self.assertEqual(one["checks"]["vram"]["estimated_requirement_gb"],two["checks"]["vram"]["estimated_requirement_gb"])
        self.assertEqual(one["checks"]["vram"]["estimated_requirement_gb"],training.estimate_vram(training.get_model("ministral-3-3b-unsloth-bnb4"),training.get_job(self.job_id)["training_config"],{"gpu_vram_total_gb":12,"gpu_vram_free_gb":10})["estimated_requirement_gb"])

    def test_probe_persists_complete_current_evidence_without_changing_runtime_report(self):
        cached=self.success_result(); before=runtime._runtime_result_path("najditrain-wsl").read_bytes()
        outputs=[subprocess.CompletedProcess([],0,json.dumps({"gpu_name":"Test GPU","free_bytes":10*1024**3,"total_bytes":12*1024**3,"used_bytes":2*1024**3})+"\n",""),subprocess.CompletedProcess([],0,"Test GPU, 12288, 2048, 10240, 1\n","")]
        result=self.original_live_probe(runtime.get_runtime("najditrain-wsl"),runner=lambda command,timeout:outputs.pop(0))
        self.assertTrue(result["success"]); self.assertTrue(all(key in result for key in ("probe_source","observed_at","total_bytes","used_bytes","free_bytes")))
        self.assertEqual(before,runtime._runtime_result_path("najditrain-wsl").read_bytes()); self.assertEqual(cached["detected"]["gpu"]["free_vram_mb"],10240)

    def test_command_builder_deterministic_structured_and_spaces(self):
        job=training.get_job(self.job_id); rt=runtime.get_runtime("najditrain-wsl"); rt["default_output_root"]="/home/najdi/output with spaces"
        one=runtime.build_training_command(job,rt); two=runtime.build_training_command(job,rt); self.assertEqual(one,two); self.assertIsInstance(one["args"],list); self.assertIn("'/home/najdi/output with spaces/",one["preview"]); self.assertNotIn("shell",one); self.assertIn("--lora-r",one["args"]); self.assertIn("--epochs",one["args"])
        rt["default_output_root"]="/tmp/a;touch /tmp/pwn"; command=runtime.build_training_command(job,rt); self.assertTrue(any("/tmp/a;touch /tmp/pwn" in value for value in command["args"])); self.assertIn("'/tmp/a;touch /tmp/pwn/",command["preview"])

    def test_epoch_plan_uses_null_in_job_and_minus_one_only_at_adapter_boundary(self):
        cfg=training.validate_training_config({"epochs":2,"max_steps":0})
        self.assertIsNone(cfg["max_steps"])
        plan=training.calculate_plan(30,cfg); self.assertEqual(plan["estimated_total_optimizer_steps"],8); self.assertEqual(plan["trainer_max_steps"],-1)
        job=training.get_job(self.job_id); job["training_config"]=cfg; job["calculated_steps"]=training.calculate_plan(2,cfg)
        command=runtime.build_training_command(job,runtime.get_runtime("najditrain-wsl"),mode="full",attempt_id="attempt-002")
        self.assertEqual(command["args"][command["args"].index("--max-steps")+1],"-1")

    def test_recovery_marks_checkpoint_non_resumable_and_invalidates_artifacts(self):
        job=training.get_job(self.job_id); job.update({"status":"FAILED","production_mode":True,"full_training_status":"FAILED"}); job["training_config"]["max_steps"]=0
        training._atomic_json(training._job_path(self.job_id),job); attempt=self.jobs/self.job_id/"attempts"/"attempt-001"; attempt.mkdir(parents=True)
        training._atomic_json(attempt/"attempt.json",{"attempt_id":"attempt-001","attempt_type":"FULL","status":"FAILED"}); training._atomic_json(self.jobs/self.job_id/"execution-manifest.json",{})
        recovered=runtime.prepare_full_recovery(self.job_id); self.assertEqual(recovered["status"],"RECOVERY_READY"); self.assertIsNone(recovered["job"]["training_config"]["max_steps"])
        metadata=json.loads((attempt/"checkpoint-validation.json").read_text()); self.assertEqual(metadata["status"],"NON_RESUMABLE")
        with self.assertRaises(training.TrainingControlError) as caught: runtime.resume_full_training(self.job_id,"attempt-001","checkpoint-1")
        self.assertEqual(caught.exception.code,"CHECKPOINT_NOT_RESUMABLE")

    def test_dry_run_creates_manifest_without_starting_or_changing_status(self):
        self.success_result(); before=training.get_job(self.job_id)
        valid=subprocess.CompletedProcess([],0,'{"status":"VALID"}\n',"")
        with patch.object(runtime,"_wsl",return_value=valid): result=runtime.dry_run(self.job_id)
        after=training.get_job(self.job_id)
        self.assertIn(result["status"],{"PASS","PASS_WITH_WARNINGS"}); self.assertFalse(result["training_started"]); self.assertEqual(before["status"],after["status"]); self.assertEqual(after["status"],"READY")
        manifest=json.loads((self.jobs/self.job_id/"execution-manifest.json").read_text(encoding="utf-8")); self.assertFalse(manifest["training_started"]); self.assertNotIn("secrets",manifest)

    def test_blocked_dry_run_does_not_create_manifest(self):
        result=runtime.dry_run(self.job_id); self.assertEqual(result["status"],"BLOCKED"); self.assertFalse((self.jobs/self.job_id/"execution-manifest.json").exists())

    def test_no_process_spawn_or_training_start_surface(self):
        source=Path(runtime.__file__).read_text(encoding="utf-8"); self.assertIn("Popen(",source); self.assertNotIn("trainer.train",source); self.assertNotIn("shell=True",source)
        with self.assertRaises(training.TrainingControlError) as caught: runtime.full_training_disabled()
        self.assertEqual(caught.exception.code,"FULL_TRAINING_NOT_ENABLED")

    def prepare_full_authorization(self):
        self.success_result(); job=training.get_job(self.job_id); job["production_mode"]=True; job["provenance"]["smoke_reference"]={"job_id":self.job_id,"attempt_id":"attempt-001"}; training._atomic_json(training._job_path(self.job_id),job)
        smoke=self.jobs/self.job_id/"attempts"/"attempt-001"; smoke.mkdir(parents=True); training._atomic_json(smoke/"result.json",{"status":"PASSED"})
        valid=subprocess.CompletedProcess([],0,'{"status":"VALID"}\n',"")
        with patch.object(runtime,"_wsl",return_value=valid): runtime.dry_run(self.job_id,attempt_type="FULL")
        return job

    def test_full_authorization_requires_exact_ack_and_is_hashed(self):
        self.prepare_full_authorization()
        with self.assertRaises(training.TrainingControlError) as caught: runtime.authorize_full_training(self.job_id,"yes")
        self.assertEqual(caught.exception.code,"AUTHORIZATION_ACK_REQUIRED")
        auth=runtime.authorize_full_training(self.job_id,f"أوافق على بدء Full Training للمهمة {self.job_id}")
        stored=json.loads((self.jobs/self.job_id/"full-training-authorization.json").read_text(encoding="utf-8")); self.assertNotIn(auth["token"],json.dumps(stored)); self.assertEqual(len(stored["token_sha256"]),64)

    def test_full_authorization_single_use_and_full_command(self):
        self.prepare_full_authorization(); auth=runtime.authorize_full_training(self.job_id,f"أوافق على بدء Full Training للمهمة {self.job_id}")
        with patch.object(runtime.threading.Thread,"start",return_value=None): attempt=runtime.start_full_training(self.job_id,auth["token"])
        self.assertEqual(attempt["attempt_type"],"FULL"); self.assertIn("--full-training",attempt["command"]["args"]); self.assertNotIn("--smoke-test",attempt["command"]["args"])
        with self.assertRaises(training.TrainingControlError) as caught: runtime.start_full_training(self.job_id,auth["token"])
        self.assertEqual(caught.exception.code,"AUTHORIZATION_ALREADY_USED")

    def test_full_authorization_rejects_wrong_token(self):
        self.prepare_full_authorization(); runtime.authorize_full_training(self.job_id,f"أوافق على بدء Full Training للمهمة {self.job_id}")
        with self.assertRaises(training.TrainingControlError) as caught: runtime.start_full_training(self.job_id,"wrong")
        self.assertEqual(caught.exception.code,"AUTHORIZATION_JOB_MISMATCH")


if __name__ == "__main__": unittest.main()
