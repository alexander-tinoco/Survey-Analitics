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
make up
```

The application is then at <http://localhost:8000>, with a health check at
<http://localhost:8000/health/>.

## What it does not do

Refuses to report a relationship whose expected cell counts are too small for
chi-square to mean anything. Refuses to call respondents a "segment" unless the
grouping beats one produced by shuffling the same answers at random. Refuses to
report a p-value without the effect size beside it. Each refusal is enforced by
a test, because the tempting failure in this domain is not a crash — it is a
confident sentence about noise.

## Common tasks

```bash
make help        # list every target
make test        # pytest with coverage
make lint        # ruff check + format check
make format      # apply fixes
make shell       # shell inside the web container
make worker-reload  # restart Celery after editing a task
make clean       # stop the stack and drop the database volume
```

## Project layout

```
config/            Project configuration
  settings/        base / local / production
  celery.py        Celery application
apps/              Feature apps (added per milestone)
  analytics/
    engine/        Pure Python statistics — no Django imports (ADR 0001)
    services/      ORM ↔ DataFrame translation
docs/
  ROADMAP.md       Milestones and their commits
  adr/             Architecture decision records
static/
  img/             Cat illustrations, served as Django static files
tests/             Test suite
```

## Documentation

- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what is built and what comes next
- [`docs/adr/`](docs/adr/) — why the architecture looks the way it does
- [`CLAUDE.md`](CLAUDE.md) — engineering standards and workflow for this repository

## Testing

```bash
make test
```

The suite enforces a coverage floor of 85%, raised for the analytics engine,
where statistical functions are tested against hand-computed expected values so
a wrong formula fails loudly instead of returning a plausible number.

## License

Not yet licensed.
