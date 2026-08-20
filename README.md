<h1 align="center">SurveyAnalytics</h1>

<p align="center">
  <img src="static/img/catHomePage.png" alt="Cat playing a guitar" width="180">
</p>

<p align="center">
  <em>Survey tools stop at counts and percentages. This one starts there.</em>
</p>

---

## What it does

Upload survey response data and get analysis, not another bar chart. The engine
runs three layers over the responses and states what it finds in plain language:

| Layer | Answers |
| --- | --- |
| **Descriptive** | How did people answer? Distributions, participation, missing data. |
| **Relational** | What goes with what? Contingency tables, chi-square, segment comparison. |
| **Pattern** | Who resembles whom? Respondent clusters, polarized vs. consensus questions. |

The output is a sentence a non-statistician can read, backed by the numbers that
produced it. Real output, from a 200-respondent dataset:

> 67.3% of respondents who answered "Engineering" to "Department" also answered
> "Agree" to "Satisfaction" — against 33.5% across everyone.

And on 30 respondents of random answers, the same engine reports **nothing at
all**. That is the harder half: a chi-square returns a plausible number for any
two columns, so findings are withheld unless they clear their own statistical
assumptions, survive correction for the number of comparisons made, and cover
enough respondents to describe someone.

Building surveys is deliberately **out of scope**. Google Forms does that well.
The gap is on the analysis side, and that is the entire product.

## Stack

Django · Django REST Framework · PostgreSQL · pandas · scipy · scikit-learn ·
Celery · Redis · HTMX · Chart.js · pytest · Docker · Jenkins

## Getting started

Requires Docker and Docker Compose. Nothing else — Python and Postgres run in
containers.

```bash
git clone git@github.com:alexander-tinoco/Survey-Analitics.git
cd Survey-Analitics

cp .env.example .env      # development defaults, safe to use as-is
make build
make migrate
make demo                 # optional: a demo account with the samples loaded
make up
```

The application is then at <http://localhost:8000>, with a health check at
<http://localhost:8000/health/>. Set `WEB_PORT` in `.env` if that port is taken.

### Signing in

`make demo` creates an account and loads all three sample files, so the
analysis is there to read on the first page you open:

| | |
| --- | --- |
| Email | `demo@example.com` |
| Password | `gato-analitico-99` |

These are development credentials in a local container with no data worth
protecting. They are printed here on purpose so the project can be evaluated
without a signup, and they must not survive a real deployment: `DJANGO_DEBUG`
is off in production settings and the account is created by an opt-in command,
never by a migration.

Without `make demo`, create your own account at `/accounts/register/` and start
a record with one of the sample files below.

### Sample data

Three exports ship in [`samples/`](samples/), each demonstrating a different
outcome:

| File | What it shows |
| --- | --- |
| `01-clear-relationship.csv` | 200 respondents with a genuine relationship between department and satisfaction, plus a coffee-preference column constructed to be unrelated. The unrelated pair is correctly rejected. |
| `02-distinct-groups.csv` | 240 respondents in three planted profiles, answering **Spanish** Likert scales — the ordinal ordering is recognized in both languages. |
| `03-no-findings.csv` | 60 respondents of random answers. Produces **no findings at all**, and says so. |

The third is the one worth uploading first. Any tool can print a number; the
question is what it does when there is nothing to report.

## How it works

### The decision everything hangs on

```
views / tasks   →   services/   →   engine/
   (Django)      (Django+pandas)   (pure Python)
```

`engine/` does not import Django. Not the ORM, not settings, not the
framework at all — only pandas, scipy and scikit-learn. A DataFrame goes in, a
frozen dataclass comes out. It performs no I/O: no files, no database, no
cache. The reasoning is recorded in
[ADR 0001](docs/adr/0001-framework-agnostic-analytics-engine.md).

The payoff is what a test of a statistical function looks like. Without the
separation, checking a chi-square means creating two hundred rows in a
database, and the setup obscures what is being asserted. With it, the case is
a literal:

```python
rows, columns = build({("Unsatisfied", "Low"): 40, ("Satisfied", "High"): 45})
result = associate("Satisfaction", "Support", rows, columns)
assert result.chi_square == pytest.approx(5.3333)
```

The descriptive engine's tests run in about a second with no database. That is
what makes a 100% coverage requirement on `engine/` reasonable rather than
performative: reaching it is cheap.

A rule stated in a document erodes, so a test walks the `engine/` package with
`ast` and fails the build if any module imports `django`, `rest_framework`,
`celery` or `apps`. The guard itself was verified by temporarily adding such an
import and watching it fail — a guard that has never failed is not known to
work.

### How responses are stored

An export arrives **wide**: one row per person, one column per question, and
every survey has different columns. Storing that shape directly makes the
database schema depend on the uploaded file. Two alternatives were rejected:

| Approach | Why not |
| --- | --- |
| A wide table per dataset | Requires creating tables at runtime; migrations stop meaning anything |
| A JSON blob per respondent | Every question becomes an unindexed key, so filtering by one answer scans every row, and the database cannot enforce that an answer refers to a question that exists |
| **Long format** ✅ | One fixed schema serves every survey |

So responses are stored **long** — one row per (respondent, question):

```
Survey ──< Dataset (versioned) ──< Question
                 │                     │
                 └──────< Response >───┘
```

The cost is real: `respondents × questions` rows, so a 240-person,
4-question upload is 960 rows. In exchange, adding a question to next year's
wave is an `INSERT` rather than a migration. Full reasoning in
[ADR 0002](docs/adr/0002-long-format-response-storage.md).

Datasets are **immutable and versioned**. Re-uploading creates a new version
rather than modifying the old one, which is what makes the analytics cache
safe — see below.

### The ingestion pipeline

```
uploaded bytes
   ↓  parsing.py  (pure)
detect delimiter → decode → read → clean → validate
   ↓  wide DataFrame
   ↓  inference.py  (pure)
infer each column's type
   ↓  question profiles
   ↓  ingestion.py  (touches the ORM)
create Dataset → create Questions → flatten to Responses
```

**Parsing** picks the delimiter by counting occurrences in the header row
among four candidates (`, ; \t |`). It works that way because of a real bug:
letting pandas sniff freely (`sep=None`) split the one-column header `Rating`
on the letter `t`. It then drops empty rows and columns, strips the `Unnamed: 0`
index column that appears when someone saved a DataFrame with its index, and
refuses files that are empty, header-only, over 500 columns, over 100,000 rows,
or that repeat a header — pandas silently renames duplicates to `Age`/`Age.1`,
which would show the user a question they never wrote.

**Inference** classifies each column, and the classification decides which
statistical tests are valid. A chi-square over free text returns a number, and
that number is noise.

| Type | How it is recognized |
| --- | --- |
| `numeric` | ≥80% of values parse as numbers, and the range does not look like a scale |
| `ordinal` | Matches a known rating scale (English or Spanish), or whole numbers anchored at 0/1 with a single-digit ceiling |
| `categorical` | Few distinct options, short answers |
| `free_text` | Mostly unique values, or long answers |

The numeric/ordinal rule was rewritten after a bug: five ages
`34, 29, 45, 38, 52` are five distinct whole numbers, and the first version
turned them into ranks 1-5, destroying the real ages. The rule is not *how
many* values there are but *where they sit* — a rating scale is anchored at 0
or 1 and tops out in single digits.

**Ingestion** is the only part that touches the ORM. It is `@transaction.atomic`
because a half-ingested dataset would report a respondent count its rows do not
support, and every later analysis would quietly compute against incomplete
data. Rows are written with `bulk_create` in batches of 2,000.

Each response keeps four things:

```python
raw_value         # exactly what the file contained
normalized_value  # whitespace collapsed, case preserved
numeric_value     # the number, or the rank on its scale
is_missing        # flag
```

`raw_value` is kept so that a parser bug can be fixed by re-deriving the other
fields, rather than by asking the user to upload again. The original file is
kept for the same reason, one level up. Missing answers are stored as rows
rather than omitted: drop them and the response count stops agreeing with the
respondent count, which makes participation rate uncomputable. An absence is
data.

### The four analysis layers

**Descriptive** — distributions, response rates, numeric summaries. Runs
inline, since it is cheap. Ordinal answers keep their scale order, because a
satisfaction chart sorted by frequency reads as noise while the same bars in
scale order read as a shape. Mean and median are both shown, with a flag when
they diverge by more than a fifth of a standard deviation — that gap is
exactly when quoting the mean alone misleads.

**Relational** — contingency tables, chi-square, Cramér's V. Runs on a worker,
because it is quadratic: 30 questions is 435 tests. Three guards are built in,
since chi-square returns a plausible number for any two columns:

1. **Expected-count validity** (Cochran's rule). Below it the approximation
   does not hold, so the result is shown but never reported as significant, no
   matter how small its p-value.
2. **Effect size beside significance.** With enough respondents a trivial
   association becomes "significant"; Cramér's V is independent of sample size
   and is what results are ranked by.
3. **Benjamini-Hochberg correction.** Twenty questions make 190 pairs, of which
   roughly ten look significant by chance. FDR rather than Bonferroni, because
   this is exploration, where missing a real pattern costs more than one false
   lead.

**Patterns** — k-means clustering and polarization. The hardest part, because
k-means *always* returns clusters: give it pure noise and it hands back six
tidy groups with labels. Random categorical answers reach a silhouette around
0.30, since one-hot encoding places respondents on the vertices of a hypercube
where genuine *geometric* separation exists without any *population* structure.

A fixed threshold cannot tell those apart, so the observed score is compared
against the same data with **each question's answers shuffled independently** —
which destroys every relationship between questions while preserving each
question's own distribution. Structure has to beat that, not merely exist:

| Dataset | Null | Observed | Verdict |
| --- | --- | --- | --- |
| Pure noise | 0.3134 | 0.3009 | **rejected** |
| Real structure | 0.6207 | 0.7664 | accepted |

Polarization is kept distinct from disagreement. Answers spread evenly across a
scale describe a population that has not settled; answers piled at both ends
and avoiding the middle describe one split into camps. Only the second is
called polarized.

**Insights** — the layer the product exists for. It reads the output of the
other three and states what it means, without recomputing anything, so a
sentence can never disagree with the table beside it. Every insight carries the
figures it was built from, and tests parse the numbers back out of the
generated text to check they match. Nothing that failed its assumptions,
survives only before correction, or covers too few respondents produces a
sentence at all.

### Background work and caching

```
browser              web              redis            worker
   │ GET /findings/
   ├───────────────►│ cached?
   │                ├───────────────►│ no
   │                │ cache.add(lock) ──atomic──►│
   │                ├──────── queue job ─────────────────►│
   │◄─── 202 ───────┤                                      │ computes
   │ poll 2s → 15s  │                          ◄─ store ───┤
   ├───────────────►│ cached? yes              ◄─ unlock ──┤
   │◄─── 200 ───────┤
```

The cache key contains the dataset id:

```python
f"analytics:relational:v1:dataset:{dataset_id}"
```

That is safe because of the storage decision above. Datasets are immutable, so
re-uploading produces a *new* id and the old key is simply never read again.
**There is no invalidation step to forget** — the classic cache bug cannot
occur by construction. The `v1` covers the other case: when the statistics
change, cached results are wrong even though the data did not change.

The lock uses `cache.add`, which is atomic in Redis, so two simultaneous
visitors cannot queue the same job twice. It is released only *after* the
result is stored, and also on failure, so a dead job never leaves a dataset
looking permanently busy.

The API answers `202` while working and `200` when ready. A `200` with an empty
list would read as "finished and found nothing" — indistinguishable from a real
result.

## What it does not do

Refuses to report a relationship whose expected cell counts are too small for
chi-square to mean anything. Refuses to call respondents a "segment" unless the
grouping beats one produced by shuffling the same answers at random. Refuses to
report a p-value without the effect size beside it. Each refusal is enforced by
a test, because the tempting failure in this domain is not a crash — it is a
confident sentence about noise.

## Known limitations

Stated rather than discovered later.

- **Everything fits in memory.** The engine assumes its input frame fits in
  RAM. The 100,000-row ingestion cap keeps that safe at survey scale, but this
  is not a tool for larger data.
- **Clustering oversegments.** On a synthetic set with three planted profiles
  it recovers four — the extra one is a reasonable subdivision, not noise, but
  it is more than were planted. Per-question weighting, a parsimony rule and
  deduplicating identical descriptions each reduced it; the remainder is
  inherent to k-means on categorical answers. Tuning further would fit the test
  fixture rather than the problem, so every profile is instead shown with the
  answers that define it, for the reader to judge.
- **Generated sentences are English templates.** Ordinal scales and
  non-answers are recognized in Spanish, but the findings themselves are not
  translated, and the phrasings are fixed.
- **No rate limiting.** Nothing stops a user from queueing many uploads at
  once and saturating the worker.
- **Free-text answers are stored but never analyzed.** No topic extraction or
  sentiment — they are excluded from every test on purpose, since a
  cross-tabulation of prose is meaningless.
- **The 500 page reuses the 400 illustration.** No dedicated cat exists for it
  yet.

## Common tasks

```bash
make help        # list every target
make test        # pytest with coverage
make lint        # ruff check + format check
make format      # apply fixes
make shell          # shell inside the web container
make worker-reload  # restart Celery after editing a task
make worker-logs    # follow the Celery worker
make test-engine    # analytics engine at its stricter 100% gate
make ci-up          # start the local Jenkins server (see docs/CI.md)
make clean          # stop the stack and drop the database volume
```

## Project layout

```
config/              Project configuration
  settings/          base / local / production
  celery.py          Celery application
  error_views.py     400 / 403 / 404 / 500 handlers
apps/
  accounts/          Custom user model, JWT and session auth
  surveys/           Ingestion: models, parsing, type inference
    services/        parsing.py and inference.py are pure; ingestion.py is not
  analytics/
    engine/          Pure Python statistics — no Django imports (ADR 0001)
      descriptive.py   distributions, response rates, numeric summaries
      relational.py    contingency tables, chi-square, Cramér's V, FDR
      patterns.py      clustering with a permutation null, polarization
      insights.py      statistics → sentences
    services/        ORM ↔ DataFrame translation, caching, job control
    tasks.py         Celery jobs
    exports.py       CSV and JSON rendering of findings
docs/
  ROADMAP.md         Milestones and their commits
  CI.md              Pipeline, and running Jenkins locally
  adr/               Architecture decision records
static/
  css/cats.css       Design tokens and every component
  js/charts.js       Chart.js rendering
  js/vendor/         Vendored third-party assets
  img/               Cat illustrations, served as Django static files
templates/           Server-rendered pages
tests/               Test suite, mirroring the apps
```

## Documentation

- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what is built and what comes next
- [`docs/adr/`](docs/adr/) — why the architecture looks the way it does
- [`docs/CI.md`](docs/CI.md) — the pipeline, and how to run Jenkins locally
- [`CLAUDE.md`](CLAUDE.md) — engineering standards and workflow for this repository

## Testing

```bash
make test
```

```bash
make test           # whole suite, 85% floor
make test-engine    # analytics engine only, 100% floor
```

The project-wide floor is 85%. The analytics engine is held to **100%**,
enforced as its own CI stage, because it is pure and fast to test and an
untested branch there returns a plausible wrong number rather than crashing.

Statistical functions are tested against expected values computed by hand and
written into the docstring:

```python
def test_statistic_matches_the_hand_computed_value(self):
    """Table:
               B1   B2  | total
        A1     10   20  |   30
        A2     30   20  |   50
        total  40   40  |   80

    chi2 = (10-15)^2/15 + (20-15)^2/15 + (30-25)^2/25 + (20-25)^2/25
         = 1.6667 + 1.6667 + 1 + 1 = 5.3333
    """
```

Deriving the expected value with the same library the code uses would only
prove pandas agrees with itself — a wrong formula would pass. Written by hand,
it fails.

There are more lines of test than of application code, which is deliberate for
a project whose failure mode is not a crash but a confident wrong answer.

## License

Not yet licensed.
