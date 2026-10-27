"""Verify historical analysis paths can be relocated without executing the tools."""
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "export_v007_e1_ollama.py": {"PROJECT": "", "REPORT_JSON": "reports/v007-e1-export-report.json", "REPORT_MD": "reports/v007-e1-export-report.md"},
    "audit_v006_metrics.py": {"DATA_DIR": "exports/gold-v006-clean", "REPORT_DIR": "reports"},
    "audit_v006_metrics_v2.py": {"DATA_DIR": "exports/gold-v006-clean", "REPORT_DIR": "reports"},
    "audit_v006_metrics_v3.py": {"DATA_DIR": "exports/gold-v006-clean", "REPORT_DIR": "reports"},
    "verify_audit.py": {"SFT_PATH": "exports/gold-v006-clean/sft.jsonl", "MULTI_TURN_PATH": "exports/gold-v006-clean/multi_turn.jsonl", "EVAL_PATH": "exports/gold-v006-clean/text_sft_eval.jsonl", "REPORTS_DIR": "reports"},
    "dataset_influence_audit.py": {"BASE": "exports/gold-v006-clean", "REPORT_JSON": "reports/gold-v006-dataset-influence-audit.json", "REPORT_MD": "reports/gold-v006-dataset-influence-audit.md"},
    "measure_v006_overlap.py": {"DATA_DIR": "exports/gold-v006-clean", "REPORT_DIR": "reports"},
    "gold_v007_balancing.py": {"SRC_DIR": "exports/gold-v006-clean", "DST_DIR": "exports/gold-v007-balanced"},
    "gold_v007_balancing_new.py": {"SRC_DIR": "exports/gold-v006-clean", "DST_DIR": "exports/gold-v007-balanced"},
}


class ScriptPortabilityTests(unittest.TestCase):
    def test_analysis_paths_follow_relocated_checkout(self):
        # Evaluate only imports and path assignments, never module-level analysis/export code.
        with tempfile.TemporaryDirectory(prefix="najdilab-path-test-") as temporary:
            checkout = Path(temporary) / "checkout with spaces"
            for name, expected in PATHS.items():
                with self.subTest(script=name):
                    tree = ast.parse((ROOT / "scripts" / name).read_text(encoding="utf-8"))
                    names = {"ROOT", *expected}
                    statements = [ast.Import(names=[ast.alias(name="os")]), ast.ImportFrom(module="pathlib", names=[ast.alias(name="Path")], level=0)]
                    statements += [node for node in tree.body if isinstance(node, ast.Assign) and all(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
                    namespace = {"__file__": str(checkout / "scripts" / name)}
                    exec(compile(ast.fix_missing_locations(ast.Module(body=statements, type_ignores=[])), name, "exec"), namespace)
                    for variable, relative in expected.items():
                        self.assertEqual(Path(namespace[variable]), checkout / relative)

    def test_windows_launchers_have_no_fixed_developer_profile(self):
        for relative in ("run.ps1", "scripts/backup.ps1", "scripts/NajdiLab_Autostart.ps1"):
            with self.subTest(launcher=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotRegex(source, r"(?i)[a-z]:[\\/]Users[\\/]")


if __name__ == "__main__":
    unittest.main()
