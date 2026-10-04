"""Typisierte Fehler der Anwendungsschicht."""

from rechnungshelfer.domain.models import Buyer


class CustomerDuplicateError(ValueError):
    """Ein neuer Kunde überschneidet sich mit vorhandenen Kundendaten."""

    def __init__(self, duplicates: list[Buyer]):
        self.duplicates = tuple(duplicates)
        super().__init__("Möglicher doppelter Kunde gefunden.")

    def format_duplicates(self) -> str:
        return "\n".join(
            f"- {buyer.customer_number} | {buyer.name}"
            for buyer in self.duplicates
        )
