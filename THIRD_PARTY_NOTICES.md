# Drittanbieter-Komponenten

Rechnungshelfer verwendet und verteilt Komponenten Dritter. Deren jeweilige
Lizenzbedingungen bleiben unberuehrt.

## KoSIT XML Validator

- Projekt: https://github.com/itplr-kosit/validator
- Lizenz: Apache License 2.0
- Zusaetzliche Hinweise und Lizenzen befinden sich im ausgelieferten
  Standalone-JAR, insbesondere unter `LICENSE.validator` und `META-INF/NOTICE`.

## Validator-Konfiguration XRechnung

- Projekt: https://github.com/itplr-kosit/validator-configuration-xrechnung
- Lizenz: Apache License 2.0

## Universal Business Language 2.1

- Herausgeber: OASIS Open
- Spezifikation: https://docs.oasis-open.org/ubl/os-UBL-2.1/UBL-2.1.html
- Die verwendeten Runtime-Schemata sind Bestandteil der mitgelieferten
  XRechnung-Konfiguration.

## Java-Laufzeit

Die portable Eclipse-Temurin-JRE wird nicht im Git-Repository gespeichert. Das
freigegebene Originalpaket und sein SHA-256 sind unter
`build_support/java_trusted_releases.json` dokumentiert. Die Lizenz- und
Hinweistexte werden im One-Folder-Paket innerhalb der Laufzeit unter
`external/java/legal/` und `external/java/NOTICE` mitgeliefert.

## PDFium und pypdfium2

- Projekt: https://github.com/pypdfium2-team/pypdfium2
- Lizenz: Apache License 2.0 oder BSD 3-Clause; fuer die gebuendelten
  PDFium-Binaerdateien gelten zusaetzliche Drittanbieterlizenzen.
- Die Lizenzdateien der Wheel-Distribution werden durch PyInstaller zusammen
  mit der Python-Abhaengigkeit ausgeliefert und muessen vor jedem Release im
  One-Folder-Paket kontrolliert werden.

## Tesseract OCR und Sprachdaten

- Projekt: https://github.com/tesseract-ocr/tesseract
- Laufzeit: Tesseract 5.5.3.20260724, Apache License 2.0
- Bildverarbeitung: Leptonica 1.87.0, BSD 2-Clause
- Deutsche Sprachdaten: Bestandteil der freigegebenen Windows-Distribution;
  Tesseract-Sprachdaten stehen unter Apache License 2.0.
- Weitere DLL-Abhaengigkeiten und ihre Lizenzbedingungen stammen aus der
  offiziellen Windows-Release-Distribution. Ihre Hinweise sind vor der
  Veroeffentlichung des portablen Pakets gegen dessen Dateiinhalt zu pruefen.
- Quelle, Installer-Hash und Hash der ausgelieferten Laufzeitauswahl stehen in
  `build_support/tesseract_trusted_releases.json`.

<!-- BEGIN GENERATED EXTERNAL COMPONENTS -->
## Mitgelieferte externe Komponenten

Dieser Abschnitt wird vom Release-Werkzeug aus `external/components.json` erzeugt.

| Komponente | Mitgelieferter Stand |
|---|---|
| Java-Laufzeit | `21.0.12.1` |
| KoSIT XML Validator | `1.6.3` |
| Tesseract OCR mit deutschen Sprachdaten | `5.5.3.20260724` |
| XRechnung-Konfiguration | `2026.01.31` |
<!-- END GENERATED EXTERNAL COMPONENTS -->
