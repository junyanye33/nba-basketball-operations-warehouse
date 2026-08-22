"""Gold layer: analytics facts and marts in DuckDB.

Marts are leakage-safe: rolling windows use ROWS BETWEEN N PRECEDING AND
1 PRECEDING so a game's own stats never leak into its "form entering the game".
"""
import duckdb
import pandas as pd

from nba_warehouse.config import Settings
from nba_warehouse.silver.loader import get_engine

MART_SQL = """
CREATE OR REPLACE TABLE fact_player_game AS
SELECT * FROM df_player_game;

CREATE OR REPLACE TABLE fact_team_game AS
SELECT * FROM df_team_game;

CREATE OR REPLACE TABLE dim_game AS
SELECT * FROM df_game;

CREATE OR REPLACE TABLE dim_player AS
SELECT * FROM df_player;

CREATE OR REPLACE TABLE dim_team AS
SELECT * FROM df_team;

CREATE OR REPLACE TABLE mart_player_form AS
SELECT
    player_id,
    game_id,
    game_date,
    points,
    minutes,
    COUNT(*) OVER w                    AS games_prior_10,
    AVG(points) OVER w                 AS avg_points_prior_10,
    AVG(minutes) OVER w                AS avg_minutes_prior_10,
    AVG(reb) OVER w                    AS avg_reb_prior_10,
    AVG(ast) OVER w                    AS avg_ast_prior_10
FROM fact_player_game
WINDOW w AS (
    PARTITION BY player_id
    ORDER BY game_date, game_id
    ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
);

CREATE OR REPLACE TABLE mart_team_schedule_context AS
SELECT
    team_id,
    game_id,
    game_date,
    is_home,
    win,
    points,
    DATE_DIFF(
        'day',
        LAG(game_date) OVER (PARTITION BY team_id ORDER BY game_date, game_id),
        game_date
    )                                   AS days_rest,
    CASE
        WHEN DATE_DIFF(
            'day',
            LAG(game_date) OVER (PARTITION BY team_id ORDER BY game_date, game_id),
            game_date
        ) = 1 THEN 1 ELSE 0
    END                                 AS is_back_to_back
FROM fact_team_game;

CREATE OR REPLACE TABLE mart_data_completeness AS
SELECT
    g.game_date,
    COUNT(DISTINCT g.game_id)                       AS games,
    COUNT(DISTINCT tg.game_id || '-' || CAST(tg.team_id AS VARCHAR)) AS team_game_rows,
    COUNT(DISTINCT g.game_id) * 2                   AS expected_team_game_rows,
    CASE
        WHEN COUNT(DISTINCT tg.game_id || '-' || CAST(tg.team_id AS VARCHAR))
             = COUNT(DISTINCT g.game_id) * 2
        THEN 'complete' ELSE 'incomplete'
    END                                             AS status
FROM dim_game g
LEFT JOIN fact_team_game tg USING (game_id)
GROUP BY g.game_date
ORDER BY g.game_date;
"""


def build_gold(settings: Settings) -> dict:
    """Export silver tables into DuckDB and rebuild facts + marts."""
    engine = get_engine(settings.database_url)
    with engine.connect() as conn:
        df_player_game = pd.read_sql("SELECT * FROM stg_player_game", conn)
        df_team_game = pd.read_sql("SELECT * FROM stg_team_game", conn)
        df_game = pd.read_sql("SELECT * FROM stg_game", conn)
        df_player = pd.read_sql("SELECT * FROM dim_player", conn)
        df_team = pd.read_sql("SELECT * FROM dim_team", conn)

    for df in (df_player_game, df_team_game, df_game):
        if "game_date" in df.columns:
            df["game_date"] = pd.to_datetime(df["game_date"]).dt.date

    con = duckdb.connect(str(settings.duckdb_path))
    try:
        con.register("df_player_game", df_player_game)
        con.register("df_team_game", df_team_game)
        con.register("df_game", df_game)
        con.register("df_player", df_player)
        con.register("df_team", df_team)
        con.execute(MART_SQL)
        stats = {
            "fact_player_game": con.sql("SELECT COUNT(*) FROM fact_player_game").fetchone()[0],
            "fact_team_game": con.sql("SELECT COUNT(*) FROM fact_team_game").fetchone()[0],
            "dim_game": con.sql("SELECT COUNT(*) FROM dim_game").fetchone()[0],
            "mart_player_form": con.sql("SELECT COUNT(*) FROM mart_player_form").fetchone()[0],
        }
    finally:
        con.close()
    return stats
