"""Darstellung temporärer HTML-Prüfberichte in der Benutzeroberfläche."""

import webbrowser

from rechnungshelfer.services.temp_report_service import create_temp_report


def show_html_report(report_html: str) -> None:
    if not report_html or not report_html.strip():
        raise ValueError("Kein Prüfbericht vorhanden.")

    report_path = create_temp_report(report_html)
    webbrowser.open(report_path.as_uri())
