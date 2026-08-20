# Vendored fonts

Self-hosted rather than linked from a CDN, for the same reason as
`static/js/vendor/`: the application renders with no external requests, works
offline, and cannot break because someone else changed a file.

Both are variable fonts, so one file per family covers every weight used.
Latin subset only — the interface is English.

| File | Family | Axes used | License |
| --- | --- | --- | --- |
| `archivo-variable.woff2` | Archivo | wght 400–700 | SIL Open Font License 1.1 |
| `roboto-mono-variable.woff2` | Roboto Mono | wght 400–500 | Apache License 2.0 |

**Archivo** (Omnibus-Type) is a grotesque drawn for highly legible
text at small sizes in official and editorial documents — the register this
product's record surfaces work in.

**Roboto Mono** carries every figure in the interface. Numbers are set in a
monospace face here because they are measurements to be compared column by
column, not because monospace looks technical.

To update, replace the file with the matching latin-subset build and update
the row above in the same commit.
