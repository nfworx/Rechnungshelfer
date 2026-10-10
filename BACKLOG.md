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
- Eine ExternInvoice-Sammel-Final-Gutschrift ist bereits der steuerliche Beleg. Sie wird als
  Quelle für dieselbe digitale Gutschrift verwendet und nicht als Anlage behandelt.
- Die ursprüngliche ExternInvoice-PDF wird ausschließlich gelesen, nicht verändert, kopiert,
  eingebettet oder durch den Rechnungshelfer dauerhaft gespeichert.
- Die aus einer ExternInvoice-PDF erzeugte XML- beziehungsweise PDF-Ausgabe stellt denselben
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

- P1.3 „Bestätigte Daten in eine editierbare Getreidegutschrift übernehmen“ sowie der
  ursprüngliche Kernumfang von P1.6 „Belegworkflow, Summenfeld und Menüführung
  vereinheitlichen“ sind umgesetzt. Später ergänzte Folgeaufgaben zu Datumsfeldern
  und gemeinsamer Belegliste bleiben offen. Als Nächstes die rollengerechte
  PDF-Fußzeile korrigieren; die einheitliche Detailanzeige finanzieller
  Prüfdifferenzen aus P1.2 und die visuelle PDF-Überarbeitung bleiben separat offen.

## P0 – Kritische Fehler und Datenrisiken

- [x] Unbeabsichtigtes Überschreiben von Geschäftspartnerstammdaten durch ältere Belege verhindern.
- [x] Beim PDF-Rückimport eingebettete Rechnungsdaten validieren und Widersprüche zu sichtbaren Belegdaten erkennen.

## P1 – Wichtige Funktionen in empfohlener Reihenfolge

### 1. ExternInvoice-Sammel-Final-Gutschrift erkennen

- [x] Eine vorhandene ExternInvoice-PDF als nicht vertrauenswürdige, unveränderte Importquelle
  einlesen und das Format „Sammel-Final-Gutschrift“ erkennen.
- [x] Vor der Verarbeitung Dateityp, Dateigröße und Lesbarkeit prüfen; die Quelldatei
  weder verändern noch kopieren oder dauerhaft im Rechnungshelfer speichern.
- [x] Vorhandene PDF-Textschichten nutzen und bei unzureichender Qualität kontrolliert
  auf OCR zurückgreifen.
- [x] Gutschriftnummer, Ausstellungsdatum, Lieferungen, Analysewerte, Mengen, Preise,
  Beträge, Steuersatz und Summen als Importentwurf erfassen.
- [x] Selbst erzeugte PDFs um einen validierten internen Belegtyp (`invoice`,
  `self_billed_invoice`, `grain_credit_note`) erweitern und den Import anhand dieses
  Merkmals in den passenden Arbeitsbereich leiten. Getreidegutschriften dabei mit
  ihren vollständigen strukturierten Daten einbetten und Widersprüche zwischen
  sichtbarem Inhalt, Exportdaten und Belegtyp blockieren.
- [ ] Bei fremden PDFs und eingescannten Belegen ohne eingebetteten Belegtyp im
  Importfenster den erkannten Typ nur als Vorschlag anzeigen und eine bewusste
  Auswahl zwischen Rechnung, Gutschrift und Getreideabrechnung ermöglichen. Nach
  einer geänderten Auswahl die fachlich passende Erkennung erneut ausführen. Eine
  Getreideabrechnung stets durch die strukturierte Prüfansicht leiten und die
  Übernahme sperren, wenn Lieferungen, Abrechnungswerte oder Pflichtangaben nicht
  ausreichend sicher rekonstruiert werden können. Die Anzahl der Lieferscheine darf
  weiterhin nur ein unterstützendes Merkmal sein.

### 2. Prüfpflichtigen Importentwurf anzeigen

- [x] Erkannte Werte zusammen mit Fundstelle, Quelltext und Erkennungssicherheit in
  einer Prüfansicht darstellen.
- [x] Für jede Lieferung den Lieferbetrag aus Abrechnungsmenge und Abrechnungspreis je
  Tonne sowie gegebenenfalls festen Betragsanpassungen berechnen. Anschließend die
  Nettosumme als Summe der Lieferbeträge, die Umsatzsteuer aus Nettosumme und
  Steuersatz, den Gesamtbetrag aus Netto und Steuer sowie den Auszahlungsbetrag
  unter Berücksichtigung der Abschlagszahlung prüfen.
- [ ] Abweichungen bei Lieferbetrag, Nettosumme, Umsatzsteuer, Gesamtbetrag oder
  Auszahlungsbetrag als blockierende Fehler mit Belegwert, Prüfwert und Differenz
  anzeigen. **Teilweise umgesetzt:** Abweichungen blockieren die Übernahme und der
  erwartete Wert wird genannt; die einheitliche Anzeige von Belegwert, Prüfwert und
  Differenz fehlt noch.
- [x] Wenn ein passendes Regelwerk eindeutig verfügbar ist, importierte Mengen- und
  Preisabzüge zusätzlich dagegen prüfen. Abweichungen in der OCR-Prüfansicht je
  Analysezeile beispielsweise als „Beleg: -28 kg / Regelwerk: -30 kg“ darstellen,
  aber nur als nicht blockierende Warnung behandeln.
- [x] Wenn kein passendes Regelwerk eindeutig verfügbar ist, auf die Regelprüfung
  verzichten und lediglich kenntlich machen, dass nur die finanziellen
  Zusammenhänge geprüft wurden.
- [x] Unsichere oder widersprüchliche Werte niemals automatisch übernehmen.
- [x] Manuelle Korrektur und ausdrückliche Bestätigung aller zu übernehmenden Daten
  ermöglichen.

### 3. Bestätigte Daten in eine editierbare Getreidegutschrift übernehmen

- [x] In der Prüfansicht eine ausdrückliche Schaltfläche „Als Getreidegutschrift
  übernehmen“ anbieten und nur einen vollständig geprüften Entwurf übernehmen.
- [x] Aus dem bestätigten Entwurf eine strukturierte Getreidegutschrift mit derselben
  Gutschriftnummer erzeugen; keinen zweiten steuerlichen Beleg anlegen und nicht
  in die allgemeine Gutschriftenmaske wechseln.
- [x] Importierte und manuell erstellte Getreidegutschriften auf dasselbe fachliche
  Dokumentmodell abbilden. Bei importierten Belegen die bestätigten Endwerte nicht
  durch ein Regelwerk überschreiben; eine mögliche Regelwerksberechnung nur als
  getrennten Vergleichswert verwenden.
- [x] Lieferungen, Analysewerte, Mengen- und Preisänderungen sowie bestätigte Beträge
  strukturiert und vollständig editierbar halten.
- [x] Herkunft des Belegs sowie erkannte Regelwerksabweichungen einschließlich der
  verwendeten Regelwerksversion strukturiert speichern, damit das Prüfverhalten
  und die Warnhinweise nach erneutem Laden nachvollziehbar bleiben. PDF-Datei,
  OCR-Rohtext und Erkennungsmetadaten weiterhin nicht dauerhaft speichern.
- [x] In der Hauptmaske bei einer bestätigten Regelwerksabweichung ausschließlich ein
  Ausrufezeichensymbol an der betroffenen Analysezeile anzeigen. Der Hoverhinweis
  erklärt knapp, dass die Abzugsberechnung vom beim Import geprüften Regelwerk
  abweicht; konkrete Vergleichswerte bleiben der OCR-Prüfansicht vorbehalten.
- [x] Abschlagszahlungen im strukturierten Beleg als eigenen Wert erhalten. PDF- und
  XML-Ausgabe erst freigeben, wenn der Betrag dort gemäß P1.5 konsistent
  dargestellt wird.
- [x] Den übernommenen Beleg im Getreideabrechnungs-Arbeitsbereich vollständig
  bearbeitbar machen; die Übernahme speichert ihn noch nicht automatisch.

### 4. Importierte Getreidegutschrift speichern und wieder öffnen

- [x] Ausschließlich die bestätigten strukturierten Belegdaten über die bestehenden
  Speicherwege sichern; die ursprüngliche ExternInvoice-PDF bleibt außerhalb der Anwendung.
- [x] Die Gutschrift nach einem Neustart vollständig und ohne Abhängigkeit von der
  ursprünglichen PDF wieder laden können.
- [x] Falls Schemaänderungen erforderlich werden, ausschließlich eine versionierte
  Migration mit Backup, Transaktion und verständlicher Fehleranzeige verwenden.
- [x] Speicherung, Neustart, erneutes Laden und Fehlerfälle mit einer temporären
  Datenbank testen.

### 5. Dieselbe Gutschrift als PDF oder XRechnung ausgeben

- [x] Aus den bestätigten strukturierten Daten wahlweise eine lesbare PDF oder eine
  XRechnung erzeugen; beide Ausgaben repräsentieren denselben Beleg.
- [x] Gutschriftnummer, Datum, Parteien, Positionen, Steuersatz und Summen in beiden
  Formaten konsistent halten.
- [x] Für die XRechnung den vorhandenen Gutschriftprozess mit Typcode `389` verwenden
  und die Ausgabe mit XSD und KoSIT validieren.
- [x] In der XRechnung jede Lieferung als eigene Position mit Abrechnungsmenge in
  Kilogramm, Abrechnungspreis je Tonne über die Preisbasis 1.000 Kilogramm und
  bestätigtem Lieferbetrag abbilden. Analysewerte,
  Ursprungsmenge, Basispreis sowie Mengen- und Preisänderungen als stabile
  Artikelmerkmale (BG-32/BT-160/BT-161) und zusätzlich lesbar ausgeben.
- [x] Abschlagszahlungen als bezahlten Betrag (BT-113 beziehungsweise
  `PrepaidAmount`) ausgeben und den Auszahlungsbetrag konsistent berechnen.
- [ ] Die PDF-Fußzeile rollengerecht erzeugen: Bei Rechnungen den Verkäufer
  beziehungsweise Belegsteller, bei Gutschriften und Getreidegutschriften den
  Käufer beziehungsweise Belegsteller anzeigen. Kontaktdaten sowie insbesondere
  IBAN und BIC aus dem fachlich richtigen Datensatz übernehmen und den Unterschied
  für alle drei Belegarten mit Regressionstests absichern.
- [x] PDF- und XML-Ausgabe bei finanziellen Inkonsistenzen sperren. Bestätigte
  Regelwerksabweichungen aus einem Import lediglich als Warnung behandeln und die
  Ausgabe dadurch nicht blockieren.
- [x] Die ursprüngliche ExternInvoice-PDF weder einbetten noch als Anlage referenzieren.

### 6. Belegworkflow, Summenfeld und Menüführung vereinheitlichen

- [x] Rechnung, Gutschrift und Getreideabrechnung trotz ihrer unterschiedlichen
  Fachmodelle nach demselben verständlichen Bedienmuster erstellen, bearbeiten,
  speichern, leeren und wieder öffnen können.
- [x] Eine manuell erstellte Getreideabrechnung beim Speichern validieren, intern als
  strukturierte Getreidegutschrift übernehmen und direkt in der Datenbank sichern;
  den zusätzlichen Bedienschritt „Getreidegutschrift erstellen“ dafür entfernen.
- [x] In der manuellen Eingabemaske Ursprungsmenge, Analysewerte und Basispreis als
  Eingaben behandeln und Abrechnungsmenge, Abrechnungspreis, Lieferbetrag und
  Gesamtsummen automatisch über das Regelwerk beziehungsweise die verbindliche
  Summenlogik berechnen.
- [x] Bei importierten Belegen bestätigte Abrechnungsmenge und Abrechnungspreis als
  Belegwerte verwenden. Lieferbetrag und Gesamtsummen weiterhin automatisch
  berechnen und gegen die importierten Referenzwerte prüfen; Regelwerksvergleiche
  verändern diese Werte nicht.
- [x] Gespeicherte Getreidegutschriften im Getreide-Arbeitsbereich laden und dort
  unmittelbar weiterbearbeiten. Das separate Prüffenster nur für den
  bestätigungspflichtigen PDF-/OCR-Import verwenden.
- [x] Für alle drei Belegarten das Summenfeld einheitlich und kompakt aufbauen. Dort
  ausschließlich die Nettosumme gesamt, die jeweils anwendbare Umsatzsteuer und
  den finalen Gesamt- beziehungsweise Auszahlungsbetrag anzeigen.
- [x] Im Summenfeld aller Belegarten in derselben Reihenfolge die Schaltflächen
  „PDF erstellen“, „XML erstellen“ und „Speichern“ anbieten. Fachliche Detailwerte
  der Getreideabrechnung weiterhin ausschließlich im Lieferungsbereich anzeigen.
- [x] Im Menü „Datei“ nur die vorhandenen Importfunktionen für XML und PDF anbieten.
- [x] Im Menü „Beleg“ die Aktionen „Speichern“, „Formular leeren“ und „Gespeicherten
  Beleg laden“ sowie „Neuer Beleg“ mit Auswahl zwischen Rechnung, Gutschrift und
  Getreideabrechnung bündeln.
- [x] „Formular leeren“ und „Neuer Beleg“ auch im Getreide-Arbeitsbereich vollständig
  unterstützen. Vor dem Verwerfen ungespeicherter Änderungen eine Bestätigung
  verlangen.
- [x] Das Menü „Stammdaten“ unverändert lassen und „Werkzeuge“ in „Hilfe“ umbenennen.
- [x] Nach der Umstellung alte, deaktivierte oder doppelte Bedienelemente entfernen
  und den vollständigen Workflow für jede Belegart mit GUI-Regressionstests
  absichern.
- [ ] Die weiterhin fehlerhaften Datumsfelder in allen drei Belegmasken systematisch
  prüfen und vereinheitlichen. Manuelle Eingabe, Datumsauswahl, Fokuswechsel,
  Validierung sowie Speichern und erneutes Laden müssen mit dem deutschen
  Datumsformat zuverlässig funktionieren und durch GUI-Regressionstests abgesichert
  werden.
- [ ] Beim Laden gespeicherter Belege unabhängig vom aktuell geöffneten Arbeitsbereich
  immer Rechnungen, Gutschriften und Getreidegutschriften in einer gemeinsamen Liste
  anzeigen. Den Belegtyp eindeutig kennzeichnen und den gewählten Beleg anschließend
  automatisch im passenden Arbeitsbereich öffnen; Filter dürfen die Gesamtliste nur
  optional einschränken.

### 7. Fachlicher End-to-End-Abnahmetest

- [ ] Eine reale ExternInvoice-Sammel-Final-Gutschrift mit mehreren Lieferungen und 7,8 Prozent
  Umsatzsteuer von der PDF-Auswahl bis zum bestätigten Beleg durchspielen.
- [ ] Unsichere OCR-Werte, rechnerische Gegenprüfung und manuelle Korrektur gezielt
  testen.
- [ ] Speichern, Neustart, erneutes Laden sowie PDF- und XRechnungsausgabe einschließlich
  KoSIT prüfen.
- [ ] Gemeinsam mit Hauptanwender und Steuerberater Bezeichnung, Steuersatz,
  Pflichtangaben und Darstellung einmal fachlich abnehmen.

## P2 – Technische Verbesserungen

- [ ] Das vorhandene `assets/Rechnungshelfer.ico` als Anwendungssymbol für die
  Windows-EXE sowie für Fenster-, Titelleisten- und Taskleistendarstellung
  einbinden und die Übernahme in den PyInstaller-Build prüfen.
- [ ] GitHub Actions für automatische Tests bei Pushes einrichten.
- [ ] Testdaten und Beispiellieferungen klar vom Produktivbetrieb trennen.
- [ ] Große GUI-Module bei Bedarf aufteilen und vereinfachen.
- [ ] Sichtbares Neuzeichnen beziehungsweise Flackern beim Aufbau und Aktualisieren
  der GUI systematisch beseitigen. Zuerst alle Masken und Dialoge mit vollständigem
  Widget-Neuaufbau erfassen; aktuell puffert `BufferedFormHost` nur die Rechnungs-
  und Gutschriftenmaske, während insbesondere die Getreideabrechnung Teilbereiche
  direkt leert und neu erzeugt. Pragmatisch lokale Änderungen bevorzugt durch
  Aktualisieren bestehender Widgets abbilden und den vorhandenen gepufferten
  Flächentausch nur für tatsächlich vollständige Maskenwechsel zu einer kleinen,
  wiederverwendbaren Lösung erweitern. Fokus, Scrollposition und Auswahlzustand
  müssen dabei erhalten bleiben. Die auffälligen Interaktionen je Maske manuell
  prüfen und zentrale Aktualisierungs- und Wechselpfade mit GUI-Regressionstests
  absichern; keine allgemeine GUI-Architekturänderung ohne nachgewiesenen Bedarf.
- [ ] Lieferungsübersicht der Getreideabrechnung kompakter darstellen: Die separaten
  Spalten „Δ Menge kg“ und „Δ Wert EUR“ entfernen und Mengenabzüge direkt in der
  Spalte „Menge kg“ sowie wertmäßige Abzüge direkt in der Spalte „Betrag EUR“
  anzeigen. Die bereits verwendete graue Darstellung der Abzugszeilen beibehalten
  und die Lesbarkeit für Basiswert, einzelne Abzüge und Ergebniswert prüfen.
- [ ] Die vollständige Testsuite systematisch auf fachliche Plausibilität,
  aktuellen Nutzen und tatsächliche Notwendigkeit jedes Tests prüfen. Dabei
  insbesondere widersprüchliche Erwartungen, gegeneinander arbeitende Tests,
  ungewollte Seiteneffekte sowie Abhängigkeiten von Ausführungsreihenfolge oder
  gemeinsamem Zustand erkennen und bereinigen. Tests nur nach nachvollziehbarer
  Prüfung entfernen oder grundlegend ändern.
- [ ] Wiederholte Test-Fixtures und Hilfsfunktionen zusammenführen, ohne fachlich
  unterschiedliche Tests zu verlieren; keine pauschale Testlöschung.
- [ ] Tesseract-Distribution verschlanken und Repository-Größe optimieren.
- [ ] Datenbank-Backup und Wiederherstellung praktisch testen.
- [ ] Die visuelle PDF-Darstellung aller Belegarten systematisch überarbeiten,
  insbesondere Abstände, Tabellenumbrüche, Ausrichtung, Summenbereich und Fußzeile.
  Fachliche Korrekturen an Rollen- und Zahlungsdaten unabhängig davon zuerst unter
  P1.5 umsetzen.

## Später – Weitere Importformate und lernende Regelvorschläge

- [ ] Nach dem fachlich abgenommenen ExternInvoice-Import bei Bedarf weitere PDF-Layouts und
  Abrechnungsprogramme als jeweils kontrollierte Importformate ergänzen.
- [ ] Nach mehreren bestätigten ExternInvoice-Abrechnungen Abweichungen zu den aktiven Regeln
  erkennen und neue oder geänderte Regeln lediglich vorschlagen.
- [ ] Regelvorschläge erklären, mit Beispieldaten testen und erst nach Freigabe als
  neue Regelwerksversion aktivieren; bestehende Abrechnungen bleiben unverändert.

## Erledigt

- [x] Vor jedem Überschreiben einer bereits vorhandenen Getreidegutschrift wird auch
  nach dem Laden desselben Belegs ausdrücklich nachgefragt.
- [x] Geschäftspartner besitzen stabile interne IDs und getrennte Kunden-/Lieferantenrollen;
  sichtbare Geschäftspartnernummern bleiben numerisch und editierbar.
- [x] Mehrere Lieferungen, Getreidearten, Analysewerte sowie konfigurierbare Mengen-,
  Preis- und Kostenregeln sind in der Getreideabrechnung vorhanden.
- [x] Regelwerke sind je Getreideart auswählbar und versionierbar; Braugerste, Hafer
  und Raps sind ergänzt, Triticale wurde entfernt.
- [x] Feldvalidierung, Datumsauswahl, Grenzfallunterdrückung für Null-Abzüge und die
  nachvollziehbare Tabellenaufschlüsselung sind umgesetzt.
- [x] Nettoabrechnungsbetrag, Umsatzsteuer und Auszahlungsbetrag werden getrennt
  berechnet und angezeigt.
- [x] Manuell berechnete und aus einer PDF geprüfte Abrechnungen werden auf dasselbe
  strukturierte Getreidegutschrift-Modell abgebildet und bleiben mit Lieferungen,
  Analysewerten sowie Mengen-, Preis- und Betragsänderungen bearbeitbar.
- [x] Strukturierte Getreidegutschriften werden verlustfrei gespeichert, nach einem
  Neustart wieder geladen und über eine getestete Projektion für PDF und XML
  bereitgestellt; beide Ausgaben sind in der Getreidemaske aktiv verfügbar.
- [x] Der zusätzliche Bedienschritt „Getreidegutschrift erstellen“ wurde entfernt;
  manuelle Abrechnungen werden beim Speichern direkt validiert und persistiert.
- [x] Gespeicherte Getreidegutschriften lassen sich im Getreide-Arbeitsbereich ohne
  dokumentweites Bearbeitungsfenster weiterbearbeiten.
- [x] Datepicker-Auswahlen aktualisieren neben dem sichtbaren Eingabefeld auch das
  zugrunde liegende Belegmodell.
