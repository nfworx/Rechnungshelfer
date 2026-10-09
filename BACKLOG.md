# Backlog – Rechnungshelfer

## Arbeitsweise

- Nur ein größeres Thema gleichzeitig bearbeiten.
- Jede Aufgabe zuerst analysieren und planen; Umsetzung erst nach Freigabe.
- Erledigte Schritte einzeln testen und vom Benutzer committen lassen.

## Feststehende fachliche Entscheidungen

- Rechnung, Gutschrift und Getreideabrechnung bleiben getrennte Eingabemasken.
- Der steuerlich führende Beleg einer Getreideabrechnung ist die **Gutschrift**.
- Eine AMIC-Sammel-Final-Gutschrift ist bereits der steuerliche Beleg. Sie wird als
  Quelle für dieselbe digitale Gutschrift verwendet und nicht als Anlage behandelt.
- Die ursprüngliche AMIC-PDF wird ausschließlich gelesen, nicht verändert, kopiert,
  eingebettet oder durch den Rechnungshelfer dauerhaft gespeichert.
- Die aus einer AMIC-PDF erzeugte XML- beziehungsweise PDF-Ausgabe stellt denselben
  Beleg mit derselben Gutschriftnummer, demselben Datum und denselben Beträgen dar.
- Erkannte Gutschriftnummern und Rechnungsnummern bleiben vor der Übernahme
  bestätigungs- und editierbar; zusätzliche Präfixe werden nicht erzeugt.
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

### 1. AMIC-Sammel-Final-Gutschrift erkennen

- Eine vorhandene AMIC-PDF als nicht vertrauenswürdige, unveränderte Importquelle
  einlesen und das Format „Sammel-Final-Gutschrift“ erkennen.
- Vor der Verarbeitung Dateityp, Dateigröße und Lesbarkeit prüfen; die Quelldatei
  weder verändern noch kopieren oder dauerhaft im Rechnungshelfer speichern.
- Vorhandene PDF-Textschichten nutzen und bei unzureichender Qualität kontrolliert
  auf OCR zurückgreifen.
- Gutschriftnummer, Ausstellungsdatum, Lieferungen, Analysewerte, Mengen, Preise,
  Beträge, Steuersatz und Summen als Importentwurf erfassen.

### 2. Prüfpflichtigen Importentwurf anzeigen

- Erkannte Werte zusammen mit Fundstelle, Quelltext und Erkennungssicherheit in
  einer Prüfansicht darstellen.
- Einzelbeträge, Nettosumme, Umsatzsteuer und Gesamtbetrag rechnerisch
  gegeneinander prüfen und Abweichungen deutlich anzeigen.
- Unsichere oder widersprüchliche Werte niemals automatisch übernehmen.
- Manuelle Korrektur und ausdrückliche Bestätigung aller zu übernehmenden Daten
  ermöglichen.

### 3. Bestätigte Daten in eine editierbare Gutschrift übernehmen

- In der Prüfansicht eine ausdrückliche Schaltfläche „Geprüfte Daten in Formular
  übernehmen“ anbieten und nur einen vollständig geprüften Entwurf übernehmen.
- Aus dem bestätigten Entwurf eine Gutschrift mit dem vorhandenen Dokumenttyp und
  derselben Gutschriftnummer erzeugen; keinen zweiten steuerlichen Beleg anlegen.
- Jede Lieferung als eigene Gutschriftposition abbilden und vorhandene
  Getreide-Mapping- und Berechnungslogik soweit sinnvoll wiederverwenden.
- Erkannte Abzüge und Analysewerte nachvollziehbar in die Positionsdarstellung
  übernehmen, ohne Beträge ein zweites Mal zu berechnen.
- Den übernommenen Beleg in der bestehenden Gutschriftenmaske vollständig
  bearbeitbar machen.

### 4. Importierte Gutschrift speichern und wieder öffnen

- Ausschließlich die bestätigten strukturierten Belegdaten über die bestehenden
  Speicherwege sichern; die ursprüngliche AMIC-PDF bleibt außerhalb der Anwendung.
- Die Gutschrift nach einem Neustart vollständig und ohne Abhängigkeit von der
  ursprünglichen PDF wieder laden können.
- Falls Schemaänderungen erforderlich werden, ausschließlich eine versionierte
  Migration mit Backup, Transaktion und verständlicher Fehleranzeige verwenden.
- Speicherung, Neustart, erneutes Laden und Fehlerfälle mit einer temporären
  Datenbank testen.

### 5. Dieselbe Gutschrift als PDF oder XRechnung ausgeben

- Aus den bestätigten strukturierten Daten wahlweise eine lesbare PDF oder eine
  XRechnung erzeugen; beide Ausgaben repräsentieren denselben Beleg.
- Gutschriftnummer, Datum, Parteien, Positionen, Steuersatz und Summen in beiden
  Formaten konsistent halten.
- Für die XRechnung den vorhandenen Gutschriftprozess mit Typcode `389` verwenden
  und die Ausgabe mit XSD und KoSIT validieren.
- Die ursprüngliche AMIC-PDF weder einbetten noch als Anlage referenzieren.

### 6. Fachlicher End-to-End-Abnahmetest

- Eine reale AMIC-Sammel-Final-Gutschrift mit mehreren Lieferungen und 7,8 Prozent
  Umsatzsteuer von der PDF-Auswahl bis zum bestätigten Beleg durchspielen.
- Unsichere OCR-Werte, rechnerische Gegenprüfung und manuelle Korrektur gezielt
  testen.
- Speichern, Neustart, erneutes Laden sowie PDF- und XRechnungsausgabe einschließlich
  KoSIT prüfen.
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

## Später – Weitere Importformate und lernende Regelvorschläge

- Nach dem fachlich abgenommenen AMIC-Import bei Bedarf weitere PDF-Layouts und
  Abrechnungsprogramme als jeweils kontrollierte Importformate ergänzen.
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
