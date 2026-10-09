# Backlog – Rechnungshelfer

## Arbeitsweise

- Nur ein größeres Thema gleichzeitig bearbeiten.
- Jede Aufgabe zuerst analysieren und planen; Umsetzung erst nach Freigabe.
- Erledigte Schritte einzeln testen und vom Benutzer committen lassen.

## Feststehende fachliche Entscheidungen

- Rechnung, Gutschrift und Getreideabrechnung bleiben getrennte Eingabemasken.
- Der steuerlich führende Beleg einer Getreideabrechnung ist die **Gutschrift**.
- Die Getreideabrechnung wird als strukturierte Sonderform der Gutschrift behandelt.
  Lieferungen, Analysewerte sowie Mengen- und Preisänderungen bleiben im
  Rechnungshelfer fachlich strukturiert und werden nicht dauerhaft auf freie
  Beschreibungstexte reduziert.
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
- Bei einer manuell erstellten Getreideabrechnung ist das ausgewählte Regelwerk
  für Mengen- und Preisänderungen führend. Bei einem PDF-/OCR-Import bleiben die
  bestätigten Werte des vorhandenen Belegs führend; ein vorhandenes Regelwerk wird
  ausschließlich für eine zusätzliche, nicht verändernde Plausibilitätsprüfung
  verwendet.
- Lieferbetrag, Nettosumme, Umsatzsteuer, Gesamtbetrag und Auszahlungsbetrag werden
  auch bei Importen immer rechnerisch geprüft. Finanzielle Abweichungen blockieren
  Übernahme und Ausgabe; Abweichungen der Analyse- und Abzugsberechnung vom
  Regelwerk erzeugen dagegen nur einen Hinweis und verändern keine Belegwerte.

## Aktuell in Entwicklung

- P1.6 „Belegworkflow, Summenfeld und Menüführung vereinheitlichen“. Vor dem
  größeren Oberflächenumbau zuerst die Überschreibwarnung für bestehende
  Getreidegutschriften korrigieren und anschließend den Getreide-Workflow in
  kleinen, einzeln getesteten Schritten vereinheitlichen.

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
- Für jede Lieferung den Lieferbetrag aus Abrechnungsmenge und Abrechnungspreis je
  Tonne sowie gegebenenfalls festen Betragsanpassungen berechnen. Anschließend die
  Nettosumme als Summe der Lieferbeträge, die Umsatzsteuer aus Nettosumme und
  Steuersatz, den Gesamtbetrag aus Netto und Steuer sowie den Auszahlungsbetrag
  unter Berücksichtigung der Abschlagszahlung prüfen.
- Abweichungen bei Lieferbetrag, Nettosumme, Umsatzsteuer, Gesamtbetrag oder
  Auszahlungsbetrag als blockierende Fehler mit Belegwert, Prüfwert und Differenz
  anzeigen.
- Wenn ein passendes Regelwerk eindeutig verfügbar ist, importierte Mengen- und
  Preisabzüge zusätzlich dagegen prüfen. Abweichungen in der OCR-Prüfansicht je
  Analysezeile beispielsweise als „Beleg: -28 kg / Regelwerk: -30 kg“ darstellen,
  aber nur als nicht blockierende Warnung behandeln.
- Wenn kein passendes Regelwerk eindeutig verfügbar ist, auf die Regelprüfung
  verzichten und lediglich kenntlich machen, dass nur die finanziellen
  Zusammenhänge geprüft wurden.
- Unsichere oder widersprüchliche Werte niemals automatisch übernehmen.
- Manuelle Korrektur und ausdrückliche Bestätigung aller zu übernehmenden Daten
  ermöglichen.

### 3. Bestätigte Daten in eine editierbare Getreidegutschrift übernehmen

- In der Prüfansicht eine ausdrückliche Schaltfläche „Als Getreidegutschrift
  übernehmen“ anbieten und nur einen vollständig geprüften Entwurf übernehmen.
- Aus dem bestätigten Entwurf eine strukturierte Getreidegutschrift mit derselben
  Gutschriftnummer erzeugen; keinen zweiten steuerlichen Beleg anlegen und nicht
  in die allgemeine Gutschriftenmaske wechseln.
- Importierte und manuell erstellte Getreidegutschriften auf dasselbe fachliche
  Dokumentmodell abbilden. Bei importierten Belegen die bestätigten Endwerte nicht
  durch ein Regelwerk überschreiben; eine mögliche Regelwerksberechnung nur als
  getrennten Vergleichswert verwenden.
- Lieferungen, Analysewerte, Mengen- und Preisänderungen sowie bestätigte Beträge
  strukturiert und vollständig editierbar halten.
- Herkunft des Belegs sowie erkannte Regelwerksabweichungen einschließlich der
  verwendeten Regelwerksversion strukturiert speichern, damit das Prüfverhalten
  und die Warnhinweise nach erneutem Laden nachvollziehbar bleiben. PDF-Datei,
  OCR-Rohtext und Erkennungsmetadaten weiterhin nicht dauerhaft speichern.
- In der Hauptmaske bei einer bestätigten Regelwerksabweichung ausschließlich ein
  Ausrufezeichensymbol an der betroffenen Analysezeile anzeigen. Der Hoverhinweis
  erklärt knapp, dass die Abzugsberechnung vom beim Import geprüften Regelwerk
  abweicht; konkrete Vergleichswerte bleiben der OCR-Prüfansicht vorbehalten.
- Abschlagszahlungen im strukturierten Beleg als eigenen Wert erhalten. PDF- und
  XML-Ausgabe erst freigeben, wenn der Betrag dort gemäß P1.5 konsistent
  dargestellt wird.
- Den übernommenen Beleg im Getreideabrechnungs-Arbeitsbereich vollständig
  bearbeitbar machen; die Übernahme speichert ihn noch nicht automatisch.

### 4. Importierte Getreidegutschrift speichern und wieder öffnen

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
- In der XRechnung jede Lieferung als eigene Position mit Abrechnungsmenge in
  Kilogramm, Abrechnungspreis je Tonne über die Preisbasis 1.000 Kilogramm und
  bestätigtem Lieferbetrag abbilden. Analysewerte,
  Ursprungsmenge, Basispreis sowie Mengen- und Preisänderungen als stabile
  Artikelmerkmale (BG-32/BT-160/BT-161) und zusätzlich lesbar ausgeben.
- Abschlagszahlungen als bezahlten Betrag (BT-113 beziehungsweise
  `PrepaidAmount`) ausgeben und den Auszahlungsbetrag konsistent berechnen.
- PDF- und XML-Ausgabe bei finanziellen Inkonsistenzen sperren. Bestätigte
  Regelwerksabweichungen aus einem Import lediglich als Warnung behandeln und die
  Ausgabe dadurch nicht blockieren.
- Die ursprüngliche AMIC-PDF weder einbetten noch als Anlage referenzieren.

### 6. Belegworkflow, Summenfeld und Menüführung vereinheitlichen

- Rechnung, Gutschrift und Getreideabrechnung trotz ihrer unterschiedlichen
  Fachmodelle nach demselben verständlichen Bedienmuster erstellen, bearbeiten,
  speichern, leeren und wieder öffnen können.
- Eine manuell erstellte Getreideabrechnung beim Speichern validieren, intern als
  strukturierte Getreidegutschrift übernehmen und direkt in der Datenbank sichern;
  den zusätzlichen Bedienschritt „Getreidegutschrift erstellen“ dafür entfernen.
- In der manuellen Eingabemaske Ursprungsmenge, Analysewerte und Basispreis als
  Eingaben behandeln und Abrechnungsmenge, Abrechnungspreis, Lieferbetrag und
  Gesamtsummen automatisch über das Regelwerk beziehungsweise die verbindliche
  Summenlogik berechnen.
- Bei importierten Belegen bestätigte Abrechnungsmenge und Abrechnungspreis als
  Belegwerte verwenden. Lieferbetrag und Gesamtsummen weiterhin automatisch
  berechnen und gegen die importierten Referenzwerte prüfen; Regelwerksvergleiche
  verändern diese Werte nicht.
- Gespeicherte Getreidegutschriften im Getreide-Arbeitsbereich laden und dort
  unmittelbar weiterbearbeiten. Das separate Prüffenster nur für den
  bestätigungspflichtigen PDF-/OCR-Import verwenden.
- Für alle drei Belegarten das Summenfeld einheitlich und kompakt aufbauen. Dort
  ausschließlich die Nettosumme gesamt, die jeweils anwendbare Umsatzsteuer und
  den finalen Gesamt- beziehungsweise Auszahlungsbetrag anzeigen.
- Im Summenfeld aller Belegarten in derselben Reihenfolge die Schaltflächen
  „PDF erstellen“, „XML erstellen“ und „Speichern“ anbieten. Fachliche Detailwerte
  der Getreideabrechnung weiterhin ausschließlich im Lieferungsbereich anzeigen.
- Im Menü „Datei“ nur die vorhandenen Importfunktionen für XML und PDF anbieten.
- Im Menü „Beleg“ die Aktionen „Speichern“, „Formular leeren“ und „Gespeicherten
  Beleg laden“ sowie „Neuer Beleg“ mit Auswahl zwischen Rechnung, Gutschrift und
  Getreideabrechnung bündeln.
- „Formular leeren“ und „Neuer Beleg“ auch im Getreide-Arbeitsbereich vollständig
  unterstützen. Vor dem Verwerfen ungespeicherter Änderungen eine Bestätigung
  verlangen.
- Das Menü „Stammdaten“ unverändert lassen und „Werkzeuge“ in „Hilfe“ umbenennen.
- Nach der Umstellung alte, deaktivierte oder doppelte Bedienelemente entfernen
  und den vollständigen Workflow für jede Belegart mit GUI-Regressionstests
  absichern.

### 7. Fachlicher End-to-End-Abnahmetest

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

- Vor jedem Überschreiben einer bereits vorhandenen Getreidegutschrift wird auch
  nach dem Laden desselben Belegs ausdrücklich nachgefragt.
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
- Manuell berechnete und aus einer PDF geprüfte Abrechnungen werden auf dasselbe
  strukturierte Getreidegutschrift-Modell abgebildet und bleiben mit Lieferungen,
  Analysewerten sowie Mengen-, Preis- und Betragsänderungen bearbeitbar.
- Der bisherige allgemeine Gutschrift-Exportweg ist automatisiert getestet; die
  verlustfreie Speicherung sowie der PDF-/XML-Export der strukturierten
  Getreidegutschrift folgen in P1.4 und P1.5.
