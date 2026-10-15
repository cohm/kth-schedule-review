# Exporting schedules from TimeEdit

[Svenska](EXPORTING.sv.md) · **English**

(For a scripted alternative, see [FETCHING.md](FETCHING.md).)

The tool reads TimeEdit's **Excel (.xlsx) export** of a schedule view.

What the export must contain:

- **One file per programme year** (e.g. CTFYS1, CTFYS2, CTFYS3), or any other
  split; the tool reads the programme and year from the line under the title
  (`CTFYS2, Civilingenjörsutbildning i teknisk fysik`). File names do not matter.
- **The full term including the August re-exam period.** For a spring term, set
  the date range to run until the end of August (e.g. 2027-01-12 – 2027-08-29).
  Otherwise re-exams of P4 courses are missing and the tool will warn.
- The calendar **marker rows** ("Examinationsdag", "Omexamination", holidays).
  They are part of the programme views by default.
- The same layout for the reference term (e.g. last year's final schedule).

Put the files for one term in one folder; Excel lock files (`~$…xlsx`) are ignored.

<!-- TODO(maintainer): add the click path in TimeEdit for selecting a programme
     view, setting the date range and exporting to Excel, with a screenshot. -->

## Privacy

Exports contain teachers' names, rooms and comments. Keep them out of version
control (the repo's `.gitignore` excludes `*.xlsx`). The reports do not
include staff names, but they do quote the remiss-comment column; check
their content before sharing them publicly.

## Export time

The remiss can change while it is out for review, so the report states when
each schedule was exported. TimeEdit writes the time into the file's
metadata (`docProps/core.xml`, "created"); for files without it, the time in
TimeEdit's default file name (`TimeEdit_2026-10-14_20_03.xlsx`) or, last,
the file's modification date is used (marked "file date"). Export all
programme years of a review together; if they were taken more than an hour
apart, the review notes it (`dataquality.export-times`).

