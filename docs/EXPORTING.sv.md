# Exportera scheman ur TimeEdit

**Svenska** · [English](EXPORTING.md)

(Ett skriptat alternativ finns i [FETCHING.sv.md](FETCHING.sv.md).)

Verktyget läser TimeEdits **Excel-export (.xlsx)** av en schemavy.

Det här måste exporten innehålla:

- **En fil per årskurs** (t.ex. CTFYS1, CTFYS2, CTFYS3), eller någon annan
  uppdelning; verktyget läser program och årskurs från raden under rubriken
  (`CTFYS2, Civilingenjörsutbildning i teknisk fysik`). Filnamnen spelar ingen roll.
- **Hela terminen inklusive omtentaperioden i augusti.** För en vårtermin ska
  datumintervallet gå till slutet av augusti (t.ex. 2027-01-12 – 2027-08-29).
  Annars saknas omtentorna för P4-kurser och verktyget varnar.
- Kalenderns **markeringsrader** ("Examinationsdag", "Omexamination",
  helgdagar). De finns med i programvyerna som standard.
- Samma upplägg för referensterminen (t.ex. förra årets slutliga schema).

Lägg filerna för en termin i en mapp; Excels låsfiler (`~$…xlsx`) ignoreras.

## Integritet

Exporterna innehåller lärares namn, lokaler och kommentarer. Håll dem utanför
versionshantering (repots `.gitignore` utesluter `*.xlsx`). Rapporterna
innehåller inga namn på personal, men de citerar kolumnen för
remisskommentarer; kontrollera innehållet innan du delar dem öppet.

## Exporttid

Remissen kan ändras medan den är ute på remiss, så rapporten anger när varje
schema exporterades. TimeEdit skriver tiden i filens metadata
(`docProps/core.xml`, "created"); för filer utan den används tiden i
TimeEdits standardfilnamn (`TimeEdit_2026-10-14_20_03.xlsx`) eller, i sista
hand, filens ändringsdatum (markerat "filens datum"). Exportera alla
årskurser i en granskning samtidigt; om de togs med mer än en timmes
mellanrum noterar granskningen det (`dataquality.export-times`).
