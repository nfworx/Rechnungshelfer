"""Startbestaetigung zwischen neuer Anwendung und externem Updater."""

import sys
import tempfile
from pathlib import Path


READY_ARGUMENT = "--update-ready-file"
READY_PREFIX = "Rechnungshelfer-ready-"


def ready_file_from_argv(argv: list[str] | None = None) -> Path | None:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        index = args.index(READY_ARGUMENT)
        candidate = Path(args[index + 1]).resolve()
    except (ValueError, IndexError, OSError):
        return None
    temp_root = Path(tempfile.gettempdir()).resolve()
    if candidate.parent != temp_root or not candidate.name.startswith(READY_PREFIX):
        return None
    return candidate


def signal_ready(argv: list[str] | None = None) -> bool:
    path = ready_file_from_argv(argv)
    if path is None:
        return False
    try:
        with path.open("x", encoding="ascii") as ready_file:
            ready_file.write("ready\n")
        return True
    except OSError:
        return False
