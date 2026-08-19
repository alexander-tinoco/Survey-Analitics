# CLAUDE.md — SurveyAnalytics

Operating rules for this repository. Claude reads this file at the start of every
session and **must** follow it. If any instruction here conflicts with a default
behaviour, this file wins.

---

## 1. What this project is

A web application whose core product is a **survey analytics engine**, not a form
builder. Users upload survey response data (CSV/XLSX) and the system runs it through
three analysis layers and turns the statistics into plain-language insights.

The full product brief lives in [`survey-analytics-idea.md`](survey-analytics-idea.md).
That file is the source of truth for scope. Do not silently expand beyond it.

### Analysis layers (the actual product)

| Layer | Delivers |
| --- | --- |
| **Descriptive** | Distributions, participation rates, missing values |
| **Relational** | Contingency tables, chi-square, correlations, segment comparison |
| **Pattern** | Respondent clustering, polarized vs. consensus detection |

### Stack (fixed — do not substitute without asking)

- **Backend:** Django + Django REST Framework
- **Database:** PostgreSQL
- **Analytics:** pandas, scipy, scikit-learn
- **Auth:** JWT via `djangorestframework-simplejwt`
- **Async & cache:** Celery + Redis
- **Frontend:** Django templates + HTMX + Chart.js (server-rendered monolith,
  no npm build step). DRF still exposes `/api/` and the HTMX views consume it.
- **Testing:** pytest + pytest-django + coverage.py
- **CI/CD:** Jenkins, Docker / Docker Compose

---

## 2. The swarm-forge workflow

Work advances through **sequential role phases inside a single session**. There are
no parallel sub-agents. Claude plays one role at a time, announces which role is
active, produces that role's output, and then **stops and waits for the user's
explicit approval** before moving on.

```
  ┌──────────────┐   approve   ┌──────────┐   approve   ┌─────────┐
  │  ARCHITECT   │ ──────────► │  CODER   │ ──────────► │ TESTER  │
  └──────────────┘             └──────────┘             └─────────┘
                                                             │ approve
                    ┌───────────┐   approve   ┌──────────┐   ▼
                    │ DOCUMENTER│ ◄────────── │ REVIEWER │ ◄─┘
                    └───────────┘             └──────────┘
                          │
                          ▼
                    commit + explain
```

### The roles

**1. ARCHITECT** — Designs. Writes the task breakdown, data model, module
boundaries, and trade-offs. Produces specs and ADRs in `docs/`. **Writes no
production code.** Output is a plan the user can say yes or no to.

**2. CODER** — Implements exactly one approved task. No scope creep, no
"while I was in there" refactors. If it finds a problem outside the task, it
reports it and keeps going with the original task.

**3. TESTER** — Writes the tests for what the coder built and runs them. Reports
real output, including failures. Never claims a passing suite it did not run.

**4. REVIEWER** — Reviews the diff against section 4 (Engineering standards).
Reports findings honestly, including "nothing to flag".

**5. DOCUMENTER** — Updates `README.md`, docstrings, `CHANGELOG.md`, and any ADR
touched by the change.

### Gate rules (non-negotiable)

- Claude **announces the active role** before producing output: `## 🧠 ARCHITECT`.
- Claude **stops at the end of every phase** and waits. It never chains two roles
  in one turn without the user saying so.
- The user approves each phase. "Approved", "dale", "sigue" advance it. Anything
  else is feedback to incorporate and re-present.
- Nothing is committed before the user approves the phase that produced it.

---

## 3. Task size and commit discipline

### One commit = one working vertical slice

A task is a **complete, functional unit of work** — something that does a real job
end to end and leaves the repo in a working state. Not a single file, and not a
whole milestone.

The right granularity is a **vertical slice**: the model *and* its migration *and*
the service that uses it *and* the serializer *and* the endpoint *and* the tests
that cover it, all in one commit. Splitting those apart produces commits that don't
build on their own and a history nobody can bisect.

Good task boundaries:

- ✅ "CSV/XLSX ingestion: model, upload endpoint, parser service, tests"
- ✅ "Chi-square contingency analysis: engine function, Celery task, cache layer, tests"
- ✅ "JWT auth: config, endpoints, login/register templates, tests"

Wrong on either side:

- ❌ "Add the ResponseDataset model" — too small, does nothing by itself
- ❌ "Build the whole analytics engine" — too big to review or approve

The test is simple: **could someone check out this commit and have a working repo
where that feature does its job?** If yes, it's the right size. If the change is
getting hard to describe in two or three sentences, it has grown into a milestone —
split it and get the split approved first.

### Documentation travels with the work

Docs are **not a commit**. A roadmap, an ADR, a README section, or a docstring ships
inside the commit that contains the code it describes. Committing a document on its
own inflates the history with entries nobody can review as work.

- ❌ `docs: add architecture decision record for storage format`
- ✅ `feat(ingest): add dataset upload and parsing` — *includes* the ADR that
  justifies the schema, the README section, and the tests

The only standalone `docs:` commit that is acceptable is one that fixes wrong or
misleading documentation about code that already exists.

The same applies to config and tooling: a linter rule, a CI tweak, or a dependency
bump rides along with the change that needed it, unless it is genuinely
self-contained infrastructure work (see M0 in the roadmap).

### One commit, one reason to exist

Each approved task ends in **its own commit**. No end-of-day mega-commits mixing
unrelated features, and no commits so thin that the message is longer than the
diff.

### Commit rules — read carefully

**Authorship belongs to the user alone.**

- ❌ **NEVER** add a `Co-Authored-By:` trailer of any kind.
- ❌ **NEVER** add `🤖 Generated with Claude Code` or any similar attribution.
- ❌ **NEVER** mention Claude, AI, or assistants in a commit message or its body.
- ✅ The commit message describes **the change**, and nothing else.

**Commits must be SSH-signed.** The repo relies on the user's global git config:

```
gpg.format      = ssh
user.signingkey = ~/.ssh/id_ed25519.pub
commit.gpgsign  = true
```

Before committing, verify signing is still on. After committing, verify the
signature landed:

```bash
git log --show-signature -1
git log -1 --pretty='%G?'   # expect G (good) or U — never N (unsigned)
```

If a commit comes out unsigned, stop and tell the user. Do not push unsigned work.

**Format:** [Conventional Commits](https://www.conventionalcommits.org/), in English,
imperative mood, subject ≤ 72 chars.

```
feat(analytics): add chi-square contingency service
fix(ingest): handle XLSX files with merged header cells
test(surveys): cover dataset upload validation
docs(adr): record choice of Celery over Django-Q
chore(ci): pin pytest to 8.x in Jenkinsfile
```

Scopes in use: `surveys`, `analytics`, `ingest`, `insights`, `api`, `auth`, `ui`,
`ci`, `docker`, `docs`, `adr`.

### Never commit without asking

Claude runs `git commit` only when the user has approved that phase. It never
pushes unless explicitly told to.

---

## 4. Engineering standards

This project is a portfolio piece. It should read like production code.

### Python / Django

- **Fat services, thin views.** Business logic lives in `services/`, never in views
  or serializers. Views orchestrate; services decide.
- **Analytics is framework-free.** Everything under `apps/analytics/engine/` takes
  and returns plain DataFrames and dataclasses — no Django imports. That keeps it
  unit-testable without a database and reusable outside the web app.
- **Type hints everywhere** on function signatures. `mypy`-friendly.
- **Docstrings** on every public module, class, and function, explaining *why*,
  not restating the code.
- Follow **PEP 8**, enforced by `ruff` (lint + format). Line length 100.
- No bare `except:`. Catch specific exceptions and let unexpected ones surface.
- Settings split: `config/settings/{base,local,production}.py`. **No secrets in the
  repo** — everything through environment variables (`django-environ`).
- Every model migration is committed alongside the model change that caused it.

### Async work

- Any computation that can exceed ~1 second (correlation matrices, clustering)
  goes to **Celery**. Never block a request on it.
- Results are cached in Redis with an explicit key strategy and TTL, keyed by
  dataset version so stale results can't leak after a re-upload.
- Tasks are idempotent and take primitive arguments (IDs, not model instances).

### Testing

- **Every feature commit ships its tests.** No "tests later".
- `pytest` + `pytest-django`, fixtures in `conftest.py`, factories via
  `factory_boy`. No fixtures loaded from JSON dumps.
- Statistical functions get tests with **hand-computed expected values**, so a
  silently wrong formula fails loudly.
- Coverage target: **≥ 85%** overall, **100%** on `apps/analytics/engine/`.
- Tests must not hit the network or depend on execution order.

### API

- REST, versioned under `/api/v1/`.
- DRF serializers for validation; never trust request data in a service.
- Consistent error envelope; correct status codes (`400` vs `422` vs `500`).
- Pagination on every list endpoint.

### Git hygiene

- Work on `main` is fine for this project, but **each task is its own commit**.
- No commented-out code. No `print()` debugging left behind — use `logging`.
- `.gitignore` covers `.env`, `__pycache__/`, `*.sqlite3`, `media/`, `.venv/`,
  `.coverage`, `htmlcov/`, `.ruff_cache/`, `.pytest_cache/`.

---

## 5. Design system — the cats

The product is professional; the **personality is playful**. The whole visual
identity is built around the cat illustrations in [`images/`](images/).

### Available assets

| File | Used for |
| --- | --- |
| `catHomePage.png` | Landing page hero — cat playing guitar |
| `catLogin.png` | Login screen |
| `catRegister.png` | Registration screen |
| `cat400.png` | HTTP 400 error page |
| `cat401.png` | HTTP 401 unauthorized page |
| `cat404.png` | HTTP 404 not found page |

If a state needs a cat that doesn't exist yet (empty dataset, processing, 500),
source a new illustration **in the same style** — black flat lineart on a
transparent/white background with sparse mint accents — and add it to `images/`
with the same naming convention.

### Visual rules

- **Palette:** ink black `#0B0B0B` on off-white `#FAFAF8`, with mint `#B8F2E6` as
  the single accent, pulled straight from the illustrations. One accent only —
  charts get their own sequential ramp derived from the mint.
- **Typography:** one geometric sans for UI, one mono for numbers and tables.
  Numbers are always tabular-figure aligned — this is an analytics product.
- **Tone of voice:** friendly and short. Empty states and errors are where the cats
  live and where copy can be witty. Dashboards, statistical output, and insight
  text stay precise and sober — **never** make a p-value cute.
- **Cats are punctuation, not wallpaper.** They own the landing, auth, error, and
  empty states. They stay out of the data views.
- Layout is generous and calm: lots of whitespace, hairline borders, minimal
  shadows. The playfulness comes from the illustrations, not from the chrome.
- Accessible by default: WCAG AA contrast, real focus states, `alt` text on every
  cat, keyboard-navigable, and never color as the sole carrier of meaning.

---

## 6. Communication with the user

The user is learning from this project. Explanation is part of the deliverable.

- **Conversation is in Spanish.** The repository — code, comments, docstrings,
  README, commit messages — is in **English**.
- **After every commit, Claude explains, in Spanish:**
  1. **Qué hice** — the change in plain terms.
  2. **El código** — walk through the key pieces and what each one does.
  3. **Por qué es buena práctica** — the principle behind it (why a service and not
     a view, why this test, why this index) and what it would cost to do it the
     lazy way.
  4. **Qué sigue** — the next task and which role handles it.
- Report reality. Failing tests are reported with their output. Skipped steps are
  named. Never describe work as done when it isn't.
- Flag real problems in one or two sentences, then keep working — the user decides
  whether to change course.

---

## 7. Session checklist

At the start of a session:

1. Read this file and `survey-analytics-idea.md`.
2. `git log --oneline -10` to see where the work stands.
3. Check `docs/ROADMAP.md` for the current phase and next task.
4. Announce the active role and the proposed task, then **wait for approval**.
