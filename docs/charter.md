# Project Charter

## Business problem

A basketball operations / analytics group needs trustworthy, up-to-date player
and team performance data for the 2025-26 NBA season to support scouting notes,
matchup previews, and workload monitoring. Analysts currently pull ad-hoc stats
manually; numbers are inconsistent between reports and nobody can say whether a
given night's data is complete.

## Users

- **Analysts** query gold marts for player form and schedule context.
- **Engineers** operate the pipeline and respond to quality report failures.

## Deliverable

A daily pipeline producing three marts a analyst can trust without re-checking:

1. Player rolling form *entering* each game (leakage-safe).
2. Team schedule context (rest days, back-to-backs).
3. A per-date data completeness report.

## Success criteria (MVP acceptance)

- One command runs the full pipeline for a date; re-running it is a no-op.
- 100% of raw rows are either loaded or quarantined with a reason — proven by
  an automated reconciliation report per date.
- All marts covered by automated grain/uniqueness/leakage tests in CI.
- A new engineer can run the offline smoke demo in under 5 minutes.

## Scope

**In:** regular-season player/team box-score logs (NBA Stats `leaguegamelog`),
bronze/silver/gold layers, reconciliation, backfill, CI.

**Out (non-goals):** live in-game data, play-by-play, ML predictions, BI
dashboards, streaming. These are future iterations, not this repo's job.

## Key decisions

| Decision | Rationale |
|---|---|
| `leaguegamelog` as the single source endpoint | One call per date returns all games; fewer API calls, simpler reconciliation |
| PostgreSQL for silver | OLTP-style constraints, UPSERT, migration tooling |
| DuckDB for gold | Columnar window functions, zero-ops analytics store |
| SQLite in smoke mode | Anyone can run the demo with zero infrastructure |
