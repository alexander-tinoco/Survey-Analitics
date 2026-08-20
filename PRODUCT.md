# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Analysts and HR staff inside institutions — universities, hospitals, companies
— who run internal surveys and receive the results as a CSV or Excel export.

They are competent with spreadsheets and **not** statisticians. They know what
a percentage is; they do not know what a p-value is, and will not learn one to
use this tool. The interface is responsible for explaining any statistical term
it puts on screen.

Their situation is batch work, not daily use: a survey closes, they get the
file, and they need conclusions they can defend to a director or a committee.
They arrive with a deadline, work in one sustained session, take the findings
away, and do not return until the next survey.

## Product Purpose

Turn raw survey response data into findings a non-statistician can read, state
and act on.

Success is a user who uploads a file and leaves with a sentence they are
willing to put in front of their director — and the numbers to back it up if
they are challenged.

## Positioning

Survey tools stop at counts and percentages. This is the analysis that comes
after: which answers travel together, which respondents form a group, which
questions split the room.

The mechanism a neighbouring product could not truthfully copy is **restraint
under statistical scrutiny**. A chi-square returns a plausible number for any
two columns, and most tools report it. This one withholds a finding unless it
clears its own assumptions (Cochran's rule), survives correction for the number
of comparisons made (Benjamini-Hochberg), and covers enough respondents to
describe someone. On a dataset of random answers it reports **nothing**, and
says so.

Building surveys is deliberately out of scope. Google Forms does that well.

## Operating Context

- Input arrives as a file export — CSV or XLSX — not through an integration.
  The user finds it in a downloads folder and uploads it.
- Survey content is frequently in **Spanish**, even though the interface is in
  English. Likert scales and non-answers are recognized in both languages.
- The output leaves the application: it goes into a slide deck, a report, or an
  email to a committee. Export is part of the job, not a convenience.
- Heavy analysis runs on a worker and takes seconds to minutes, so the
  interface has to represent work in progress honestly.
- Surveys are re-run in waves. The same survey gets uploaded again next
  quarter, and earlier results must remain valid for the data that produced
  them.

## Capabilities and Constraints

**Confirmed capabilities**

- CSV/XLSX ingestion with delimiter detection, cleaning, and validation.
- Question type inference: categorical, ordinal, numeric, free text.
- Three analysis layers — descriptive, relational (contingency, chi-square,
  Cramér's V), pattern (respondent clustering, polarization).
- Plain-language findings, ranked by effect size weighted with coverage.
- CSV and JSON export of findings, carrying the evidence behind each sentence.
- Immutable, versioned datasets; JWT API alongside the server-rendered pages.

**Constraints**

- Data must fit in memory. Ingestion is capped at 100,000 rows and 500 columns.
- Clustering oversegments on categorical answers: three planted profiles come
  back as four. Profiles are therefore always shown with the answers that
  define them, for the reader to judge.
- Generated findings are English templates. There is no i18n layer.
- Free-text answers are stored but never analyzed — no topic extraction, no
  sentiment. They are excluded from every statistical test on purpose.
- No rate limiting.

**Terminology the interface must not assume is known**

p-value, chi-square, Cramér's V, silhouette, correction for multiple
comparisons, ordinal, polarization. Each may appear, but never unexplained.

## Brand Commitments

- Name: **SurveyAnalytics**.
- The visual identity is built on a set of cat illustrations in `static/img/`
  (landing, login, register, 400, 401, 404). These are binding assets.
- **Cats are punctuation, not wallpaper.** They own the landing, auth, error
  and empty states. They stay out of every view that shows data — a cat beside
  a p-value undercuts the number it sits next to.
- Voice: friendly and short in empty states and errors; precise and sober
  wherever statistics appear. Never make a p-value cute.
- Palette drawn from the illustrations: ink black, off-white, one mint accent.

## Evidence on Hand

- Working engine with real verified output. On a 200-respondent set with a
  constructed relationship it reports *"67.3% of respondents who answered
  'Engineering' to 'Department' also answered 'Agree' to 'Satisfaction' —
  against 33.5% across everyone."* On 30 respondents of random answers it
  reports nothing.
- 387 tests, 99.6% coverage overall, 100% on the analysis engine.
- CI pipeline running green (lint, tests, engine coverage gate).
- Architecture decision records in `docs/adr/`.
- **No** customers, testimonials, benchmarks, pricing, or deployment. Nothing
  here may be fabricated: the product has never been used by a real
  institution.

## Product Principles

1. **Silence is a valid answer.** Reporting nothing on weak data is the
   feature, not a failure state. The interface must present it as a finding.
2. **Every claim carries its evidence.** No sentence appears without the
   figures behind it, and the user must always be able to reach the table that
   produced it.
3. **The finding is the product; the charts are support.** A user who reads
   only the first screen should already have something they can say out loud.
4. **Explain the statistics in place.** Any term the interface uses, it
   defines — at the moment it is used, not in a help page.
5. **The work leaves the building.** Findings are drafted here and presented
   elsewhere, so exporting is a first-class path, not a secondary action.

## Accessibility & Inclusion

- WCAG AA contrast, visible focus states, full keyboard navigation.
- Colour is never the sole carrier of meaning — every status that uses colour
  also carries a word.
- Every chart has a table beside it with the same numbers; a canvas is opaque
  to a screen reader.
- Numbers are set in tabular figures so columns can be compared by eye.
