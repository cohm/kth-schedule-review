# Hämta exporter från TimeEdit

**Svenska** · [English](FETCHING.md)

I stället för att exportera varje årskurs för hand öppnar `schedcheck fetch`
rätt exportlänkar i din standardwebbläsare (eller den du anger med
`--browser`, t.ex. `--browser Safari`), och `schedcheck collect` arkiverar
nedladdningarna. TimeEdits personalvyer kräver KTH-inloggning; verktyget ser
den aldrig: nedladdningarna sker i din egen, inloggade webbläsare.

## Förberedelse (en gång)

Skapa en konfiguration i din arbetsmapp (inte i detta repo), t.ex. `workspace/timeedit.toml`:

```toml
base  = "https://cloud.timeedit.net/kth/web/staff01/ri.xlsx"
views = { remiss = 9, final = 10 }        # preliminärt / publicerat schema
objects = { CTFYS1 = "386379.16", CTFYS2 = "386225.16", CTFYS3 = "386092.16" }

# Terminens första dag .. slutet av omtentaperioden i augusti.
[terms]
VT26 = ["2026-01-13", "2026-08-23"]
VT27 = ["2027-01-12", "2027-08-29"]
```

En årskurs objekt-id är detsamma i alla vyer och terminer. Så hittar du det:
exportera årskursen en gång för hand och kopiera sedan nedladdningslänken
(Chrome: `chrome://downloads`, högerklicka på länken under filnamnet, *Kopiera
länkadress*; Safari: öppna nedladdningslistan med ⌥⌘L, högerklicka på filen,
*Kopiera adress*) och läs av värdet för `objects=`. Nycklarna (`CTFYS1`, …)
måste stämma med programraden i exportens huvud.

Vad URL-parametrarna betyder, så långt vi vet (observerat 2026-10):

| parameter | betydelse |
|---|---|
| `sid` | vy: `9` preliminärt (remiss), `10` publicerat schema |
| `p` | datumintervall, `ÅÅÅÅMMDD.x,ÅÅÅÅMMDD.x` |
| `objects` | årskursen |
| övriga (`ox`, `types`, `fe`, `mw`, `ps`, …) | layoutval; behålls som i TimeEdits egna länkar |

## Varje granskning

```sh
# 1. Öppna exporterna i standardwebbläsaren (logga in i TimeEdit där om du ombeds)
python3 -m schedcheck fetch --config workspace/timeedit.toml \
    --new VT27:remiss --old VT26:final \
    --new-dir VT27/remiss --old-dir VT27/reference

# 2. När nedladdningarna är klara
python3 -m schedcheck collect --from ~/Downloads

# 3. Granska
python3 -m schedcheck program --new VT27/remiss --old VT27/reference --out VT27/reports
```

Utan `--programs` hämtas alla årskurser i konfigurationen; ange t.ex.
`--programs CTFYS` (alla dess årskurser) eller `--programs CTMAT2`.
`fetch --print-only` skriver bara ut länkarna. `collect` tittar bara på filer
som laddats ned efter `fetch`, identifierar varje fil på årskurs och
datumintervall i dess huvud, döper om den (`CTFYS1_VT27_remiss.xlsx`), visar
vilka filer den ignorerade och avslutar med ett fel om en begärd export saknas.

Varje termin kan begäras en gång per hämtning (filerna skiljs åt på
datumintervallet). Håll nere antalet förfrågningar; detta använder en
KTH-vy som inte är publik.

## Länkar till schemana i rapporten

Med samma konfiguration länkar granskningen varje årskurs till dess schema i
TimeEdit (rapportens huvud, panelerna per årskurs, kommentarsutkasten,
`issues.json`):

```sh
python3 -m schedcheck program --new VT27/remiss --old VT27/reference --out VT27/reports \
    --timeedit workspace/timeedit.toml
```

Vyn (remiss/final) tas från filnamnen som `collect` ger
(`CTFYS1_VT27_remiss.xlsx`); för andra filnamn, ange `--new-view remiss
--old-view final`. Datumintervallet är det i respektive exports huvud.

TimeEdits schemasidor har adresser som `…/staff01/ri<omkastad>.html`: samma
fråga som en exportlänk, omskriven med TimeEdits egen reversibla
förvrängning (`schedcheck.io.fetch.te_scramble` / `te_unscramble`; testerna
använder länkar kopierade från TimeEdit). Länkarna kräver KTH-inloggning,
precis som exporterna.
