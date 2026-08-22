"""Contract tests on the gold DuckDB marts (grain, leakage safety, completeness)."""
import duckdb
import pytest


@pytest.fixture(scope="module")
def gold(pipeline_env):
    con = duckdb.connect(str(pipeline_env.duckdb_path), read_only=True)
    yield con
    con.close()


def test_fact_player_game_grain_is_unique(gold):
    dupes = gold.sql(
        """
        SELECT game_id, player_id, COUNT(*) AS n
        FROM fact_player_game GROUP BY 1, 2 HAVING COUNT(*) > 1
        """
    ).fetchall()
    assert dupes == []


def test_every_game_has_exactly_two_team_rows(gold):
    bad = gold.sql(
        """
        SELECT game_id FROM fact_team_game
        GROUP BY game_id HAVING COUNT(*) <> 2
        """
    ).fetchall()
    assert bad == []


def test_player_form_is_leakage_safe(gold):
    # Tatum scored 30 on Jan 10 and 24 on Jan 12. His "form entering Jan 12"
    # must be exactly the Jan 10 value -- the Jan 12 game must not leak in.
    row = gold.sql(
        """
        SELECT games_prior_10, avg_points_prior_10
        FROM mart_player_form
        WHERE player_id = 1628369 AND game_id = '0022500655'
        """
    ).fetchone()
    assert row == (1, 30.0)

    # First-ever game: no prior data, so the window must be empty, not zero.
    first = gold.sql(
        """
        SELECT games_prior_10, avg_points_prior_10
        FROM mart_player_form
        WHERE player_id = 1628369 AND game_id = '0022500641'
        """
    ).fetchone()
    assert first[0] == 0
    assert first[1] is None


def test_schedule_context_days_rest(gold):
    row = gold.sql(
        """
        SELECT days_rest, is_back_to_back
        FROM mart_team_schedule_context
        WHERE team_id = 1610612738 AND game_id = '0022500655'
        """
    ).fetchone()
    assert row == (2, 0)


def test_data_completeness_mart(gold):
    rows = gold.sql(
        "SELECT game_date, status FROM mart_data_completeness ORDER BY game_date"
    ).fetchall()
    assert len(rows) == 2
    assert all(status == "complete" for _, status in rows)
