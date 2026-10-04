# Rechnungshelfer Release-Werkzeug

`release_tool.py` ist das interne Kommandozeilenwerkzeug des Herausgebers. Es
wird nicht an Endnutzer ausgeliefert und veraendert Git niemals selbst.

## 1. Nur pruefen

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py check
```

Der Befehl ist read-only gegenueber den Quelldateien und prueft:

- Projektvoraussetzungen und vorhandenen Changelogabschnitt
- neuestes stabiles KoSIT-Release
- generierte Komponentenabschnitte in README und Drittanbieterhinweisen
- Python-Abhaengigkeiten mit `pip-audit`

Mit `--with-tests` wird zusaetzlich die komplette Testsuite ausgefuehrt.

## 2. Externe Komponenten aktualisieren

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py update-components
```

Dieser Befehl darf ausschliesslich externe Komponenten, deren Register und die
eindeutig markierten generierten Dokumentationsabschnitte aendern. Aktuell ist
KoSIT automatisch angebunden. Nach der Bestaetigung werden Download, Groesse
und SHA-256 geprueft und die komplette Testsuite ausgefuehrt. Bei einem Fehler
werden alle Aenderungen dieses Schrittes zurueckgerollt.

`version.py`, Changelog und frei geschriebene README-Texte bleiben unveraendert.
Die erzeugten Aenderungen werden danach bewusst als eigener Git-Commit
kontrolliert.

## 3. Release vorbereiten

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py prepare --version 1.0.1
```

`prepare` darf die technische Programmversion und generierte
Komponentenabschnitte synchronisieren. Der Changelogabschnitt fuer die
angegebene Version muss bereits manuell vorhanden sein und wird nicht vom
Werkzeug erfunden oder veraendert. Aus diesem Abschnitt entsteht eine
Release-Notes-Datei unter `build/release-notes-<VERSION>.md`.

Anschliessend werden Git-Diff und Releasebeschreibung kontrolliert und
committed.

## 4. Build ausfuehren

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py build --channel stable
```

Der Build-Befehl veraendert keine Quelldateien. Er:

1. kontrolliert Version, Changelog, generierte Metadaten und Git-Arbeitsbaum,
2. fuehrt `pip-audit` aus,
3. fuehrt die komplette Testsuite aus,
4. fragt vor dem One-Folder-Build nach,
5. erstellt ZIP, SHA-256-Datei und Update-Manifest,
6. kontrolliert Artefakte und Datenschutzregeln.

Ein stabiler Build sollte aus einem sauberen Commit erfolgen. Fuer lokale
Testbauten existiert `--allow-dirty`. Falls Git in der aktuellen Shell nicht
verfuegbar ist, kann die Kontrolle nur bewusst mit `--skip-git-check`
uebergangen werden. Diese Option ist fuer eine offizielle Veroeffentlichung
nicht empfohlen.

## Protokolle

```text
build/logs/release-tool.log
build/logs/release-report.json
```

Jeder Zwischenschritt meldet sofort `INFO`, `OK`, `WARNUNG`, `FEHLER` oder
`AUSGABE`. Dateiinhalte und Zugangsdaten werden nicht protokolliert.

## Verantwortungsgrenzen

- Das Werkzeug committed, taggt, pusht und veroeffentlicht nicht automatisch.
- Python-Pakete werden geprueft, aber nicht waehrend eines Releases automatisch aktualisiert.
- Release Notes und Changelogtexte bleiben menschlich gepflegt.
- Java und XRechnung werden dokumentiert, besitzen aber noch keinen automatischen Quellenadapter.
- UBL 2.1 ist ein festgelegter Dokumentstandard und kein automatisch anzuhebendes Werkzeug.

`release_builder.py` bleibt nur als kompatibler Einstiegspunkt erhalten und
erwartet dieselben Unterbefehle. Neue Dokumentation und Aufrufe verwenden
ausschliesslich `release_tool.py`.
