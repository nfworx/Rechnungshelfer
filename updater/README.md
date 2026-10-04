# Updater-Architektur

Es gibt **zwei fachlich und technisch getrennte Updatewege**:

| Updateweg | Aufgabe | Beispiel | Code |
|---|---|---|---|
| Programmupdate fuer Benutzer | Aktualisiert Rechnungshelfer selbst | `1.0.0` auf `1.0.1` | `Updater.exe` / `application_update.py` |
| Komponentenpflege fuer Herausgeber | Aktualisiert den Projektinhalt vor einem Release | KoSIT `1.6.2` auf `1.6.3` | `build_support/update_external_components.py` |

`runner.py` gehoert ausschliesslich zur ausgelieferten `Updater.exe` und
akzeptiert nur Programmmanifeste. `core.py` enthaelt gemeinsam
benoetigte Sicherheitsbausteine: Manifestpruefung, Download, SHA-256,
sicheres Entpacken, Transaktion und Rollback.

```text
Benutzer:
Updater.exe / runner.py
`-- application_update.py          Rechnungshelfer.exe und _internal/

Herausgeber/Projektpflege:
build_support/update_external_components.py
`-- external_components_update.py  Java, KoSIT, XRechnung oder UBL

core.py                             gemeinsame Sicherheitslogik
data/                               wird von keinem Updateweg veraendert
```

Die Anwendung kopiert `Updater.exe` vor dem Start in ein festes Verzeichnis
unter `%TEMP%`. Danach beendet sie sich und schliesst die SQLite-Datenbank.

## Sicherheitsregeln

- Remotequellen sind nur ueber HTTPS erlaubt.
- Paketgroesse und SHA-256 muessen exakt zum Manifest passen.
- ZIP-Pfadtraversal, symbolische Links und doppelte Pfade werden abgelehnt.
- Ein Anwendungsarchiv darf keinen `data/`-Ordner enthalten.
- Erlaubte Anwendungspfade sind `Rechnungshelfer.exe`, `Updater.exe` und `_internal/`.
- Komponenten duerfen nur ihre fest im Code hinterlegten Zielpfade ersetzen.
- Austausch erfolgt ueber Staging und Rollback auf demselben Laufwerk.
- KoSIT-Updates muessen einen Java-Smoke-Test bestehen.
- Nach einem Programmupdate muss die neue Anwendung ihren Start bestaetigen.

Der Onlinecheck liest ausschliesslich das neueste stabile Release aus
`nfworx/Rechnungshelfer`. Er verlangt GitHubs SHA-256-Digest fuer das Manifest
und prueft das Programm-ZIP gegen Manifest sowie GitHub-Assetmetadaten. Das
gepruefte Manifest wird vor dem Start von `Updater.exe` lokal fixiert.

## Manifesttypen

Beispiele liegen in:

- `updater/update-manifest.example.json`
- `updater/components-manifest.example.json`

Komponenten und ihre erlaubten Ziele:

| ID | Zielpfad |
|---|---|
| `kosit-validator` | `external/kosit/validator` |
| `xrechnung-configuration` | `external/kosit/xrechnung` |
| `ubl-schemas` | `external/ubl` |
| `java-runtime` | `external/java` |

Die installierten Komponentenstaende stehen in `external/components.json`.

## Manueller Kommandozeilentest

Komponentenpflege im Quellprojekt:

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py check
.\.venv\Scripts\python.exe build_support\release_tool.py update-components
```

`check` veraendert keine Quelldateien. `update-components` fragt das neueste
stabile KoSIT-Release beim offiziellen `itplr-kosit/validator`-Repository ab
und aktualisiert erst nach ausdruecklicher Bestaetigung. Groesse und
SHA-256-Digest muessen zu den Release-Metadaten passen.

Ein vollstaendiges Programmupdate sollte nur an einer Kopie eines
One-Folder-Builds getestet werden. Die normale Benutzeroberflaeche startet den
Updater ueber **Updates** und beendet Rechnungshelfer danach automatisch.
