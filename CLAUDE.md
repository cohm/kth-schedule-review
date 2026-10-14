# kth-schedule-review — notes for agents

Checks KTH TimeEdit schedule exports (remiss) against study plans and a reference
schedule. Domain rules: `docs/PROCESS.md` (read it before changing checks or
judging findings). Usage: `README.md`. Extending: `docs/ADDING_A_CHECK.md`.

## Layout

- `schedcheck/io/` readers (TimeEdit xlsx, ProgramVisualization study plans) → `model.py`
- `schedcheck/calendar.py` term calendar from marker rows; `term.py` TermData + exam classification
- `schedcheck/checks/` coverage, structure, exams, dataquality (registry in `__init__.py`)
- `schedcheck/reviews/` program and course reviews; `report/` html, comments (sv/en), json
- `skills/schedule-remiss-review/` the user-facing agent skill
- `tests/` unittest with synthetic exports (`tests/helpers.py`)

## Rules

- Stdlib only, Python ≥ 3.11. Run `python3 -m unittest discover -s tests -t .`.
- No programme-specific logic in code; programme knowledge goes in `programs/<PROG>.toml`
  or comes from the study-plan data.
- Never commit real exports or generated reports (names, comments). `.gitignore` covers them.
- Keep `docs/PROCESS.md` in sync when judgement rules change.
- Issue `key`s must stay stable across runs (accept lists depend on them).
