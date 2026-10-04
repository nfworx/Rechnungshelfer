# Rechnungshelfer

Desktop-Anwendung zum Erstellen, Verwalten und Exportieren von Rechnungen und
Gutschriften. Belege koennen als PDF und als XRechnung-XML (UBL 2.1) ausgegeben
und vor dem Export mit XSD sowie dem KoSIT-Validator geprueft werden.

**Rechnungen und Gutschriften einfach erstellen.**

Sichtbarer Name, technischer Bezeichner, EXE-Name und Hersteller werden zentral
in `app_info.py` gepflegt. Die Programmversion steht ausschliesslich in
`version.py`.

## Funktionen

- Rechnungen und Gutschriften/Self-Billing erstellen
- Kunden- und Lieferantenverwaltung
- Eigene Stammdaten und Zahlungsdaten verwalten
- Mehrere Umsatzsteuersaetze und Einheiten verwenden
- Optionale abweichende Lieferadresse
- Automatische Summen- und Steuerberechnung
- PDF-Export
- XRechnung-Export nach UBL 2.1
- XSD- und KoSIT-Validierung
- Testrechnung und Testgutschrift direkt ins Formular laden
- Lokale SQLite-Datenbank mit Migration und Sicherung

## Voraussetzungen

- Windows 10 oder neuer, 64 Bit
- Python 3.12 fuer die Entwicklung
- Vollstaendige portable Java-Laufzeit unter `external/java/`
- KoSIT-Validator und XRechnung-Konfiguration unter `external/kosit/`

Die portable Java-Laufzeit wird wegen ihrer Groesse nicht im Repository
versioniert. Nur `java.exe` zu kopieren reicht nicht aus; Java benoetigt das
vollstaendige Runtime-Verzeichnis.

Hinweise zu den mitgelieferten Komponenten und deren Lizenzen stehen in
`THIRD_PARTY_NOTICES.md`.

## Entwicklung starten

```powershell
git clone https://github.com/nfworx/Rechnungshelfer.git
cd Rechnungshelfer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Unter `tests/fixtures/validator/` liegen eine reproduzierbare Testrechnung und
Testgutschrift. Beide werden in der Testsuite durch XSD und KoSIT validiert.
Die XML-Dateien koennen so neu erzeugt werden:

```powershell
.\.venv\Scripts\python.exe -m tests.generate_validator_fixtures
```

### Anwendung schnell testen

Ueber **Testbeleg laden** kann eine vollstaendig ausgefuellte Testrechnung oder
Testgutschrift ins Formular geladen und sofort als PDF beziehungsweise XML
exportiert werden. Das Laden veraendert die Datenbank nicht. Erst
**Beleg speichern** uebernimmt den Testbeleg dauerhaft.

## One-Folder-Build

Build-Abhaengigkeiten installieren und Paket erstellen:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build.ps1
```

Der Build-Befehl des Release-Werkzeugs prueft `requirements.txt` vor der
Testsuite mit `pip-audit` und bricht bei bekannten Schwachstellen ab.

Der Build erzeugt:

```text
dist/<APP_ID>/<APP_ID>.exe
dist/<APP_ID>/Updater.exe
release/<APP_ID>-<VERSION>-win64.zip
release/<APP_ID>-<VERSION>-win64.zip.sha256
release/<APP_ID>-<VERSION>-<CHANNEL>-manifest.json
```

Die Windows-Dateieigenschaften werden beim Build aus `app_info.py` und
`version.py` generiert. Details zum Release-Ablauf stehen in `RELEASING.md`.

## Versionierung

Das Projekt verwendet Semantic Versioning:

- `PATCH`, beispielsweise `1.0.1`: kompatible Fehlerbehebung
- `MINOR`, beispielsweise `1.1.0`: neue kompatible Funktion
- `MAJOR`, beispielsweise `1.0.0`: inkompatible Aenderung oder stabile Hauptversion

Zu jedem Release gehoeren ein Git-Tag wie `v1.0.1`, ein Eintrag in
`CHANGELOG.md`, das versionierte ZIP-Paket und dessen SHA-256-Pruefsumme.

Die Datenbank hat unabhaengig davon eine eigene Schema-Version. Programmversion
und Datenbankschema duerfen nicht miteinander verwechselt werden.

## Portable Datenablage

Rechnungshelfer arbeitet immer portabel und legt seine Daten im eigenen
Programmordner ab:

```text
Rechnungshelfer/
|-- Rechnungshelfer.exe
|-- Updater.exe
|-- data/
|   |-- invoices.db
|   `-- master_data.json
`-- _internal/
```

Der gesamte Ordner kann auf einen anderen beschreibbaren Datentraeger kopiert
werden. Ein Einsatz unter `C:\Program Files` ist fuer diesen Modus ungeeignet,
weil normale Benutzer dort nicht schreiben duerfen.

## Zwei getrennte Updatearten

Rechnungshelfer unterscheidet klar zwischen:

- **Programmupdate:** aktualisiert Rechnungshelfer selbst, beispielsweise von
  Version `1.0.0` auf `1.0.1`.
- **Komponentenpflege des Herausgebers:** aktualisiert vor einem neuen Release
  externe Pruefwerkzeuge wie KoSIT, Java oder UBL-Schemata im Quellprojekt.

Endnutzer sehen und verwenden nur den Programm-Updater. Die Komponentenpflege
ist ein separates Wartungsskript unter `build_support/` und wird nicht in der
Benutzeroberflaeche oder `Updater.exe` angeboten.

### Programmupdate und One-Folder-Prinzip

Ein Programmupdate ersetzt den vollstaendigen One-Folder-Build. Eine laufende
EXE kann ihren eigenen Ordner unter Windows nicht sicher austauschen. Deshalb
wird `Updater.exe` vor dem Update nach `%TEMP%` kopiert und von dort
gestartet. Er wartet auf das Ende des Hauptprogramms, prueft das Paket, tauscht
den Programmordner ueber ein Staging-Verzeichnis aus und startet die neue
Version. Erst nachdem diese ihren erfolgreichen Start bestaetigt hat, wird die
Rollback-Kopie entfernt.

Der Herausgeber kann Java, KoSIT, die XRechnung-Konfiguration oder UBL-Schemata
vor einem Release getrennt pflegen. Die aktualisierten Komponenten werden erst
mit dem naechsten vollstaendigen Rechnungshelfer-Release an Benutzer verteilt.
Das interne Werkzeug `build_support/release_tool.py` trennt die rein lesende
Pruefung, Komponentenpflege, Releasevorbereitung und den eigentlichen Build in
eigene Befehle. Ein Build aktualisiert niemals Komponenten, Version oder
Dokumentation nebenbei. Jeder Schritt meldet sofort Erfolg, Warnung oder Fehler.
Details stehen in `build_support/README.md`.

Der Updater darf `data/` niemals entfernen oder ueberschreiben. Updater-Quelle,
Architektur und Manifest liegen unter `updater/`.

Der gebaute Rechnungshelfer prueft nach dem sichtbaren Programmstart in einem
Hintergrundthread das neueste stabile Release im offiziellen GitHub-Repository.
Nur wenn eine neuere Version vorliegt, erscheint ein Updatefenster. Ueber
**Updates** kann dieselbe Pruefung jederzeit manuell gestartet werden; dort
werden auch "aktuell" und Netzwerkfehler sichtbar gemeldet.

Der Updatecheck verwendet ausschliesslich das fest hinterlegte Repository
`nfworx/Rechnungshelfer`. GitHub-Tag, Manifestversion, Manifest-SHA-256,
ZIP-Groesse und ZIP-SHA-256 muessen uebereinstimmen. Ein Zugriffstoken oder
Zugriff auf Rechnungsdaten ist dafuer nicht erforderlich.

### Release-Hosting

Das oeffentliche GitHub-Repository dient spaeter auch als Release-Hosting. Fuer
Updates muessen das Manifest und das Release-ZIP unter stabilen, oeffentlich
lesbaren HTTPS-Adressen erreichbar sein. Zu einem Release gehoeren:

- stabiles Update-Manifest als Release-Asset
- versioniertes One-Folder-ZIP
- SHA-256-Pruefsumme
- kurze Versionshinweise

Der Release-Tag muss zur Version passen, beispielsweise `v1.0.1`. Manifest und
ZIP muessen aus demselben GitHub-Release stammen. Ein Zugriffstoken wird nicht
in Rechnungshelfer eingebaut.

## Datenablage

- Entwicklung: `data/`
- Portable Anwendung: `data/` direkt neben `Rechnungshelfer.exe`
- Testweise Uebersteuerung: Umgebungsvariable `RECHNUNGSHELFER_DATA_DIR`

Im portablen Modus gehoeren die Benutzerdaten zum transportierbaren Ordner,
bleiben aber vom austauschbaren Programminhalt logisch getrennt. Vor
Datenbankmigrationen wird automatisch eine Sicherung erstellt.

Rechnungsdaten, Stammdaten, exportierte PDFs und erzeugte Validator-Berichte
duerfen nicht in Git oder in ein Release-Paket aufgenommen werden. Der
Buildprozess bricht ab, wenn er solche Dateien im One-Folder-Paket findet.
Temporaere HTML-Pruefberichte werden beim Beenden und spaetestens beim naechsten
Programmstart automatisch entfernt.

## Projektstruktur

```text
assets/                 Schriftarten und Bilder
build_support/          Internes Release-Werkzeug und Buildhilfen
external/               Java, KoSIT und UBL-Schemata
gui_ctk/                CustomTkinter-Oberflaeche
repositories/           SQLite- und Stammdatenzugriff
services/               PDF-, XML- und Validierungslogik
tests/                  Unit-, Regressions- und Validator-Tests
updater/                Updatearchitektur und Manifest
app_info.py             Produktmetadaten
version.py              Programmversion
controller.py           Anwendungslogik
models.py               Datenmodelle und Berechnung
main.py                 Programmeinstieg
```

<!-- BEGIN GENERATED EXTERNAL COMPONENTS -->
## Mitgelieferte externe Komponenten

Dieser Abschnitt wird vom Release-Werkzeug aus `external/components.json` erzeugt.

| Komponente | Mitgelieferter Stand |
|---|---|
| Java-Laufzeit | `21.0.12.1` |
| KoSIT XML Validator | `1.6.2` |
| OASIS UBL-Schemata | `2.1` |
| XRechnung-Konfiguration | `2026.01.31` |
<!-- END GENERATED EXTERNAL COMPONENTS -->

## Fachlicher Hinweis

Die technische Validierung ersetzt keine steuerliche oder rechtliche Pruefung.
Bei B2B-Empfaengern kann als interne Kaeuferreferenz beispielsweise
`BUCHHALTUNG` verwendet werden. Oeffentliche Auftraggeber stellen fuer BT-10 in
der Regel eine Leitweg-ID bereit.

## Lizenz

Der Quellcode ist oeffentlich einsehbar. Bis eine ausdrueckliche Lizenzdatei
hinzugefuegt wird, werden keine Nutzungs-, Aenderungs- oder
Weiterverbreitungsrechte eingeraeumt.
