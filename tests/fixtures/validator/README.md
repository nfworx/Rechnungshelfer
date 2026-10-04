# Validator-Testbelege

Die beiden XML-Dateien sind ausschliesslich synthetische Testdaten. Namen,
Adressen, Steuerdaten und Kontoverbindungen sind nicht fuer echte Belege
bestimmt.

Sie decken Rechnung (InvoiceTypeCode 380), Gutschrift/Self-Billing
(InvoiceTypeCode 389), getrennte und identische Lieferadresse, mehrere
Einheiten, Positionsrabatte sowie 19 %, 7 %, 7,8 % und 0 % Umsatzsteuer ab.

Neu erzeugen:

```powershell
.\.venv\Scripts\python.exe -m tests.generate_validator_fixtures
```

Fehlerszenarien werden nicht als viele redundante XML-Dateien abgelegt. Sie
werden in `tests/test_validation_matrix.py` jeweils aus einer gueltigen Kopie
erzeugt, gezielt veraendert und gegen die erwartete Validatorreaktion geprueft.
