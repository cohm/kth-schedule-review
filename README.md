# kth-schedule-review

**Svenska** · [English](README.en.md)

Granskar preliminära KTH-scheman (remiss) exporterade ur TimeEdit, så att
programansvariga och lärare kan ge återkoppling snabbare och missa mindre.

Schemat som granskas jämförs med

- **utbildningsplanen** för varje kull (från [ProgramVisualization](https://github.com/cohm/ProgramVisualization)),
- ett **referensschema**, normalt förra årets slutliga schema,

och verktyget rapporterar:

| Kontroll | Vad den hittar |
|---|---|
| `coverage` | kurser i utbildningsplanen som saknas i schemat (och schemalagda kurser som inte finns i planen); kurser utan ordinarie tentamen eller omtentamen, när utbildningsplanen, förra årets schema eller kursplanen säger att det ska finnas en |
| `structure` | per kurs: ändrat antal föreläsningar/övningar/laborationer…, ändrad ordning, tillfällen flyttade ≥ 2 undervisningsveckor, ändrade examinationsmoduler |
| `exams` | tentamina i kurser som läses parallellt samma dag eller dagar i rad; omtentavägar (studenter i årskurs N som tenterar om kurser från årskurs N−1); par av valbara kurser rangordnade efter hur troligt det är att studenter läser båda (behörighetsgrupper för masterprogram i utbildningsplanen räknas som "båda") |
| `teaching` | föreläsningar, övningar, laborationer m.m. i kurser som läses parallellt och krockar i tid; graderat efter om hela klassen eller enskilda grupper berörs och hur troligt det är att studenter läser båda kurserna |
| `syllabus` | schemalagda examinationsmoduler mot den gällande kursplanen från kursens sida på kth.se (t.ex. TEN1 schemalagd fast kursplanen har bytt till TEN2); kursplanen räknas också som belägg för att en tentamen saknas |
| `rooms` | per kurs och tillfälle, platserna i de bokade lokalerna jämfört med förra året (från [KTH Places](https://www.kth.se/places)): ≥ 10 / 20 / 40 % färre platser, ≥ 50 % fler, tillfällen utan bokad lokal |
| `dataquality` | gamla kurstillfälleskoder, exporter vars datumintervall missar omtentorna i augusti, befintliga remisskommentarer |

Resultat: en fristående **HTML-rapport** (svenska och engelska, går att
växla), **utkast till remisskommentarer** (Markdown och HTML, svenska eller
engelska) och **`issues.json`** för skript och AI-agenter. Inget skickas
någonstans; du redigerar och skickar kommentarerna själv.

Kräver Python ≥ 3.11 och inget annat.

**Exempel:** granskningen av remissen för CTFYS VT27 —
[rapport](https://cohm.github.io/kth-schedule-review/docs/examples/CTFYS_VT27/CTFYS_VT27_review.html),
[kommentarsutkast](docs/examples/CTFYS_VT27/CTFYS_VT27_kommentarer.md), [om exemplen](docs/examples/README.md).

## Kom igång

1. Exportera schemana ur TimeEdit som .xlsx, en fil per årskurs, för terminen
   som granskas och för referensterminen (se [docs/EXPORTING.sv.md](docs/EXPORTING.sv.md)),
   eller låt `schedcheck fetch` öppna exporterna i din (inloggade) webbläsare
   och `schedcheck collect` arkivera dem (se [docs/FETCHING.sv.md](docs/FETCHING.sv.md)).
   Lägg dem i två mappar, t.ex.

   ```
   VT27/remiss/      TimeEdit_….xlsx  (CTFYS1, CTFYS2, CTFYS3)
   VT27/reference/   TimeEdit_….xlsx  (förra årets slutliga schema)
   ```

2. Kör en programgranskning:

   ```sh
   python3 -m schedcheck program --new VT27/remiss --old VT27/reference --out VT27/reports
   ```

   Program och årskurser läses från exporternas huvud; utbildningsplanerna
   hämtas från ProgramVisualization och examinationsmodulerna från kursernas
   sidor på kth.se (bara moduler och kurstillfällenas datum sparas), med
   cache i `~/.cache/schedcheck`. `--no-syllabus` hoppar över kurssidorna.
   Lokalernas antal platser kommer från KTH Places (första körningen läser
   ~115 byggnadssidor och en sida per använd lokal, några minuter; sedan
   cache i 30 dagar); `--no-rooms` hoppar över detta, och `--rooms FIL`
   lägger till antal platser som saknas i Places:

   ```toml
   [capacity]
   "012:024" = 16        # lokalens namn som i exporten
   "Wenström" = 24
   ```

   Med `--timeedit workspace/timeedit.toml` (konfigurationen för `fetch`)
   länkar rapporten dessutom varje årskurs till dess schema i TimeEdit.

3. Öppna `VT27/reports/<PROG>_<termin>_review.html`, läs
   `<PROG>_<termin>_kommentarer.md` och redigera kommentarerna innan du skickar dem.

En lärare kan granska bara sina egna kurser, utan utbildningsplan:

```sh
python3 -m schedcheck course SF1674 --new VT27/remiss --old VT27/reference --out reports/SF1674
```

`python3 -m schedcheck dump MAPP [--course KOD …]` skriver ut vad tolkningen
förstod, det första att titta på när ett resultat verkar fel.

## Språk

Svenska är standard. `--lang en` (eller `SCHEDCHECK_LANG=en`) byter språk för
kommandots meddelanden och hjälptexter, kommentarsutkasten (`*_comments.md` i
stället för `*_kommentarer.md`) och språket rapporten öppnas i; rapporten
innehåller alltid båda och har en knapp för att växla. `issues.json` har
varje text på båda språken. Termerna följer [docs/GLOSSARY.md](docs/GLOSSARY.md).

## Allvarlighetsgrader

| | betydelse |
|---|---|
| **fel** | behöver nästan säkert rättas (saknad obligatorisk kurs eller tentamen, obligatoriska tentamina som krockar) |
| **varning** | behöver troligen rättas eller frågas om |
| **granska** | en skillnad mot referensschemat; kan mycket väl vara avsiktlig, en människa bör bedöma |
| **info** | sammanhang; dolt som standard i rapporten |

## Acceptera kända skillnader

När en skillnad är bekräftad som avsiktlig, anteckna det så att nya körningar
inte tar upp den igen:

```toml
# workspace/accepted.toml (checkas inte in)
[[accepted]]
check = "structure.counts"
course = "DD1327"
note = "Nytt workshopupplägg, bekräftat med examinator 2026-10-20"
```

```sh
python3 -m schedcheck program … --accepted workspace/accepted.toml
```

`key` (från `issues.json`) kan läggas till för att bara acceptera ett visst fall.

## Programspecifika inställningar

Valfria filer `programs/<PROG>.toml` innehåller gemensam kunskap på
programnivå: andra tröskelvärden och extra behörighetsgrupper för
masterprogram. Se [programs/EXAMPLE.toml](programs/EXAMPLE.toml). De flesta
program behöver ingen.

## Med en AI-agent

[`skills/schedule-remiss-review/SKILL.md`](skills/schedule-remiss-review/SKILL.md)
är en Claude Code-skill som kör verktyget, sorterar fynden och putsar
kommentarsutkastet. [docs/PROCESS.md](docs/PROCESS.md) (på engelska)
beskriver remissprocessen som den bygger på och är också läsvärd för den som
är ny i remissarbetet.

Installera skillen i ett projekt: `ln -s /sökväg/till/kth-schedule-review/skills/schedule-remiss-review .claude/skills/`

## Begränsningar

- Bara program (och kullar) som finns i ProgramVisualization får kontroller
  mot utbildningsplanen; andra får ändå kontroller av struktur, tentamina och
  datakvalitet.
- Terminens struktur (tentamens- och omtentaperioder) härleds från
  markeringsraderna "Examinationsdag" och "Omexamination" i exporterna.
  Exporter utan dem ger svagare resultat.
- "Samma ämne" för valbara kurser gissas från kurskodens prefix (SF, SI, …).

## Utveckling

Utvecklardokumentationen är på engelska: [README.en.md](README.en.md#development),
[CONTRIBUTING.md](CONTRIBUTING.md), [docs/ADDING_A_CHECK.md](docs/ADDING_A_CHECK.md).

```sh
python3 -m unittest discover -s tests -t .
```
