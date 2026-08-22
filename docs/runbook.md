# Runbook

## Daily operation

```bash
python -m nba_warehouse.cli run-date --date YYYY-MM-DD
```

This ingests to bronze, loads silver, rebuilds gold, and writes
`data/reports/reconciliation_<date>.json`. Check `"status"` in the report.

## When reconciliation fails

1. Open the report: which check failed?
   - `player_rows_accounted_for` / `team_rows_accounted_for`: rows were lost
     between bronze and silver. Check `rejected_record` for that date; if the
     gap is not explained by quarantined rows, inspect the loader logs.
   - `two_team_rows_per_game`: a game is missing one side — usually a partial
     API response. Re-ingest the date.
2. Fix and replay from bronze (no new API call needed):

```bash
python -m nba_warehouse.cli run-date --date YYYY-MM-DD --skip-ingest
```

## Quarantined rows

```sql
SELECT reason, COUNT(*) FROM rejected_record
WHERE game_date = 'YYYY-MM-DD' GROUP BY reason;
```

Quarantine is expected for malformed source rows. A sudden spike means the API
schema drifted — compare the newest bronze snapshot's headers against
`silver/parser.py`.

## Backfill a date range

```bash
python -m nba_warehouse.cli replay --start-date 2026-01-01 --end-date 2026-01-31
```

Safe to re-run at any time: silver loads are UPSERTs on natural keys and gold
is rebuilt from silver, so replays are idempotent (verified by
`tests/integration/test_idempotency.py`).

## Schema changes

Never edit tables manually. Add a migration:

```bash
alembic revision -m "add column x"
# edit the generated file
alembic upgrade head
```
