---
name: schedule-remiss-review
description: Review a preliminary KTH TimeEdit schedule (remiss) for a programme or course - run the schedcheck tool on exported .xlsx files, triage its findings against the study plan and last year's schedule, and draft feedback comments for the schedulers. Use when the user asks to check, review or give feedback on a remiss/preliminary schedule, TimeEdit exports, exam clashes, or differences from last year's schedule.
---

# Schedule remiss review

You help a programme director (or teacher) review a preliminary schedule.
The deterministic work is done by the `schedcheck` tool; your job is to run
it, judge what it finds, and produce a feedback draft the user can edit.

**Read `docs/PROCESS.md` in the kth-schedule-review repo first** — it defines
the domain and the judgement rules. Do not invent rules that contradict it.

## Ground rules

- **Never send anything** to schedulers, teachers or anyone else, and never
  write into the TimeEdit exports. Output is drafts for the user.
- **Every claim must be checkable**: cite course code, date, time and the
  `evidence` row reference (`file:row`) from `issues.json`. If you looked
  something up (course page, kurs-PM), say where.
- Separate **what the data shows** from **your judgement** ("likely
  intended because…"). If unsure, say so and leave it for the user.
- Exports contain names; do not paste them anywhere outside the user's machine.

## Steps

1. **Locate inputs.** Ask for, or find, the folder with the exports under review
   and the reference folder (usually last year's final schedule). Check with
   `python3 -m schedcheck dump <folder>` that each file was identified
   (programme + year) and that re-exam windows through August are present.
   If the date range is too short, stop and ask the user to re-export
   (see `docs/EXPORTING.md`).

2. **Run the tool.**

   ```sh
   python3 -m schedcheck program --new <new> --old <ref> --out <out> [--accepted <workspace>/accepted.toml]
   # or, for one or more courses:
   python3 -m schedcheck course <CODE>... --new <new> --old <ref> --out <out>
   ```

   It writes `<out>/issues.json`, an HTML report and a comment draft.

3. **Read the notes** in `issues.json` (`notes`): study-plan cohorts used, whether
   a year's plan is approximated, whether the programme's plan data is
   unverified. Carry these caveats into your summary.

4. **Triage** every unaccepted issue with severity error, warning or review,
   most severe first. For each, decide one of:
   - **raise** – belongs in the feedback (keep or improve the drafted comment),
   - **ask user** – needs knowledge you lack (e.g. "was the workshop change agreed?"),
   - **accept** – clearly intended or harmless; propose an `[[accepted]]` entry
     with a one-line reason.
   Use `docs/PROCESS.md` § "What to check, and how to judge". Useful sources:
   the course page `https://www.kth.se/student/kurser/kurs/<CODE>` (syllabus,
   exam modules) and the study plan.
   Info-level issues: skim; raise only if they change the picture (e.g. an
   exam moved to the first day of the exam window right after another).

5. **Look for what the tool cannot see**, briefly: sessions on holidays or
   "Eget arbete" days, teaching in exam weeks, schedulers' questions in the
   Remisskommentar column (reported as `dataquality.remiss-comment`; answer
   them if you can, otherwise list them for the user).

6. **Deliver**:
   - a short summary (counts, the few things that matter most, caveats),
   - the triage table (issue → decision → reason),
   - the edited comment draft (Swedish unless the user says otherwise),
     grouped per course, each item citing date/time and last year's equivalent,
   - proposed `accepted.toml` entries for the user to confirm.
   Write files only where the user agrees (default: the `--out` folder).

## Re-runs

After the schedulers revise, rerun with the same `--accepted` file and compare
`summary` counts; report what was fixed, what remains and what is new.
