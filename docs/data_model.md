# Data Model

## Silver (PostgreSQL) — relational, typed, validated

| Table | Grain | Primary key | Notes |
|---|---|---|---|
| `dim_team` | one row per team | `team_id` | |
| `dim_player` | one row per player | `player_id` | `team_id` = most recent team |
| `stg_game` | one row per game | `game_id` | home/away FKs to `dim_team`; index on `game_date` |
| `stg_team_game` | one row per (game, team) | `(game_id, team_id)` | exactly 2 rows per game (tested) |
| `stg_player_game` | one row per (game, player) | `(game_id, player_id)` | indexes on `game_date` and `(player_id, game_date)` |
| `rejected_record` | one row per quarantined raw row | surrogate `id` | reason + raw payload, never dropped silently |
| `pipeline_run` | one row per pipeline execution | `run_id` | audit: status, rows loaded/rejected |

Schema changes ship as version-controlled Alembic migrations (`migrations/`).

## Gold (DuckDB) — columnar, analytics-ready

| Table | Grain | Key point |
|---|---|---|
| `fact_player_game` | (game, player) | mirror of silver, columnar |
| `fact_team_game` | (game, team) | mirror of silver, columnar |
| `dim_game` | game | |
| `mart_player_form` | (game, player) | rolling averages over the **prior** 10 games only (`ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING`) — no leakage of the current game |
| `mart_team_schedule_context` | (game, team) | `days_rest`, `is_back_to_back` via `LAG` over game dates |
| `mart_data_completeness` | game_date | expected vs actual team-game rows |

## Why this grain design

- Natural keys (`game_id`, `player_id`, `team_id`) come from the source system,
  which makes loads idempotent: an UPSERT on the natural key means replaying a
  date can never create duplicates.
- Player-game and team-game are kept as separate facts because they answer
  different questions and have different cardinalities; deriving one from the
  other at query time would be slower and error-prone.
