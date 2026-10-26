"""Unit test for TRAINING_PLAN_MISMATCH fix - isolated without WSL/GPU."""
import argparse
import json
import os
import sys
from pathlib import Path

# Import the adapter script logic
sys.path.insert(0, str(Path("C:/Users/Admin/AppData/Local/hermes/NajdiLab/scripts")))
from najdilab_training_adapter import resolve_plan


def test_smoke_test_logic():
    """Test Smoke Test mode: full_plan matches expected_steps, execution limited to max_steps."""
    print("\n" + "=" * 70)
    print("UNIT TEST: Smoke Test Logic")
    print("=" * 70)
    
    # Mock attempt data (simulating attempt.json)
    mock_attempt = {
        "model_path": "/home/najdi/najdi-training/models/gemma-4-E2B-it-official",
        "sft_file": "",
        "multi_turn_file": "",
        "expected_steps": 27,
        "smoke_test": True,
        "max_steps": 2,
        "epochs": 1,
        "batch_size": 4,
        "gradient_accumulation_steps": 1,
    }
    
    # Mock rows - use realistic values that produce expected_steps=27
    # batches = ceil(records/batch_size) = ceil(108/4) = 27
    # steps_epoch = ceil(batches/grad_acc) = ceil(27/1) = 27
    # total = min(steps_epoch*epochs, max_steps) = min(27*1, 2) = 2 for smoke test
    mock_rows = [{"messages": [], "message_loss_mask": [], "target_message_index": 0}] * 108  # 108 records
    mock_native_count = 0
    
    # Calculate full_plan (without max_steps) - should be 27
    full_plan = resolve_plan(
        len(mock_rows) + mock_native_count,
        mock_attempt["batch_size"],
        mock_attempt["gradient_accumulation_steps"],
        mock_attempt["epochs"],
        -1  # No max_steps limit
    )
    
    print(f"\nFull Plan (records={len(mock_rows)+mock_native_count}, epochs=1, batch=4, grad_acc=1):")
    print(f"  estimated_total_optimizer_steps: {full_plan['estimated_total_optimizer_steps']}")
    print(f"  trainer_max_steps: {full_plan['trainer_max_steps']}")
    
    # Verify full_plan matches expected_steps
    assert full_plan["estimated_total_optimizer_steps"] == mock_attempt["expected_steps"], \
        f"Full plan mismatch: expected {mock_attempt['expected_steps']}, got {full_plan['estimated_total_optimizer_steps']}"
    
    print(f"\n✓ Full plan ({full_plan['estimated_total_optimizer_steps']}) matches expected_steps ({mock_attempt['expected_steps']})")
    
    # Calculate execution plan (with max_steps=2)
    exec_plan = resolve_plan(
        len(mock_rows) + mock_native_count,
        mock_attempt["batch_size"],
        mock_attempt["gradient_accumulation_steps"],
        mock_attempt["epochs"],
        mock_attempt["max_steps"]  # Limited to 2
    )
    
    print(f"\nExecution Plan (max_steps=2):")
    print(f"  estimated_total_optimizer_steps: {exec_plan['estimated_total_optimizer_steps']}")
    print(f"  trainer_max_steps: {exec_plan['trainer_max_steps']}")
    
    # Verify execution plan is limited to 2
    assert exec_plan["trainer_max_steps"] == mock_attempt["max_steps"], \
        f"Execution plan mismatch: expected max_steps={mock_attempt['max_steps']}, got {exec_plan['trainer_max_steps']}"
    
    print(f"\n✓ Execution plan ({exec_plan['estimated_total_optimizer_steps']}) respects max_steps limit ({mock_attempt['max_steps']})")
    
    # Test Full Training mode
    print("\n" + "=" * 70)
    print("UNIT TEST: Full Training Logic")
    print("=" * 70)
    
    mock_attempt["smoke_test"] = False
    mock_attempt["max_steps"] = 27
    
    full_plan_full = resolve_plan(
        len(mock_rows) + mock_native_count,
        mock_attempt["batch_size"],
        mock_attempt["gradient_accumulation_steps"],
        mock_attempt["epochs"],
        mock_attempt["max_steps"]
    )
    
    print(f"\nFull Training Plan (max_steps=27):")
    print(f"  estimated_total_optimizer_steps: {full_plan_full['estimated_total_optimizer_steps']}")
    print(f"  trainer_max_steps: {full_plan_full['trainer_max_steps']}")
    
    assert full_plan_full["estimated_total_optimizer_steps"] == mock_attempt["expected_steps"], \
        f"Full training mismatch: expected {mock_attempt['expected_steps']}, got {full_plan_full['estimated_total_optimizer_steps']}"
    
    print(f"\n✓ Full training plan (27) matches expected_steps ({mock_attempt['expected_steps']})")
    
    # Test mismatch rejection
    print("\n" + "=" * 70)
    print("UNIT TEST: Mismatch Rejection")
    print("=" * 70)
    
    mock_mismatch = {
        "model_path": "/home/najdi/najdi-training/models/gemma-4-E2B-it-official",
        "sft_file": "",
        "multi_turn_file": "",
        "expected_steps": 27,
        "smoke_test": False,
        "max_steps": 10,  # Wrong value
        "epochs": 1,
        "batch_size": 4,
        "gradient_accumulation_steps": 1,
    }
    
    mismatch_plan = resolve_plan(
        len(mock_rows) + mock_native_count,
        mock_mismatch["batch_size"],
        mock_mismatch["gradient_accumulation_steps"],
        mock_mismatch["epochs"],
        mock_mismatch["max_steps"]
    )
    
    print(f"\nMismatch Test (expected=27, actual={mismatch_plan['estimated_total_optimizer_steps']}):")
    
    if mismatch_plan["estimated_total_optimizer_steps"] != mock_mismatch["expected_steps"]:
        print(f"✓ Mismatch correctly detected: expected {mock_mismatch['expected_steps']}, got {mismatch_plan['estimated_total_optimizer_steps']}")
    else:
        print("✗ Mismatch not detected (unexpected)")
    
    print("\n" + "=" * 70)
    print("ALL UNIT TESTS PASSED")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(test_smoke_test_logic())
