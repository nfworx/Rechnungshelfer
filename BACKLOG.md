# Backlog – Rechnungshelfer

## Arbeitsweise

- Nur ein größeres Thema gleichzeitig bearbeiten.
- Jede Aufgabe zuerst analysieren und planen; Umsetzung erst nach Freigabe.
- Erledigte Schritte einzeln testen und vom Benutzer committen lassen.

## Feststehende fachliche Entscheidungen

- Rechnung, Gutschrift und Getreideabrechnung bleiben getrennte Eingabemasken.
- Der steuerlich führende Beleg einer Getreideabrechnung ist die **Gutschrift**.
- Eine interne oder externe Getreideabrechnung ist Berechnungsnachweis beziehungsweise
  Anlage zur Gutschrift und erhält keinen eigenen steuerlichen Nummernkreis.
- Gutschriftnummern und Rechnungsnummern werden manuell und ohne Präfix eingegeben.
- Eine Abrechnung verwendet einen ausdrücklich ausgewählten Steuersatz für alle
  enthaltenen Lieferungen.
- OCR-Ergebnisse und daraus abgeleitete Regeln dürfen niemals ungeprüft übernommen
  werden, sondern müssen als bestätigungspflichtiger Entwurf angezeigt werden.

## Aktuell in Entwicklung

- Keine aktive Aufgabe. Im neuen Chat genau einen Punkt aus P1 auswählen.

## P0 – Kritische Fehler und Datenrisiken

- Unbeabsichtigtes Überschreiben von Geschäftspartnerstammdaten durch ältere Belege verhindern.
- Beim PDF-Rückimport eingebettete Rechnungsdaten validieren und Widersprüche zu sichtbaren Belegdaten erkennen.

## P1 – Wichtige Funktionen in empfohlener Reihenfolge

### 1. Allgemeines Anlagenmodell und Oberfläche

- Ein dokumenttypunabhängiges Anlagenmodell entwerfen; nicht auf AMIC oder Getreide
  fest verdrahten.
- Zunächst PDF-Anlagen unterstützen und Dateiname, Beschreibung, MIME-Typ,
  Dateigröße und SHA-256-Prüfsumme erfassen.
- In Rechnung und Gutschrift Anlagen hinzufügen, anzeigen, öffnen und entfernen.
- Fremde Dateien als nicht vertrauenswürdig behandeln, Dateityp und Größe prüfen
  und keine Datei beim bloßen Auswählen verändern.
- Die manuelle Gutschrift muss auch dann funktionieren, wenn eine AMIC-Abrechnung
  nur als Anlage beigefügt und nicht inhaltlich erkannt wird.

### 2. Anlagen sicher speichern und wieder laden

- Vor der Implementierung entscheiden, ob Anlagen als verwaltete Dateien im
  Datenverzeichnis oder als Datenbank-BLOB gespeichert werden. Backup,
  Portabilität, Dateigröße, Löschen und verwaiste Dateien berücksichtigen.
- Notwendige Schemaänderungen ausschließlich über eine versionierte Migration mit
  Backup, Transaktion und verständlicher Fehleranzeige durchführen.
- Anlagen zusammen mit dem Beleg konsistent speichern, laden und löschen; keine
  stillen Überschreibungen vorhandener Dateien.
- Speicherung und Neustart mit einer echten temporären Migration testen.

### 3. Anlagen in den Ausgabeformaten

- Eine externe Abrechnung auf der Gutschrift eindeutig als Anlage bezeichnen und
  auf die Gutschriftnummer beziehen.
- Anlagen in der XRechnung fachgerecht über `AdditionalDocumentReference`
  referenzieren beziehungsweise einbetten und mit KoSIT validieren.
- Für den PDF-Versand festlegen und umsetzen, ob Anlagen angehängt, mit dem PDF
  zusammengeführt oder gemeinsam als Paket ausgegeben werden.
- Die Anlage darf nicht wie ein zweiter steuerlicher Beleg erscheinen.

### 4. Getreideabrechnung speichern und wieder öffnen

- Einen unveränderlichen Abrechnungssnapshot aus Lieferungen, Analysewerten,
  Regelwerksversion, Berechnungsschritten, Steuersatz und Summen speichern.
- Die erzeugte Gutschrift eindeutig mit diesem Snapshot verknüpfen, ohne die
  Berechnung ein zweites Mal in den Rechnungspositionen anzuwenden.
- Abrechnungen laden, nachvollziehbar anzeigen und bei Änderungen bewusst als neue
  Berechnung beziehungsweise Version behandeln.
- Schemaänderung, Backup, Migration, Fehlerfall und Neustart testen.

### 5. Getreideabrechnung als lesbare Gutschriftanlage

- Für intern berechnete Abrechnungen eine übersichtliche Anlage mit allen
  Lieferungen, Ursprungsmengen, Abrechnungsmengen, Analysewerten und einzelnen
  Mengen-, Preis- und Kostenänderungen erzeugen.
- Benutzertexte statt interner Codes wie `dockage` oder technischer Faktoren
  ausgeben.
- Gutschrift und Berechnungsanlage verwenden dieselbe Gutschriftnummer; es gibt
  keine zusätzliche sichtbare Abrechnungsnummer.
- Mehrseitiges PDF, Seitenumbrüche und größere Lieferungsmengen testen.

### 6. Fachlicher End-to-End-Abnahmetest

- Einen realistischen AMIC-Anwendungsfall mit mehreren Lieferungen, 7,8 Prozent
  Umsatzsteuer, manueller Gutschriftnummer und externer Anlage durchspielen.
- Speichern, Neustart, erneutes Laden, PDF und XRechnung einschließlich KoSIT prüfen.
- Gemeinsam mit Hauptanwender und Steuerberater Bezeichnung, Steuersatz,
  Pflichtangaben und Darstellung einmal fachlich abnehmen.

## P2 – Technische Verbesserungen

- GitHub Actions für automatische Tests bei Pushes einrichten.
- Testdaten und Beispiellieferungen klar vom Produktivbetrieb trennen.
- Große GUI-Module bei Bedarf aufteilen und vereinfachen.
- Wiederholte Test-Fixtures und Hilfsfunktionen zusammenführen, ohne fachlich
  unterschiedliche Tests zu verlieren; keine pauschale Testlöschung.
- Tesseract-Distribution verschlanken und Repository-Größe optimieren.
- Datenbank-Backup und Wiederherstellung praktisch testen.

## Später – OCR und lernende Regelvorschläge

- Externe Getreideabrechnungen, insbesondere AMIC-Abrechnungen, per OCR einlesen.
- Erkannte Kopfdaten, Lieferungen, Analysewerte, Abzüge und Summen in einer
  Prüfansicht den sichtbaren Originalstellen gegenüberstellen.
- Nur ausdrücklich bestätigte Werte in eine Gutschrift oder interne
  Getreideabrechnung übernehmen; bei unsicherer Erkennung manuelle Eingabe und
  unveränderte Originalanlage ermöglichen.
- Nach mehreren bestätigten AMIC-Abrechnungen Abweichungen zu den aktiven Regeln
  erkennen und neue oder geänderte Regeln lediglich vorschlagen.
- Regelvorschläge erklären, mit Beispieldaten testen und erst nach Freigabe als
  neue Regelwerksversion aktivieren; bestehende Abrechnungen bleiben unverändert.

## Erledigt

- Geschäftspartner besitzen stabile interne IDs und getrennte Kunden-/Lieferantenrollen;
  sichtbare Geschäftspartnernummern bleiben numerisch und editierbar.
- Mehrere Lieferungen, Getreidearten, Analysewerte sowie konfigurierbare Mengen-,
  Preis- und Kostenregeln sind in der Getreideabrechnung vorhanden.
- Regelwerke sind je Getreideart auswählbar und versionierbar; Braugerste, Hafer
  und Raps sind ergänzt, Triticale wurde entfernt.
- Feldvalidierung, Datumsauswahl, Grenzfallunterdrückung für Null-Abzüge und die
  nachvollziehbare Tabellenaufschlüsselung sind umgesetzt.
- Nettoabrechnungsbetrag, Umsatzsteuer und Auszahlungsbetrag werden getrennt
  berechnet und angezeigt.
- Eine berechnete Getreideabrechnung kann als bearbeitbare Gutschrift mit einer
  Position je Lieferung in die vorhandene Gutschriftenmaske übernommen werden.
- Der erzeugte Beleg nutzt die bestehenden JSON-, Datenbank-, PDF- und XML-Wege;
  Pflichtfeldprüfung, XSD, PDF-Erzeugung und Speichern/Laden sind automatisiert
  getestet.
