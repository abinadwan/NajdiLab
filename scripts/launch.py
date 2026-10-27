"""Validate interpreter/configuration before starting this checkout."""
import os
from pathlib import Path
import runpy
import sys

from local_runtime import check_runtime


def main():
    check_runtime()
    value = os.environ.get('NAJDILAB_PORT', '8770')
    try:
        port = int(value)
    except ValueError:
        raise SystemExit('NAJDILAB_PORT must be an integer from 1 to 65535.')
    if not 1 <= port <= 65535:
        raise SystemExit('NAJDILAB_PORT must be an integer from 1 to 65535.')
    os.environ.setdefault('NAJDILAB_NO_DEMO', '1')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    runpy.run_module('app.server', run_name='__main__')


if __name__ == '__main__':
    main()
