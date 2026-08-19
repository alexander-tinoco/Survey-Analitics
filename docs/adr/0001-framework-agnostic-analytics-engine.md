# 0001 — Framework-agnostic analytics engine

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

The analytics engine is the product. Everything else — auth, upload forms,
dashboards — is delivery mechanism around it. That inverts the usual Django
priority, and the code layout should reflect it.

The default Django instinct is to put analysis logic in model methods or manager
querysets, where it can reach the ORM directly. That is convenient to write and
expensive to live with:

- Every statistical test needs a database to run, so the fastest tests in the
  project become the slowest.
- Test setup drifts toward "create 200 Response rows" instead of "here is a
  DataFrame with these five values", which obscures what is being asserted.
- The statistics get coupled to a storage schema that will change (see
  [ADR 0002](0002-long-format-response-storage.md)), so schema changes break math
  that had no reason to care.
- Reusing the engine outside the web app — a notebook, a CLI, a scheduled job —
  requires dragging Django settings along.

## Decision

Everything under `apps/analytics/engine/` is **pure Python**. It imports pandas,
scipy, and scikit-learn, and it must not import Django, the ORM, or project
settings.

The contract at the boundary:

- **Input:** a `pandas.DataFrame` plus explicit parameters.
- **Output:** frozen `dataclass` result objects. No dicts, no `QuerySet`, no
  serializers.
- **No I/O.** The engine does not read files, hit the database, touch the cache,
  or log to external systems.

Translation between the ORM and DataFrames lives in `apps/analytics/services/`.
Services load data, call the engine, and persist or cache the result. Celery tasks
call services, never the engine directly.

```
views/tasks  →  services/  →  engine/
 (Django)      (Django +      (pure Python:
                pandas)        pandas/scipy/sklearn)
```

A test enforces the boundary: it walks `engine/` and fails if any module imports
`django`.

## Consequences

**Accepted costs**

- An explicit mapping layer has to be written and maintained; some data is loaded
  into memory that a SQL aggregate could have computed in the database.
- Contributors cannot take the shortcut of reaching for a queryset mid-calculation.
- Very large datasets will eventually need chunking, since the engine assumes its
  input fits in memory. Acceptable at survey scale (thousands of respondents, not
  millions).

**Gained**

- Statistical correctness is testable in isolation, in milliseconds, against
  hand-computed expected values. This is why `CLAUDE.md` can demand 100% coverage
  on `engine/` — it is cheap to reach and genuinely meaningful.
- Storage schema and statistics evolve independently.
- The engine is reusable from a notebook or CLI with a plain `import`.
- The dependency direction is one-way and checkable, so the boundary cannot rot
  quietly.
