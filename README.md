# kth-schedule-review

Checks preliminary KTH schedules ("remiss") exported from TimeEdit, so programme
directors and teachers can give feedback faster and miss less.

It compares the schedule under review with

- the **study plan** of each cohort (from [ProgramVisualization](https://github.com/cohm/ProgramVisualization)),
- a **reference schedule**, typically last year's final schedule,

and reports:

| Check | What it finds |
|---|---|
| `coverage` | study-plan courses missing from the schedule (and scheduled courses not in the plan); courses without an ordinary exam or a re-exam |
| `structure` | per course: changed number of lectures/exercises/labs…, changed order, occasions moved ≥ 2 teaching weeks, changed exam modules |
| `exams` | exams of courses taken in parallel on the same or consecutive days; re-exam paths (year N students retaking year N−1 courses); elective pairs ranked by how likely students take both (master-eligibility groups from the study plan count as "both") |
| `teaching` | lectures, exercises, labs etc. of courses taken in parallel that overlap in time; graded by whether whole classes or single groups are affected and how likely students take both courses |
| `dataquality` | stale course-round codes, exports whose date range misses the August re-exams, existing remiss comments |

Outputs: a self-contained **HTML report**, **draft remiss comments** (Swedish or
English, Markdown) and **`issues.json`** for scripts and AI agents.
Nothing is ever sent anywhere; you edit and send the comments yourself.

Requires Python ≥ 3.11 and nothing else.

**Example:** the review of the CTFYS VT27 remiss —
[report](https://cohm.github.io/kth-schedule-review/docs/examples/CTFYS_VT27/CTFYS_VT27_review.html),
[draft comments](docs/examples/CTFYS_VT27/CTFYS_VT27_kommentarer.md), [about](docs/examples/README.md).

## Quick start

1. Export the schedules from TimeEdit as .xlsx, one file per programme year,
   for the term under review and for the reference term (see
   [docs/EXPORTING.md](docs/EXPORTING.md)), or let `schedcheck fetch` open the
   exports in your browser and `schedcheck collect` file them (see
   [docs/FETCHING.md](docs/FETCHING.md)). Put them in two folders, e.g.

   ```
   VT27/remiss/      TimeEdit_….xlsx  (CTFYS1, CTFYS2, CTFYS3)
   VT27/reference/   TimeEdit_….xlsx  (last year's final schedule)
   ```

2. Run a programme review:

   ```sh
   python3 -m schedcheck program --new VT27/remiss --old VT27/reference --out VT27/reports
   ```

   The programme and programme years are read from the export headers; study
   plans are downloaded from ProgramVisualization and cached in `~/.cache/schedcheck`.

3. Open `VT27/reports/<PROG>_<term>_review.html`, read
   `<PROG>_<term>_kommentarer.md`, and edit the comments before sending.

A teacher can review just their course(s), no study plan needed:

```sh
python3 -m schedcheck course SF1674 --new VT27/remiss --old VT27/reference --out reports/SF1674
```

`python3 -m schedcheck dump FOLDER [--course CODE …]` prints what the parser
understood, which is the first thing to look at when a result seems wrong.

## Severities

| | meaning |
|---|---|
| **error** | almost certainly needs fixing (missing mandatory course or exam, clashing mandatory exams) |
| **warning** | probably needs fixing or asking about |
| **review** | a difference from the reference schedule; may well be intended, a human should judge |
| **info** | context; hidden by default in the report |

## Accepting known differences

When a difference is confirmed as intended, record it so reruns stay quiet:

```toml
# workspace/accepted.toml (not committed)
[[accepted]]
check = "structure.counts"
course = "DD1327"
note = "New workshop format, confirmed with examiner 2026-10-20"
```

```sh
python3 -m schedcheck program … --accepted workspace/accepted.toml
```

`key` (from `issues.json`) can be added to accept one specific instance only.

## Programme-specific settings

Optional `programs/<PROG>.toml` files hold shared, programme-level knowledge:
threshold overrides and extra master-eligibility groups. See
[programs/EXAMPLE.toml](programs/EXAMPLE.toml). Most programmes need none.

## Using it with an AI agent

[`skills/schedule-remiss-review/SKILL.md`](skills/schedule-remiss-review/SKILL.md)
is a Claude Code skill that runs the tool, triages the findings and polishes the
comment draft. [docs/PROCESS.md](docs/PROCESS.md) is the domain description it
relies on and is also a good read for humans new to the remiss process.

To install the skill in a project: `ln -s /path/to/kth-schedule-review/skills/schedule-remiss-review .claude/skills/`

## Limitations

- Only programmes (and cohorts) that ProgramVisualization covers get study-plan
  checks; others still get structure, exam and data-quality checks.
- Term structure (exam and re-exam windows) is derived from the "Examinationsdag"
  and "Omexamination" marker rows in the exports. Exports without them give
  weaker results.
- "Same subject" for electives is guessed from the course-code prefix (SF, SI, …).

## Development

```sh
python3 -m unittest discover -s tests -t .
```

Tests use synthetic exports generated in code; never add real exports to the
repo. Curated example outputs live in `docs/examples/`, checked for personal
data before they are added. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/ADDING_A_CHECK.md](docs/ADDING_A_CHECK.md).
