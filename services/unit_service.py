#unit_service.py
from rechnungshelfer.domain.models import Unit


def get_unit_options():
    return [u.value for u in Unit]


def unit_code_to_display(code: str) -> str:
    if code in Unit.__members__:
        return Unit[code].value
    return code


def unit_display_to_code(label: str) -> str:
    for u in Unit:
        if u.value == label:
            return u.name
    return label
