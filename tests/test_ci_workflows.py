"""Guards for the CI trigger policy and test wiring (text checks; PyYAML is not a CI dependency)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
HEAVY = ["checks.yml", "public-source-candidate.yml"]


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", HEAVY)
def test_superseded_runs_are_cancelled(name):
    text = _text(name)
    assert "concurrency:\n  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}\n  cancel-in-progress: true\n" in text


@pytest.mark.parametrize("name", HEAVY)
def test_draft_pull_request_pushes_do_not_start_heavy_jobs(name):
    text = _text(name)
    assert "types: [opened, synchronize, reopened, ready_for_review]" in text
    assert "workflow_dispatch:" in text
    jobs = text.split("\njobs:\n", 1)[1]
    job_blocks = re.split(r"\n  (?=[a-z][\w-]*:\n)", "\n" + jobs)
    for block in [b for b in job_blocks if b.strip()]:
        assert "    if: github.event_name != 'pull_request' || github.event.pull_request.draft == false" in block
        assert re.search(r"\n    timeout-minutes: \d+", block)


def test_every_node_unit_test_runs_in_source_checks():
    text = _text("checks.yml")
    for path in sorted((ROOT / "tests").glob("*.test.cjs")):
        assert f"tests/{path.name}" in text, f"{path.name} is not run by Source checks"


@pytest.mark.parametrize("script", ["tests/chat-browser.cjs", "tests/chat-enhancements-browser.cjs", "tests/review-restrictions-browser.cjs", "tests/i18n-browser.cjs", "tests/a11y-browser.cjs"])
def test_browser_acceptance_runs_with_a_step_timeout(script):
    text = _text("checks.yml")
    assert re.search(rf"- run: node (?:--test )?{re.escape(script)}\n        timeout-minutes: \d+", text)
