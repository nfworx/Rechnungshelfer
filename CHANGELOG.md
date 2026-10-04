# Changelog

Alle wesentlichen Aenderungen dieses Projekts werden hier dokumentiert. Das
Versionsschema folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Added

- Der separate Programm-Updater zeigt waehrend Warten, Download, Pruefung und Installation ein sichtbares Fortschrittsfenster mit gruenem Balken

### Changed

- Die aktualisierte Anwendung wird erst gestartet, nachdem der Fortschritt sichtbar 100 Prozent erreicht hat

## [1.0.1] - 2026-10-04

### Changed

- KoSIT XML Validator von Version 1.6.2 auf 1.6.3 aktualisiert
- Komponentenpruefung akzeptiert kuenftige semantische KoSIT-Versionen, ohne auf einen veralteten exakten Versionswert festgelegt zu sein

### Security

- KoSIT-Downloads muessen neben dem GitHub-Digest einem lokal freigegebenen SHA-256 entsprechen
- HTTPS wird auch nach Download-Weiterleitungen erneut erzwungen
- Vor der ersten Ausfuehrung eines heruntergeladenen KoSIT-JAR werden SHA-256 und eine zweite Bestaetigung verlangt
- Veraenderliche GitHub-Releases werden sichtbar gemeldet und KoSIT-Updates aus einer Administrator-Shell abgebrochen
- Der eingecheckte KoSIT-Validator wird in der Testsuite gegen die lokale Vertrauensliste geprueft

### Fixed

- Ein erfolgreiches KoSIT-Update wird nicht mehr durch eine fest auf Version 1.6.2 gesetzte Build-Pruefung zurueckgerollt
- Update-Service-Tests simulieren neue Releases relativ zur aktuellen Programmversion und bleiben nach `prepare` gueltig
- Abgelehnte unsichere Download-Weiterleitungen hinterlassen keine leere Zieldatei

## [1.0.0] - 2026-10-04

### Added

- Erste oeffentliche Version von Rechnungshelfer
- Rechnungen und Gutschriften/Self-Billing erstellen und verwalten
- PDF- und XRechnung-Export nach UBL 2.1
- Lokale XSD- und KoSIT-Validierung
- Kunden-, Lieferanten- und Stammdatenverwaltung
- Testrechnung und Testgutschrift direkt ins Formular laden
- Gepufferter Formularwechsel zur Reduzierung sichtbarer Zeichenartefakte
- Zentral gepflegte Produkt- und Versionsmetadaten
- PyInstaller-One-Folder-Build mit Windows-Dateiversion
- Versioniertes Release-ZIP mit SHA-256-Pruefsumme
- Separater Updater fuer vollstaendige One-Folder-Updates
- Nicht blockierender Updatecheck beim Programmstart und ueber den Updates-Button
- Updatehinweis mit Versionsvergleich und Link zu den GitHub-Versionshinweisen
- Internes Release-Werkzeug mit getrennten Befehlen fuer Pruefung, Komponentenpflege, Vorbereitung und Build
- Lokale Testmanifeste mit Paketgroesse und SHA-256-Pruefung
- Automatisches Rollback bei fehlgeschlagenem Austausch oder Programmstart

### Security

- Benutzerdaten werden ausschliesslich im portablen `data/`-Ordner gespeichert
- Datenbanken, Stammdaten, PDFs und Validator-Berichte werden von Git ausgeschlossen
- Der Build bricht ab, wenn Benutzer- oder Berichtsdaten im Release-Paket erkannt werden
- Updatearchive werden gegen Pfadtraversal, symbolische Links und unbekannte Zielpfade geschuetzt
- Temporaere HTML-Pruefberichte werden beim Programmstart und beim Beenden automatisch entfernt
- Python-Abhaengigkeiten werden vor einem Release automatisch auf bekannte Schwachstellen geprueft
- Pillow wurde auf Version 12.3.0 aktualisiert
