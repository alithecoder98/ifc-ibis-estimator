# Estimating rules (placeholder)

**Placeholder content** — the client's real short-form estimating guidance (how an
estimator actually reasons about edge cases: which material determines the code when
an element has mixed materials, how proxies/unknowns get flagged, etc.) hasn't arrived
yet, same blocking status as `data/codes_clean.csv`, `data/rules_initial.json`, and
`data/ground_truth.csv` (see `CLAUDE.md` "Still open"). This file exists so Phase 3.4's
LLM prompt has something real to include rather than an empty section; replace its
content with the client's actual rules the moment they're available — nothing else
needs to change, the prompt template reads this file as plain text.

- If an element has no quantity data at all (neither Qto nor computed from geometry),
  flag it rather than guessing a code from class alone.
- A composite element with more than one material layer is usually a hint it will need
  splitting into one line per layer during review — flag it as a candidate for that,
  don't try to pick a single code for the whole thing.
- An `IfcBuildingElementProxy` is, by definition, something the architect's authoring
  tool couldn't classify properly — treat it as low-confidence and flag it, even when a
  candidate code looks like a plausible match.
- When two candidate codes seem equally plausible, prefer the one whose family matches
  the element's structural role (e.g. a load-bearing wall over a finish code) and flag
  the ambiguity rather than picking silently.
