"""Declare historical private-artifact prerequisites without hiding corruption."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def requires_private_artifacts(*names):
    missing = [name for name in names if not (ROOT / name).is_file()]
    return unittest.skipIf(bool(missing), 'Private historical artifacts not distributed: ' + ', '.join(missing))
