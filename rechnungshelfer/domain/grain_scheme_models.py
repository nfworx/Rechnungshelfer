"""Persistierte Entwuerfe und unveraenderliche Getreide-Regelversionen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GrainSchemeDraft:
    grain_type_code: str
    harvest_year: int
    name: str
    payload: Mapping[str, Any]
    updated_at: str = ""


@dataclass(frozen=True)
class GrainSchemeVersionRecord:
    id: int
    grain_type_code: str
    harvest_year: int
    revision: int
    name: str
    payload: Mapping[str, Any]
    activated_at: str

    @property
    def display_version(self) -> str:
        return f"{self.harvest_year}.{self.revision}"
