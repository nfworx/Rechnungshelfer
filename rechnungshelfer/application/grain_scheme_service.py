"""Anwendungsfaelle fuer bearbeitbare und freigegebene Regelwerke."""

from __future__ import annotations

from rechnungshelfer.domain.grain_scheme_models import GrainSchemeDraft


class GrainSchemeApplicationService:
    def __init__(self, *, database, repository):
        self._database = database
        self._repository = repository

    def load_drafts(self, harvest_year: int):
        return self._repository.list_drafts(_valid_year(harvest_year))

    def save_drafts(self, harvest_year: int, drafts: dict[str, dict]) -> None:
        year = _valid_year(harvest_year)
        with self._database.transaction():
            for grain_type_code, payload in drafts.items():
                self._repository.save_draft(
                    GrainSchemeDraft(
                        grain_type_code=_required(grain_type_code, "Getreideart"),
                        harvest_year=year,
                        name=_draft_name(payload, grain_type_code),
                        payload=payload,
                    ),
                    commit=False,
                )

    def activate(self, grain_type_code: str, harvest_year: int, payload: dict):
        draft = GrainSchemeDraft(
            grain_type_code=_required(grain_type_code, "Getreideart"),
            harvest_year=_valid_year(harvest_year),
            name=_draft_name(payload, grain_type_code),
            payload=payload,
        )
        with self._database.transaction():
            self._repository.save_draft(draft, commit=False)
            return self._repository.activate(draft, commit=False)

    def list_versions(self, grain_type_code: str, harvest_year: int):
        return self._repository.list_versions(
            _required(grain_type_code, "Getreideart"),
            _valid_year(harvest_year),
        )


def _draft_name(payload: dict, grain_type_code: str) -> str:
    return str(payload.get("name") or f"{grain_type_code} Standard").strip()


def _required(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} fehlt.")
    return normalized


def _valid_year(value: int) -> int:
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Erntejahr ist ungültig.") from exc
    if year < 2000 or year > 2200:
        raise ValueError("Erntejahr muss zwischen 2000 und 2200 liegen.")
    return year
