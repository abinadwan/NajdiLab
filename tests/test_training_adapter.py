import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from najdilab_training_adapter import resolve_plan


def test_epoch_plan_resolves_eight_steps_without_override():
    plan=resolve_plan(30,1,8,2.0,-1)
    assert plan["optimizer_steps_per_epoch"] == 4
    assert plan["estimated_total_optimizer_steps"] == 8
    assert plan["trainer_max_steps"] == -1


def test_positive_override_is_preserved():
    plan=resolve_plan(30,1,8,2.0,5)
    assert plan["estimated_total_optimizer_steps"] == 5
    assert plan["max_steps_override"] == 5
