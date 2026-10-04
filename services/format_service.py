#format_service.py
from decimal import Decimal, InvalidOperation

def parse_de(value: str) -> Decimal:
    """Konvertiert deutschen String (1.234,56) in Decimal"""
    value = str(value or "").strip()
    if not value:
        return Decimal("0.00")

    try:
        return Decimal(value.replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Ungültige Zahl: {value}") from exc


def format_de(value) -> str:
    """Für GUI/PDF Anzeige: deutsches Format"""
    try:
        if isinstance(value, Decimal):
            d = value

        elif isinstance(value, str):
            value = value.strip()

            # Deutsches Format erkennen
            if "," in value:
                d = Decimal(value.replace(".", "").replace(",", "."))
            else:
                # Englisches/DB-Format: 76.97
                d = Decimal(value)

        else:
            d = Decimal(str(value))

        s = f"{d:.2f}"
        int_part, dec_part = s.split(".")
        int_part = "{:,}".format(int(int_part)).replace(",", ".")
        return f"{int_part},{dec_part}"

    except (InvalidOperation, ValueError, TypeError):
        return "0,00"
