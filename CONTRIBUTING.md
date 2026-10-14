# Contributing

Contributions from programme directors, teachers and schedulers are welcome.

- **Never commit real schedule exports** (they contain staff names) or ad-hoc
  reports. Tests use synthetic exports built in `tests/helpers.py`.
  Deliberately chosen example outputs may go in `docs/examples/` once checked:
  no staff names, no local paths, and the programme director agrees.
- **Adding a programme** usually needs no code: if ProgramVisualization has
  its study plans, it works. Programme-level knowledge (threshold overrides,
  extra eligibility groups) goes in `programs/<PROG>.toml`; see `EXAMPLE.toml`.
- **Adding a check:** see [docs/ADDING_A_CHECK.md](docs/ADDING_A_CHECK.md).
- **Changing judgement rules** (what is an error vs. a warning): update
  [docs/PROCESS.md](docs/PROCESS.md) in the same change so humans and agents
  keep reading the same rules.
- Keep the tool stdlib-only so it runs anywhere with Python ≥ 3.11.
- Run `python3 -m unittest discover -s tests -t .` before submitting.
