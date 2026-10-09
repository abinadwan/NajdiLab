from pathlib import Path
from unittest.mock import patch

from app import runtime_control


def test_selected_model_identity_and_revision_reach_loader_arguments(tmp_path: Path):
    job = {
        "job_id": "train-20261009-999", "dataset_version": "candidate-v1",
        "model_config": {"id": "chosen-model", "path": "/models/chosen", "revision": "rev-42"},
        "training_config": {}, "calculated_steps": {"estimated_total_optimizer_steps": 3},
    }
    runtime = {"dataset_root": "/datasets", "default_output_root": "/outputs", "python_path": "/venv/python", "training_script_path": "/app/train.py"}
    with patch.object(runtime_control.training, "_version_dir", return_value=tmp_path):
        command = runtime_control.build_training_command(job, runtime)
    args = command["args"]
    assert args[args.index("--model-path") + 1] == "/models/chosen"
    assert args[args.index("--model-id") + 1] == "chosen-model"
    assert args[args.index("--model-revision") + 1] == "rev-42"

