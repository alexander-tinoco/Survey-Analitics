# Roadmap

Delivery plan for SurveyAnalytics. Scope comes from
[`survey-analytics-idea.md`](../survey-analytics-idea.md); process rules come from
[`CLAUDE.md`](../CLAUDE.md).

Each milestone below is **one commit**: a working vertical slice that leaves the
repository in a functional state, with its tests and its documentation included.
Milestones are approved and executed in order.

**Legend:** ⬜ not started · 🟨 in progress · ✅ done

---

## ✅ M0 — Foundation

`chore: bootstrap Django project with Docker stack and CI pipeline`

Reproducible environment and a green pipeline before any feature exists. This is
the one milestone that is pure infrastructure, because nothing after it is
trustworthy without it.

- `docker-compose.yml` (web, Postgres 16, Redis 7) with healthchecks, `Dockerfile`,
  `.env.example`, `Makefile`
- `config/settings/{base,local,production}.py` with `django-environ`
- `ruff`, `pytest`, `coverage` configured in `pyproject.toml`
- `Jenkinsfile` running lint → test → coverage gate
- Smoke test and `README.md` with setup instructions

**Done when:** `make up` serves Django, `make test` is green, `make lint` is clean,
and Jenkins reproduces all three.

---

## ✅ M1 — Authentication and shell

`feat(auth): add JWT authentication and application shell`

JWT for the API, session-backed pages for the HTML views, and the first cats on
screen. Auth and layout ship together because a login page needs a layout and a
layout without auth has nothing to protect.

- Custom user model, `simplejwt`, `/api/v1/auth/` (register, login, refresh)
- `base.html`, design tokens in `cats.css`, login and register screens
  (`catLogin.png`, `catRegister.png`)
- 400 / 401 / 404 error pages with their cats
- Tests for the auth flows and the protected-route redirect

**Done when:** a user registers and logs in from the browser, the API issues a JWT,
and the error pages render.

---

## ✅ M2 — Ingestion

`feat(ingest): add survey dataset upload and parsing`

The entry point of the product. Everything downstream reads what this milestone
writes, so the schema decision ([ADR 0002](adr/0002-long-format-response-storage.md))
matters more than the code.

- `Survey`, `Dataset`, `Question`, `Response` models and migrations
- CSV/XLSX parser service, upload endpoint with validation
- Question type inference (categorical / ordinal / numeric / free text)
- Dataset versioning on re-upload, dataset list and detail screens
- Tests covering malformed files, mixed types, and version bumps

**Done when:** uploading a real survey export produces typed questions and
normalized responses, and re-uploading bumps the version instead of overwriting.

---

## ✅ M3 — Descriptive layer

`feat(analytics): add descriptive analysis and dashboard`

First layer of the engine and the first thing a user sees as analysis.

- `engine/descriptive.py` — distributions, participation rate, missing values;
  DataFrame in, dataclass out ([ADR 0001](adr/0001-framework-agnostic-analytics-engine.md))
- Import-boundary test that fails if `engine/` imports Django
- `/api/v1/datasets/<id>/descriptive/`, dashboard template, Chart.js rendering
- Empty state with its cat
- Unit tests with hand-computed expected values

**Done when:** a user uploads a file and sees per-question distributions in the
browser.

---

## ✅ M4 — Relational layer

`feat(analytics): add relational analysis with async processing`

The first genuinely expensive computation, so this is where Celery and the cache
strategy get proven.

- `engine/relational.py` — contingency tables, chi-square with Cramér's V,
  segment comparison
- Celery task, Redis cache keyed by dataset version, job status endpoint
- Polling UI with a processing state
- Tests for the statistics and for cache invalidation on re-upload

**Done when:** requesting a correlation matrix returns immediately with a job id,
the result is cached, and re-uploading the dataset invalidates it.

---

## ⬜ M5 — Pattern layer

`feat(analytics): add respondent clustering and polarization detection`

- `engine/patterns.py` — encoding, k-means with silhouette-based k selection,
  cluster profiling
- Consensus vs. polarized scoring per question
- Cluster and polarization views in the dashboard
- Tests on synthetic datasets with known cluster structure

**Done when:** the app groups respondents into profiles and flags which questions
divide them.

---

## ⬜ M6 — Insight generation

`feat(insights): add plain-language insight generation`

The differentiator: what generic survey tools do not do.

- Template-based narration of statistical results
- Relevance ranking so the strongest findings surface first
- Insights panel in the UI, linked to the numbers that produced each sentence
- Tests asserting that generated sentences match the statistics behind them

**Done when:** the app states findings in sentences a non-statistician can read,
backed by the data that produced them.

---

## Out of scope

Recorded so it stays decided rather than re-argued:

- **Survey building / form rendering.** Google Forms does this well; the product
  brief is explicit that the value is on the analysis side.
- **Real-time collaboration**, multi-tenant billing, and public sharing links.
- **Google Forms/Sheets import.** Named in the brief as a possible source, but
  deferred until file ingestion is solid — it is a connector, not a capability.
