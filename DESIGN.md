# Design

The world is **The Bound Record**: a numbered laboratory notebook rather than a
dashboard. It was chosen over the category's default because a dashboard has no
way to render *"nothing was found"* as anything but an empty state — and this
product withholds findings often enough that its refusal needs to look like a
result. A notebook writes the null result down with the same care as a positive
one.

Two disciplines were donated by directions that lost the round: **one colour
reserved exclusively for the action that commits**, and **radical scale
hierarchy** — the finding being read swells while the rest of the record
recedes.

## Ground and palette

The scene is an office under fluorescent light with the blinds open, not a
reading lamp. The page is therefore light and slightly cold: engineering-paper
white cooled toward green, never cream.

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#f4f6f3` | Page ground |
| `--paper-raised` | `#fbfcfa` | Sheets, masthead, evidence blocks |
| `--ink` | `#0b0f0e` | Body text, rules that separate sections |
| `--ink-soft` | `#4a5551` | Secondary prose |
| `--ink-faint` | `#78837e` | Labels, captions, entry numbers |
| `--rule` | `#d5ddd7` | Hairline separators |
| `--rule-strong` | `#b6c2ba` | Input borders, scrollbar thumb |
| `--grid` | `rgba(31,111,99,.07)` | The 24px ruling the record is written on |
| `--mint` / `--mint-ink` | `#b8f2e6` / `#145a50` | Countersignature: recorded, confirmed |
| `--correction` | `#b8322b` | **Reserved.** Actions that commit, and statements the reader must not skim |
| `--stamp` | `#1f6f63` | The mark beside a checked line |

The mint is inherited from the cat illustrations, where it appears in the eyes.
Its role changed with the world: it is no longer a decorative accent but the
colour of something countersigned.

**Correction red appears on nothing decorative.** It is the destructive and
committing button, the focus ring, the caret, the disclosure marker, and the
border of a withheld result. If it appears anywhere else, that is a bug.

## Type

| Face | Use | Why |
| --- | --- | --- |
| **Archivo** 400/600/700 | All prose and headings | A grotesque drawn for legibility at small sizes in official and editorial documents — the register a record works in |
| **Roboto Mono** 400/500 | Every figure, all metadata | Numbers here are measurements compared down a column, so they are monospaced and tabular |

Both are self-hosted variable fonts, latin subset (`static/fonts/`). Figures
carry `font-variant-numeric: tabular-nums` everywhere, without exception.

Headings run `-0.025em` tracking and `text-wrap: balance`. Body measure is
capped at `68ch`.

## Structure

- **Hairline rules, not cards.** Sections are separated by a 1px rule and a top
  border; nothing is boxed unless it is a sheet the reader writes into (forms)
  or a figure block attached to a claim.
- **2px radii.** Paper is cut, not rounded.
- **No shadows.** Depth in a bound record comes from rules and ground, not from
  elevation.
- **The 24px grid is drawn once at page level.** It is the paper, so it never
  repeats inside a container and never becomes texture.

## Components

`.entry-head` states which record the reader is inside, on every surface that
has one. `.finding` is a two-column grid of entry number and body; the first
finding is set at headline scale and the rest recede. `.stamp` carries status
as a word plus a colour, never colour alone. `.readings` is a ruled instrument
line rather than a row of KPI cards. `.withheld` gives a null result the width
and weight of a finding.

`.index` is the record's table of contents: a sticky rail from `60rem`, and a
horizontally scrollable strip below that. It marks the section being read with
`aria-current` via IntersectionObserver.

## Illustrations

The cats own the landing, authentication, error and empty states. They appear
on no surface that shows data — a cat beside a p-value undercuts the number it
sits next to. A test asserts this on the record page.

`static/img/cat400.png` currently stands in on the 500 page; no dedicated
illustration exists for it yet.

## Browser surfaces

Selection, caret, scrollbars and focus rings are themed from the palette. Focus
is a 2px correction-red outline at 2px offset, never removed.

## Motion

One authored moment: smooth scrolling to a section, and the index mark that
follows the reader. Transitions are 0.12–0.15s on interactive states only.
Everything is disabled under `prefers-reduced-motion`.

## Accessibility

WCAG AA contrast throughout. Every chart has a table beside it with the same
numbers. Table captions are visually hidden but present, because a screen
reader navigating table-by-table has no heading context. Colour never carries
meaning alone.
