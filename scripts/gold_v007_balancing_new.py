import json, re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]

SRC_DIR = ROOT / 'exports/gold-v006-clean'
DST_DIR = ROOT / 'exports/gold-v007-balanced'

# The rest of the script is omitted here; refer to the original plan.
