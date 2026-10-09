from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clean_export import create_clean_export  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the immutable gold-v005-clean Training View")
    parser.add_argument(
        "--source-export",
        type=Path,
        default=ROOT / "exports" / "gold-v004",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "exports" / "gold-v005-clean",
    )
    parser.add_argument(
        "--eval-report-dir",
        type=Path,
        default=ROOT / "reports" / "eval-v2",
    )
    args = parser.parse_args()
    result = create_clean_export(args.source_export, args.output, args.eval_report_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
