# Backlog – Rechnungshelfer

## Aktuell in Entwicklung

Nur ein größeres Thema gleichzeitig bearbeiten.

- Getreideabrechnung vollständig integrieren.

## Eingang – spontane Ideen

Neue Ideen ungefiltert sammeln. Noch nicht bewerten oder implementieren.

- _Noch keine Einträge._

## P0 – Kritische Fehler und Datenrisiken

- Unbeabsichtigtes Überschreiben von Geschäftspartnerstammdaten durch ältere Belege verhindern.
- Beim PDF-Rückimport eingebettete Rechnungsdaten validieren und Widersprüche zu sichtbaren Belegdaten erkennen.

## P1 – Wichtige Funktionen

- Getreideabrechnung speichern und wieder laden.
- Umsatzsteuer und Auszahlungsbetrag in die Fachlogik integrieren.
- Getreide-Gutschrift mit eindeutiger Belegnummer, PDF und vorhandener XML-Infrastruktur vollständig erzeugen.
- Allgemeine Beleganlagen unterstützen, damit externe Abrechnungen, Wiegescheine
  und andere Nachweise eindeutig einer Gutschrift oder Rechnung zugeordnet werden
  können. Die Gutschrift bleibt der führende steuerliche Beleg; Anlagen erhalten
  keinen eigenen steuerlichen Nummernkreis.
- Integrationstests mit echten Datenbankmigrationen, Speicherung und Neustart ergänzen.

## P2 – Technische Verbesserungen

- GitHub Actions für automatische Tests bei Pushes einrichten.
- Testdaten und Beispiellieferungen klar vom Produktivbetrieb trennen.
- Große GUI-Module bei Bedarf aufteilen und vereinfachen.
- Tesseract-Distribution verschlanken und Repository-Größe optimieren.
- Datenbank-Backup und Wiederherstellung praktisch testen.

## Später / Vielleicht

Noch nicht priorisierte Verbesserungen und neue Funktionen.

- Externe Getreideabrechnungen, insbesondere AMIC-Abrechnungen, per OCR einlesen.
  Erkannte Lieferungen, Analysewerte und Abzüge nur als prüfbaren Entwurf
  übernehmen; erst nach ausdrücklicher Benutzerbestätigung eine Gutschrift
  erzeugen. Wenn die Erkennung scheitert, soll weiterhin eine manuelle Gutschrift
  mit der externen Abrechnung als Anlage möglich sein.

## Erledigt

Abgeschlossene Aufgaben entfernen oder bei Bedarf kurz vermerken. Größere Änderungen werden in `CHANGELOG.md` dokumentiert.

- _Noch keine Einträge._
