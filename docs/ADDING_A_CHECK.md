# Adding a check

Checks live in `schedcheck/checks/`. A check is a function that receives a
`Context` and returns a list of `Issue`s:

```python
from ..i18n import T
from ..model import Issue
from . import Context, register

@register("walking", ("program", "course"), "Lectures in buildings far apart, back to back")
def check_walking(ctx: Context) -> list[Issue]:
    issues = []
    for e in ctx.new.events:
        if not any(ctx.wants(c) for c in e.codes):
            continue
        ...
        issues.append(Issue(
            "warning", "walking.far-apart", scope, course,
            T(f"{course}: {a} och {b} ligger direkt efter varandra i olika campus.",
              f"{course}: {a} and {b} are back to back on different campuses."),
            ask=T("Går det att flytta det ena?", "Could one of them be moved?"),
            key="stable-id", evidence=[e.cite()], details={...}))
    return issues
```

Then import the module in `run_checks()` in `schedcheck/checks/__init__.py`.

What `Context` provides:

| field | content |
|---|---|
| `review` | `"program"` or `"course"`; `applies_to` decides which reviews run the check |
| `new`, `old` | `TermData`: in-term events (de-duplicated), `year_events[(prog, year)]`, `calendar` (periods, exam and re-exam windows, teaching weeks), `exams()` |
| `plans` | per `(prog, year)`: `YearPlan` with the cohort's `StudyPlan` (may be `None`) |
| `config` | thresholds, eligibility-group overrides, accept list |
| `courses` / `wants(code)` | the course filter of a course review |

Conventions:

- **Severity**: `error` (almost certainly wrong), `warning` (probably wrong or
  should be asked about), `review` (a difference a human should judge),
  `info` (context).
- **`check`** is `"<module>.<what>"`; **`key`** must be stable between runs for
  the same finding, so accept lists keep working.
- **`evidence`**: `Event.cite()` strings, so every finding can be checked in the
  source export.
- **Text in both languages.** `message` is `T(sv=..., en=...)` (see
  `schedcheck/i18n.py`); `Issue` refuses a text missing either language.
  Build both from the same data, next to each other, so they cannot drift.
  `ask` (optional, also `T`) is the question the comment draft appends, e.g.
  "Ska den läggas in?". Use the terms in [GLOSSARY.md](GLOSSARY.md); helpers in
  `i18n` format weekdays (`when`, `weekday`) and lists (`join`).
- **`details`**: structured, language-neutral data for reports and agents.
- No programme-specific logic in code. Put programme knowledge in
  `programs/<PROG>.toml` and read it through `Config`.
- Add a test in `tests/` using the synthetic export helpers in `tests/helpers.py`.

## Adding a review type

A review (see `schedcheck/reviews/`) builds a `Context` and runs the registered
checks whose `applies_to` contains its name; add a CLI subcommand in
`schedcheck/__main__.py`.
