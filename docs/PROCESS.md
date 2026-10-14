# The schedule remiss process (domain description)

This document explains what a schedule review at KTH is about, for humans new
to it and for AI agents assisting with it. It is the knowledge the checks are
built on and the basis for judging what they find.

## The cycle

1. KTH's schedulers build next term's schedule in **TimeEdit**.
2. They send a **preliminary schedule ("remiss")** to programme directors
   (programansvariga, PA) and teachers for feedback, with a deadline.
3. Reviewers export the schedule from TimeEdit (one export per programme year),
   check it, and send comments. Comments can be written in a "Remisskommentar"
   column; schedulers sometimes leave their own questions there too.
4. The schedulers revise; the **final schedule (slutligt schema)** is published.

To first order a new schedule should look like last year's: same courses, same
number and order of lectures (Föreläsning), exercises (Övning), labs
(Laboration/Datorlaboration), seminars etc., exams in similar positions.
Differences are not necessarily wrong (courses get redesigned, calendars shift),
but each should be noticed and, if not obviously intended, asked about.

## Calendar vocabulary

- **Terms:** HT (autumn, periods P1 + P2) and VT (spring, P3 + P4). "VT27" is
  spring 2027, academic year 2026/27.
- Each period ends with an **exam window** (tentamensperiod), marked in exports
  by "Examinationsdag" rows.
- **Re-exam windows** (omtentaperiod, "Omexamination" rows): in VT typically the
  week after Easter (re-exams of HT courses), early June (re-exams of P3
  courses) and mid/late August (re-exams of P4 courses and others). The
  August window belongs to the spring term's schedule; an export whose date
  range stops at the end of May misses it.
- Easter moves between years, so calendar dates and ISO week numbers do not
  line up year to year. The tool compares **teaching weeks within a period**,
  skipping a re-exam week that falls inside the teaching period.
- Holidays and "Eget arbete" (self-study days) appear as marker rows too.

## Programmes, cohorts and study plans

- A programme (e.g. CTFYS, Engineering Physics) has a **study plan per cohort**
  (intake year). In VT27, year 1 is the HT2026 cohort, year 2 HT2025, year 3
  HT2024. Study plans can change between cohorts, so a course can legitimately
  move from year 2 to year 3.
- The official plans are at <https://www.kth.se/student/kurser/kurser-inom-program>.
  The tool reads them via ProgramVisualization, which extracts them to JSON
  and records how reliable each year is (exact or approximated from another
  cohort) and whether the programme's data has been verified by its director.
- Course categories: **mandatory** (obligatorisk), **conditionally elective**
  (villkorligt valfri; often "pick one of these", e.g. the degree project),
  **recommended** electives (rekommenderade valfria). An elective slot
  ("Valfri kurs, årskurs 3 våren") lists recommended courses; students pick
  courses worth the slot's credits, and may pick others.
- **Master-eligibility:** some electives are required for admission to specific
  master programmes (in the data as `qualifiesFor`, `required: true`). Students
  aiming for that master take all of them, so their exams must not clash.

## Reading an export

One row per scheduled activity. Columns that matter:

| column | content |
|---|---|
| Startdatum/Starttid/Sluttid | when |
| Aktivitet | activity type: Föreläsning, Övning, Laboration, Seminarium, Tentamen, Omtenta, Kontrollskrivning (KS, mid-term test), Examination, … |
| Grupp(er) | "SF1674 Helklass" = whole class; "DD1327 grupp A-D" = a sub-group (parallel sessions) |
| Tillfälleskod/kurskod | course code, possibly with round: "SF1674-12368 (VT27)"; several codes when courses share the activity |
| Program/grupp | which programme years attend, e.g. "CTMAT2-3", "CLGYM3-MAFY" (specialisation) |
| Examinationsmodul | exam module, e.g. "Tentamen. TEN1" |
| Remisskommentar | comments (only in remiss exports) |

Column names differ slightly between export versions; the tool normalises them.

## What to check, and how to judge

### 1. Coverage

Every course the study plan gives credits for this term must appear, with
teaching (not only a re-exam). A missing **mandatory** course is almost
certainly an error. A missing recommended elective may mean the course is not
given this year; worth asking. For a "pick one" group (degree projects), one
option being scheduled is enough.

Every course with an exam should have an **ordinary exam** in its period's
exam window and a **re-exam** in a later re-exam window. "Examination" rows
during the teaching period (oral exams, presentations) are partial exams.

### 2. Structure versus last year

For each course compare occasions. Judging differences:

- The tool separates four kinds of change per course: sessions **moved**
  between weeks (same activities, other week), **reordered within** a week,
  **added** and **removed**. Only when the sequence of activities itself
  differs is it called an order change; occasions that keep their sequence but
  shift by a week are info.
- Same activities, small reorder within a week: usually fine, but an exercise
  session placed *before* the lecture it builds on is worth flagging.
- Fewer exercise sessions, labs or seminars: ask; it can be a resource cut
  nobody intended.
- More sessions or a new activity type (e.g. workshops): usually a deliberate
  course change; mention briefly or accept.
- An ordinary exam that disappeared: error-level, ask.
- Occasions shifted by weeks: check that the course still fits its period and
  does not collide with exam weeks or holidays.
- Changed exam modules (TEN1+TEN2 → TEN1): may reflect a new syllabus
  (kursplan); check the course page before asking.
- Degree-project courses (SA114X, …) and courses shared with many programmes
  have noisy schedules; focus on clear problems (sessions on holidays,
  in exam weeks; schedulers' own questions in the comment column).

### 3. Exams of parallel courses

- Mandatory courses of the same programme year: never the same day, ideally
  not consecutive days. Friday→Monday counts as fine (weekend between).
- **Re-exam paths:** students in year N who failed a year N−1 course retake it
  while taking year N courses. Their exams should not clash either; this cannot
  always be guaranteed, so it is a softer requirement. Same for two re-exams of
  the same year (students retaking two courses).
- Electives: clashes between electives in the same master-eligibility group
  are as serious as mandatory clashes. Other elective clashes are worth knowing
  about; same-subject electives (e.g. two SF math courses) are more likely to be
  combined than unrelated ones.
- Two codes on one row (e.g. DD2421 + FDD3431) are the same sitting, not a clash.

### 4. Teaching overlaps

Sessions (lectures, exercises, labs, seminars, KS, programme information) of
courses taken in parallel must not overlap; students cannot be in two places.

- Two whole-class sessions of mandatory courses overlapping: error.
- A whole-class session overlapping one group's session: affects that group
  only, still worth fixing. Two group sessions overlapping may be fine if the
  group divisions are coordinated; ask only if in doubt.
- Electives: same rules of thumb as for exams (master-eligibility groups count
  as mandatory; same-subject pairs matter more than unrelated ones). An
  elective overlap that already existed last year is a known pattern; raise it
  only if it got worse or affects many sessions.
- Optional activities (räknestuga, övrigt) matter less.
- The programme's own activities (code `8X<PROG>`, e.g. term-start
  information) count as mandatory. Shared slots of other codes (e.g. joint
  degree-project time for many programmes) are context.
- The same session listed under two codes (e.g. a course and its doctoral
  variant) is not a clash; neither is a re-exam during teaching.

The report's per-year panel states the number of sessions checked and whether
any overlap, so "no clashes" is visible as a result.

### 5. Data quality

- A teaching row tied to a course **round from another term** (e.g.
  "SK1104-51000 (HT25)" in VT27) is likely a stale round; ask the scheduler.
  On re-exam rows an old round is plausible (re-exam for an earlier round).
- An export that lacks the August re-exam window has too short a date range;
  re-export.

## Writing feedback

Be specific and checkable: course code, date and time, what is different from
last year (with last year's date), and a question rather than a demand when the
change might be intended. Group comments per course. Swedish is the default
language with the schedulers. The tool's draft comments follow this pattern;
they are drafts for a human to review and send.
