"""Replaying the same logical date must not change silver row counts."""
from sqlalchemy import func, select

from nba_warehouse.pipeline import load_date
from nba_warehouse.silver import schema
from nba_warehouse.silver.loader import get_engine
from tests.conftest import make_settings, run_full_pipeline


def _counts(engine) -> dict:
    with engine.connect() as conn:
        return {
            table.name: conn.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
            for table in (
                schema.stg_game,
                schema.stg_team_game,
                schema.stg_player_game,
                schema.dim_player,
                schema.dim_team,
                schema.rejected_record,
            )
        }


def test_replay_is_idempotent(tmp_path):
    settings = run_full_pipeline(make_settings(tmp_path))
    engine = get_engine(settings.database_url)

    before = _counts(engine)
    # Replay both dates from existing bronze snapshots
    load_date(settings, "2026-01-10")
    load_date(settings, "2026-01-12")
    after = _counts(engine)

    assert before == after
    assert before["stg_player_game"] == 8  # 4 players x 2 games
    assert before["stg_team_game"] == 4
    assert before["stg_game"] == 2
    assert before["rejected_record"] == 1
