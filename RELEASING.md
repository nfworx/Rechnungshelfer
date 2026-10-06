# Release-Prozess

Ein Release besteht aus getrennten, kontrollierbaren Schritten. Das interne
Werkzeug veraendert Git nicht automatisch.

## 1. Zustand pruefen

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py check --with-tests
```

Der Befehl aendert keine Quelldateien. Ein gemeldetes Komponentenupdate muss
nicht zwingend Bestandteil desselben Releases werden.

## 2. Komponentenpflege bei Bedarf

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py update-components
```

Danach den Git-Diff kontrollieren und Komponentenupdate sowie generierte
Dokumentationsabschnitte als eigenen Commit sichern. Programmversion und
Changelog werden hierbei nicht veraendert.

Neue KoSIT-Versionen muessen vor der Installation mit ihrem unabhaengig
kontrollierten SHA-256 in `build_support/kosit_trusted_releases.json`
freigegeben werden. Das Werkzeug prueft danach Download und Weiterleitungen,
zeigt den Hash an und fragt vor der ersten Ausfuehrung des JAR erneut nach.
Komponentenupdates niemals aus einer als Administrator gestarteten Shell
ausfuehren.

## 3. Releasebeschreibung manuell pflegen

Vor `prepare` muss `CHANGELOG.md` einen Abschnitt der Zielversion enthalten,
beispielsweise:

```text
## [1.0.0] - 2026-10-04
```

Release Notes und fachliche Texte werden bewusst kontrolliert und nicht vom
Werkzeug erfunden.

## 4. Technische Metadaten vorbereiten

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py prepare --version 1.0.0
```

Dieser Schritt synchronisiert `version.py` und die generierten
Komponentenabschnitte. Die extrahierten Release Notes liegen danach unter:

```text
build/release-notes-1.0.0.md
```

Danach Git-Diff kontrollieren und den vorbereiteten Quellstand committen.

## 5. Stabilen Build erstellen

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py build --channel stable
```

Der Build startet nur aus einem vorbereiteten Zustand, fuehrt `pip-audit` und
alle Tests aus und fragt vor PyInstaller nochmals nach. Fuer ein offizielles
Release muss der Git-Arbeitsbaum sauber sein.

Neben ZIP, Pruefsumme und Manifest entsteht ein JSON-Groessenbericht. Er misst
den vollstaendigen Build, das komprimierte ZIP, die Python-Anwendung ohne
externe Laufzeiten sowie Java, KoSIT-Validator, XRechnung, UBL und Babel
getrennt und dient als Ausgangsbasis fuer spaetere Releasevergleiche.

Nur fuer beaufsichtigte Testbauten:

```powershell
.\.venv\Scripts\python.exe build_support\release_tool.py build --channel test --allow-dirty
```

## 6. Datenschutzkontrolle

Folgende Inhalte duerfen weder committed noch veroeffentlicht werden:

- `data/`, Datenbanken und Datenbanksicherungen
- `master_data.json`
- exportierte Rechnungs- und Gutschrift-PDFs
- erzeugte KoSIT-Berichte
- Zugangsdaten, Tokens, private Schluessel und Zertifikate

Die eingecheckten XML-Dateien unter `tests/fixtures/validator/` enthalten nur
synthetische Testdaten. Build und Artefaktpruefung brechen bei erkannten
Benutzer- oder Berichtsdaten ab.

## 7. Git-Tag und GitHub-Release

Erst nach erfolgreicher Artefaktpruefung:

```powershell
git tag -a v1.0.0 -m "Rechnungshelfer 1.0.0"
git push origin main
git push origin v1.0.0
```

Der GitHub-Release-Tag muss exakt zur Manifestversion passen. Hochgeladen
werden:

```text
Rechnungshelfer-1.0.0-win64.zip
Rechnungshelfer-1.0.0-win64.zip.sha256
Rechnungshelfer-1.0.0-stable-manifest.json
Rechnungshelfer-1.0.0-size-report.json
```

Als Beschreibung dient `build/release-notes-1.0.0.md`.

## 8. Updatefunktion kontrollieren

Der automatische Updatecheck erwartet das neueste stabile GitHub-Release im
oeffentlichen Repository. GitHub-Tag, Manifestversion, Manifest-SHA-256,
ZIP-Groesse und ZIP-SHA-256 muessen uebereinstimmen.

Vor dem naechsten stabilen Release wird ein Update von der vorherigen Version
auf einer Testkopie durchgefuehrt. Der portable `data/`-Ordner muss dabei
unveraendert erhalten bleiben.
