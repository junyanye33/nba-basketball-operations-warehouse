"""Idempotent silver loads: dialect-aware UPSERT keyed on natural keys.

Re-running the same date produces identical row counts (safe replays/backfills).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Table, create_engine, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine

from nba_warehouse.silver import schema


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url)


def init_db(database_url: str) -> None:
    engine = get_engine(database_url)
    schema.metadata.create_all(engine)


def upsert(conn: Connection, table: Table, rows: list[dict], key_cols: list[str]) -> int:
    if not rows:
        return 0
    dialect = conn.dialect.name
    if dialect == "postgresql":
        ins = pg_insert(table)
    elif dialect == "sqlite":
        ins = sqlite_insert(table)
    else:
        raise NotImplementedError(f"Unsupported dialect: {dialect}")
    update_cols = {
        c.name: ins.excluded[c.name] for c in table.columns if c.name not in key_cols
    }
    stmt = ins.on_conflict_do_update(index_elements=key_cols, set_=update_cols)
    conn.execute(stmt, rows)
    return len(rows)


def _project(rows: list[dict], table: Table) -> list[dict]:
    cols = {c.name for c in table.columns}
    return [{k: v for k, v in row.items() if k in cols} for row in rows]


def load_silver(
    engine: Engine,
    logical_date: str,
    games: list[dict],
    team_rows: list[dict],
    player_rows: list[dict],
    rejects: list[dict],
) -> dict:
    """Load one logical date transactionally. Returns load stats."""
    run_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    logical = datetime.strptime(logical_date, "%Y-%m-%d").date()

    teams = {
        row["team_id"]: {
            "team_id": row["team_id"],
            "team_abbreviation": row["team_abbreviation"],
            "team_name": row.get("team_name"),
        }
        for row in team_rows
    }
    players = {
        row["player_id"]: {
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "team_id": row["team_id"],
        }
        for row in player_rows
    }

    with engine.begin() as conn:
        loaded = 0
        loaded += upsert(conn, schema.dim_team, list(teams.values()), ["team_id"])
        loaded += upsert(conn, schema.dim_player, list(players.values()), ["player_id"])
        loaded += upsert(conn, schema.stg_game, _project(games, schema.stg_game), ["game_id"])
        loaded += upsert(
            conn,
            schema.stg_team_game,
            _project(team_rows, schema.stg_team_game),
            ["game_id", "team_id"],
        )
        loaded += upsert(
            conn,
            schema.stg_player_game,
            _project(player_rows, schema.stg_player_game),
            ["game_id", "player_id"],
        )

        # A date replay replaces that date's quarantine result. This prevents
        # duplicate rejected rows and also removes stale rejects after a parser
        # fix makes previously invalid source rows loadable.
        conn.execute(
            schema.rejected_record.delete().where(
                schema.rejected_record.c.game_date == logical
            )
        )
        if rejects:
            conn.execute(
                schema.rejected_record.insert(),
                [
                    {
                        "run_id": run_id,
                        "endpoint": r.get("endpoint", "leaguegamelog"),
                        "game_date": logical,
                        "reason": r["reason"][:200],
                        "raw_row": r["raw_row"],
                        "rejected_at": started,
                    }
                    for r in rejects
                ],
            )

        conn.execute(
            schema.pipeline_run.insert(),
            [
                {
                    "run_id": run_id,
                    "logical_date": logical,
                    "started_at": started,
                    "finished_at": datetime.now(timezone.utc).replace(tzinfo=None),
                    "status": "success",
                    "rows_loaded": loaded,
                    "rows_rejected": len(rejects),
                    "detail": None,
                }
            ],
        )

    return {"run_id": run_id, "rows_loaded": loaded, "rows_rejected": len(rejects)}


def silver_counts(engine: Engine, logical_date: str) -> dict:
    """Row counts for one date, used by reconciliation."""
    logical = datetime.strptime(logical_date, "%Y-%m-%d").date()
    with engine.connect() as conn:
        def count(table, date_col):
            return conn.execute(
                select(func.count()).select_from(table).where(date_col == logical)
            ).scalar_one()

        return {
            "games": count(schema.stg_game, schema.stg_game.c.game_date),
            "team_games": count(schema.stg_team_game, schema.stg_team_game.c.game_date),
            "player_games": count(
                schema.stg_player_game, schema.stg_player_game.c.game_date
            ),
            "rejected": count(
                schema.rejected_record, schema.rejected_record.c.game_date
            ),
        }
