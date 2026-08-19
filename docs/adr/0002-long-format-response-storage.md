# 0002 — Long-format response storage

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

Uploaded survey exports arrive **wide**: one row per respondent, one column per
question. Every survey has a different set of columns, and the same survey changes
between waves.

Storing that shape directly means the database schema depends on the file being
uploaded. Two variants were considered:

1. **Wide table per dataset** — create a physical table with a column per question
   at upload time. Requires runtime DDL, makes migrations meaningless, and turns
   "compare question 3 against question 7" into dynamic SQL over an unknown schema.
2. **Wide JSON blob** — one row per respondent with answers in a `JSONField`.
   No DDL, but every question becomes an unindexed key inside a document, so
   filtering by a single answer scans every row and the database cannot enforce
   that an answer refers to a question that exists.

Both make the number of questions a *schema* concern. It should be a *data*
concern.

## Decision

Store responses in **long format**: one row per (respondent, question) pair.

```
Survey ──< Dataset (versioned) ──< Question
                  │                    │
                  └──────< Response >───┘
```

- **`Survey`** — the logical survey, stable across re-uploads.
- **`Dataset`** — one upload, with a monotonically increasing `version`. Immutable
  once ingested.
- **`Question`** — belongs to a dataset; carries text, position, and inferred type
  (categorical / ordinal / numeric / free text).
- **`Response`** — one answer: `(dataset, respondent_key, question, raw_value,
  normalized_value)`.

Notes on the shape:

- `respondent_key` is a per-dataset identifier, not a `User` FK — respondents are
  survey participants, not application accounts.
- Both `raw_value` and `normalized_value` are kept, so the original export is
  always recoverable and parsing bugs are fixable without a re-upload.
- Datasets are versioned rather than mutated, which is what makes the Redis cache
  key in M4 safe: a key scoped to `dataset_id` can never serve stale results,
  because a re-upload produces a different dataset.
- Indexes on `(dataset, question)` and `(dataset, respondent_key)` cover the two
  access patterns: per-question aggregation and per-respondent reconstruction.

The engine ([ADR 0001](0001-framework-agnostic-analytics-engine.md)) never sees
this shape. Services pivot long → wide with `DataFrame.pivot` before calling it,
because pandas, scipy, and scikit-learn all expect wide input.

## Consequences

**Accepted costs**

- Row count is `respondents × questions` — a 500-respondent, 40-question survey
  stores 20,000 rows. Small for Postgres, but not free.
- Every analysis pays a pivot on the way into the engine. Mitigated by caching
  results (M4), not by denormalizing storage.
- Reading raw rows is less intuitive than looking at a wide table.

**Gained**

- One fixed schema serves every survey. No runtime DDL, no migration per upload.
- Referential integrity is real: an answer cannot point at a question that does
  not exist.
- Adding, removing, or reordering questions between waves is ordinary data, not a
  schema change.
- Long format is the natural shape for per-question aggregation and for the
  contingency tables in M4, which pair two questions at a time.
- Versioned, immutable datasets give correct cache invalidation for free.
