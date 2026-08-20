# v1.0.0 — Survey analysis that knows when to stay quiet

Google Forms tells you 68% chose "Agree" and stops. This is the analysis that
comes after — and the refusal to report one when the data does not support it.

## What it does

Upload a survey export and it reads the responses the way an analyst would:

- **Descriptive** — distributions, participation, and which question people avoided
- **Relational** — every pair of questions cross-tabulated, ranked by strength
- **Pattern** — respondent profiles, and which questions split the room
- **Findings** — the above, written as sentences with the figures attached

From the included 200-respondent sample:

> **50.6%** of respondents who answered "Ingeniería" to "Departamento" also
> answered "Muy de acuerdo" to "Estoy satisfecho con mi puesto" — against
> **16.7%** across everyone.

From 60 respondents of random answers: **nothing at all**, stated as a result.

## What makes it different

A chi-square returns a plausible number for any two columns, and most tools
print it. Three guards live in the engine rather than in the reader's judgement:

- **Expected-count validity** (Cochran's rule) — an unreliable test is never
  reported as significant, however small its p-value
- **Effect size beside significance** — Cramér's V, reported in words, is what
  results are ranked by
- **Benjamini-Hochberg correction** — twenty questions make 190 pairs, of which
  ten look significant by chance alone

Clustering is validated against a **permutation null** rather than a fixed
threshold, after a test caught random categorical data scoring 0.30 — twice the
cutoff that looked reasonable. One-hot encoding creates real geometric
separation where no population structure exists; a constant cannot tell those
apart, and a null derived from the data itself can.

## Engineering

- The analytics engine imports **no framework** — pandas, scipy and sklearn
  only. A test walks the package with `ast` and fails the build otherwise.
- **383 tests**, 98.6% coverage overall, **100% on the engine** as its own CI
  stage. Statistical functions are checked against values computed by hand.
- Immutable versioned datasets, which is what makes the analytics cache key
  safe by construction: there is no invalidation step to forget.
- Heavy analysis on Celery with an atomic Redis lock; `202` while computing,
  `200` when ready.
- Ordinal scales recognized in **English and Spanish**, accents folded.
- Findings export as CSV or JSON, each carrying its evidence.

## Getting started

```bash
cp .env.example .env
make build && make migrate && make demo && make up
```

Then sign in at <http://localhost:8000> with `demo@example.com` /
`gato-analitico-99`. Three sample exports ship in `samples/`; upload
`03-no-findings.csv` first.

## Known limitations

No public deployment. Everything must fit in memory (capped at 100,000 rows).
Clustering oversegments on categorical answers. Findings are generated from
English templates even when the survey is in Spanish. Free text is stored but
never analyzed.

---

**Full documentation:** [README](../README.md) ·
**Design:** [DESIGN.md](../DESIGN.md) ·
**Decisions:** [ADRs](adr/)
