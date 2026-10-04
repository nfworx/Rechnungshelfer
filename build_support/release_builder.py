"""Kompatibler Einstiegspunkt; neue Aufrufe verwenden release_tool.py."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from build_support.release_tool import main


if __name__ == "__main__":
    raise SystemExit(main())
