"""Zentrale SQLite-Verbindung, Pfade und Transaktionsgrenze."""

from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app_info import DATA_DIR_ENV

from .migrations import migrate_database


def get_exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def get_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    data_dir = Path(override) if override else get_exe_dir() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path() -> Path:
    return get_data_dir() / "invoices.db"


def open_database(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.execute("PRAGMA busy_timeout=10000")
        migrate_database(connection)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
    except Exception:
        connection.close()
        raise
    return connection


class Database:
    """Besitzt die gemeinsame Verbindung aller Repositories."""

    def __init__(self, db_path: Path | str | None = None):
        self.connection = open_database(db_path)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        try:
            with self.connection:
                yield
        except Exception:
            self.connection.rollback()
            raise

    def close(self) -> None:
        self.connection.close()
