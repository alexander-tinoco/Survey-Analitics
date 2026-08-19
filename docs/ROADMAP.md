# Roadmap

Delivery plan for SurveyAnalytics. Scope comes from
[`survey-analytics-idea.md`](../survey-analytics-idea.md); process rules come from
[`CLAUDE.md`](../CLAUDE.md).

Each row below is **one commit**: a working vertical slice that leaves the
repository in a functional state. Milestones are approved and executed in order.

**Legend:** ⬜ not started · 🟨 in progress · ✅ done

---

## M0 — Foundation

Get a reproducible environment and a green pipeline before any feature exists.
Nothing after this milestone is trustworthy without it.

| # | Commit | Contents | Status |
| --- | --- | --- | --- |
| M0.1 | `chore(docker): add development stack` | `docker-compose.yml` (web, Postgres 16, Redis 7), `Dockerfile`, `.env.example`, `Makefile` shortcuts | ⬜ |
| M0.2 | `chore(ci): add Django project skeleton and pipeline` | `config/settings/{base,local,production}.py`, `django-environ` wiring, `ruff` + `pytest` + `coverage` config, `Jenkinsfile`, smoke test | ⬜ |

**Done when:** `docker compose up` serves Django, `pytest` runs green, `ruff check`
is clean, and the Jenkins pipeline reproduces all three.

---

## M1 — Authentication

JWT for the API, session-backed pages for the HTML views, and the first two cats
on screen.

| # | Commit | Contents | Status |
| --- | --- | --- | --- |
| M1.1 | `feat(auth): add JWT authentication` | Custom user model, `simplejwt` config, `/api/v1/auth/` (register, login, refresh), serializers, tests | ⬜ |
| M1.2 | `feat(ui): add base layout and auth screens` | `base.html`, design tokens in `cats.css`, login/register templates using `catLogin.png` / `catRegister.png`, error pages for 400/401/404, tests | ⬜ |

**Done when:** a user can register and log in from the browser and obtain a JWT
from the API, and the error pages render their cats.

---

## M2 — Ingestion

The entry point of the whole product. Everything downstream reads what this
milestone writes, so the schema decision here ([ADR 0002](adr/0002-long-format-response-storage.md))
matters more than the code.

| # | Commit | Contents | Status |
| --- | --- | --- | --- |
| M2.1 | `feat(ingest): add dataset upload and parsing` | `Survey`, `Dataset`, `Question`, `Response` models + migrations, CSV/XLSX parser service, upload endpoint with validation, tests | ⬜ |
| M2.2 | `feat(ingest): add question type inference and dataset versioning` | Type inference (categorical / ordinal / numeric / free text), re-upload creates a new dataset version, dataset detail view, tests | ⬜ |

**Done when:** uploading a real survey export produces typed questions and
normalized responses, and re-uploading bumps the version instead of overwriting.

---

## M3 — Descriptive layer

First layer of the engine, and the first thing a user actually sees as analysis.

| # | Commit | Contents | Status |
| --- | --- | --- | --- |
| M3.1 | `feat(analytics): add descriptive engine` | `engine/descriptive.py` — distributions, participation rate, missing values; pure DataFrame in / dataclass out, unit tests with hand-computed values | ⬜ |
| M3.2 | `feat(ui): add descriptive dashboard` | `/api/v1/datasets/<id>/descriptive/`, dashboard template, Chart.js rendering, empty state, tests | ⬜ |

**Done when:** a user uploads a file and sees per-question distributions in the
browser.

---

## M4 — Relational layer

The first genuinely expensive computation, so this is where Celery and the cache
strategy get proven.

| # | Commit | Contents | Status |
| --- | --- | --- | --- |
| M4.1 | `feat(analytics): add contingency and chi-square analysis` | `engine/relational.py` — contingency tables, chi-square with Cramér's V, segment comparison; unit tests against hand-computed values | ⬜ |
| M4.2 | `feat(analytics): run relational analysis asynchronously` | Celery task, Redis cache keyed by dataset version, job status endpoint, polling UI, tests | ⬜ |

**Done when:** requesting a correlation matrix returns immediately with a job id,
the result is cached, and re-uploading the dataset invalidates it.

---

## M5 — Pattern layer & insights

The differentiator: this is what generic survey tools do not do.

| # | Commit | Contents | Status |
| --- | --- | --- | --- |
| M5.1 | `feat(analytics): add respondent clustering` | `engine/patterns.py` — encoding, k-means with silhouette-based k selection, cluster profiling, tests | ⬜ |
| M5.2 | `feat(analytics): add polarization detection` | Consensus vs. polarized scoring per question, tests | ⬜ |
| M5.3 | `feat(insights): add plain-language insight generation` | Template-based narration of statistical results, ranking by relevance, insights panel in the UI, tests | ⬜ |

**Done when:** the app states findings in sentences a non-statistician can read,
backed by the numbers that produced them.

---

## Out of scope

Recorded so it stays decided rather than re-argued:

- **Survey building / form rendering.** Google Forms does this well; the product
  brief is explicit that the value is on the analysis side.
- **Real-time collaboration**, multi-tenant billing, and public sharing links.
- **Google Forms/Sheets import.** Named in the brief as a possible source, but
  deferred until file ingestion is solid — it is a connector, not a capability.
