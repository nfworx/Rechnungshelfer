# rechnungshelfer/repositories/master_data_repository.py
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from rechnungshelfer.repositories.database import get_data_dir


class MasterDataRepository:
    def __init__(self, path: Path | None = None):
        if path is None:
            path = get_data_dir() / "master_data.json"

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, seller, payment):
        data = {
            "seller": self._model_to_dict(seller),
            "payment": self._model_to_dict(payment),
        }

        content = json.dumps(data, indent=2, ensure_ascii=False)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def load_into(self, seller, payment):
        if not self.path.exists():
            return seller, payment

        data = json.loads(self.path.read_text(encoding="utf-8"))

        self._apply_dict(seller, data.get("seller", {}))
        self._apply_dict(payment, data.get("payment", {}))

        return seller, payment

    def apply_to_invoice(self, invoice):
        if not self.path.exists():
            return invoice

        seller = deepcopy(invoice.seller)
        payment = deepcopy(invoice.payment)

        self.load_into(seller, payment)

        invoice.seller = seller
        invoice.payment = payment

        return invoice

    def _model_to_dict(self, model):
        ignored = {
            "required_fields",
            "readonly_fields",
            "FIELD_LABELS_DE",
        }

        return {
            key: value
            for key, value in model.__dict__.items()
            if not key.startswith("_") and key not in ignored
        }

    def _apply_dict(self, model, data):
        for key, value in data.items():
            # Alte Stammdaten mit leerer Käuferreferenz auf den Standardwert anheben.
            if key == "buyer_reference" and not str(value or "").strip():
                continue
            if self._is_legacy_placeholder(key, value):
                continue
            if hasattr(model, key):
                setattr(model, key, value)

    @staticmethod
    def _is_legacy_placeholder(key, value):
        text = str(value or "").strip()
        exact_placeholders = {
            ("name", "Musterfirma"),
            ("postcode", "XXXXX"),
            ("city", "Musterstadt"),
            ("email", "info@musterfirma.de"),
            ("contact_name", "Max Mustermann"),
            ("account_holder", "Musterfirma"),
        }
        if (key, text) in exact_placeholders:
            return True
        if key == "street" and text.lower().startswith(("musterstra", "musterstraß")):
            return True
        if key in {"phone", "vat", "tax_number", "registry_number", "iban", "bic"}:
            return bool(text) and set(text.upper()) == {"X"}
        return False
