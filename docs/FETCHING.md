# Fetching exports from TimeEdit

Instead of exporting each programme year by hand, `schedcheck fetch` opens the
right export links in your browser, and `schedcheck collect` files the
downloads. TimeEdit's staff views need a KTH login; the tool never sees it:
the downloads happen in your own, logged-in browser.

## Setup (once)

Create a config in your workspace (not in this repo), e.g. `workspace/timeedit.toml`:

```toml
base  = "https://cloud.timeedit.net/kth/web/staff01/ri.xlsx"
views = { remiss = 9, final = 10 }        # preliminary / published schedule
objects = { CTFYS1 = "386379.16", CTFYS2 = "386225.16", CTFYS3 = "386092.16" }

# First day of term .. end of the August re-exam period.
[terms]
VT26 = ["2026-01-13", "2026-08-23"]
VT27 = ["2027-01-12", "2027-08-29"]
```

The object id of a programme year is the same in all views and terms. To find
it: export the year once by hand, then copy the download link (in Chrome:
`chrome://downloads`, right-click the link under the file name, *Copy link
address*) and read the `objects=` value. The keys (`CTFYS1`, …) must match the
programme line in the export header.

What the URL parameters mean, as far as we know (observed 2026-10):

| parameter | meaning |
|---|---|
| `sid` | view: `9` preliminary (remiss), `10` published schedule |
| `p` | date range, `YYYYMMDD.x,YYYYMMDD.x` |
| `objects` | the programme year |
| others (`ox`, `types`, `fe`, `mw`, `ps`, …) | layout options; kept as in TimeEdit's own links |

## Each review

```sh
# 1. Open the exports (log in to TimeEdit in the browser if asked)
python3 -m schedcheck fetch --config workspace/timeedit.toml \
    --new VT27:remiss --old VT26:final \
    --new-dir VT27/remiss --old-dir VT27/reference

# 2. When the downloads are done
python3 -m schedcheck collect --from ~/Downloads

# 3. Review
python3 -m schedcheck program --new VT27/remiss --old VT27/reference --out VT27/reports
```

`fetch --print-only` just prints the links. `collect` only looks at files
downloaded after the fetch, identifies each by the programme year and date
range in its header, renames it (`CTFYS1_VT27_remiss.xlsx`), reports files it
ignored, and exits with an error if a requested export is missing.

Each term can be requested once per fetch (files are told apart by their date
range). Keep the number of requests small; this uses a non-public KTH view.
