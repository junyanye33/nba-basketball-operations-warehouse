"""Silver relational schema (PostgreSQL in live mode, SQLite in smoke mode).

Grain contracts:
    dim_team          one row per NBA team
    dim_player        one row per player
    stg_game          one row per game_id
    stg_team_game     one row per (game_id, team_id)     -- exactly 2 per game
    stg_player_game   one row per (game_id, player_id)
    rejected_record   quarantine for rows failing validation (never dropped silently)
    pipeline_run      audit log of every pipeline execution
"""
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

dim_team = Table(
    "dim_team",
    metadata,
    Column("team_id", Integer, primary_key=True),
    Column("team_abbreviation", String(10), nullable=False),
    Column("team_name", String(100)),
)

dim_player = Table(
    "dim_player",
    metadata,
    Column("player_id", Integer, primary_key=True),
    Column("player_name", String(120), nullable=False),
    Column("team_id", Integer),
)

stg_game = Table(
    "stg_game",
    metadata,
    Column("game_id", String(20), primary_key=True),
    Column("season", String(10), nullable=False),
    Column("game_date", Date, nullable=False),
    Column("home_team_id", Integer, nullable=False),
    Column("away_team_id", Integer, nullable=False),
    Column("home_points", Integer),
    Column("away_points", Integer),
    # Neutral-site games (e.g. NBA Europe games): source marks both teams as
    # away, so home/away are deterministic slots rather than true venue roles.
    Column("is_neutral", Integer, nullable=False, server_default="0"),
    Index("ix_stg_game_date", "game_date"),
)

stg_team_game = Table(
    "stg_team_game",
    metadata,
    Column("game_id", String(20), primary_key=True),
    Column("team_id", Integer, primary_key=True),
    Column("game_date", Date, nullable=False),
    Column("is_home", Integer, nullable=False),
    Column("win", Integer),
    Column("points", Integer),
    Column("fgm", Integer),
    Column("fga", Integer),
    Column("fg3m", Integer),
    Column("fg3a", Integer),
    Column("ftm", Integer),
    Column("fta", Integer),
    Column("oreb", Integer),
    Column("dreb", Integer),
    Column("reb", Integer),
    Column("ast", Integer),
    Column("stl", Integer),
    Column("blk", Integer),
    Column("tov", Integer),
    Column("pf", Integer),
    Column("plus_minus", Float),
    Index("ix_stg_team_game_date", "game_date"),
)

stg_player_game = Table(
    "stg_player_game",
    metadata,
    Column("game_id", String(20), primary_key=True),
    Column("player_id", Integer, primary_key=True),
    Column("team_id", Integer, nullable=False),
    Column("game_date", Date, nullable=False),
    Column("minutes", Float),
    Column("points", Integer),
    Column("fgm", Integer),
    Column("fga", Integer),
    Column("fg3m", Integer),
    Column("fg3a", Integer),
    Column("ftm", Integer),
    Column("fta", Integer),
    Column("oreb", Integer),
    Column("dreb", Integer),
    Column("reb", Integer),
    Column("ast", Integer),
    Column("stl", Integer),
    Column("blk", Integer),
    Column("tov", Integer),
    Column("pf", Integer),
    Column("plus_minus", Float),
    Index("ix_stg_player_game_date", "game_date"),
    Index("ix_stg_player_game_player", "player_id", "game_date"),
)

rejected_record = Table(
    "rejected_record",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(40), nullable=False),
    Column("endpoint", String(50), nullable=False),
    Column("game_date", Date),
    Column("reason", String(200), nullable=False),
    Column("raw_row", Text),
    Column("rejected_at", DateTime, nullable=False),
)

pipeline_run = Table(
    "pipeline_run",
    metadata,
    Column("run_id", String(40), primary_key=True),
    Column("logical_date", Date, nullable=False),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime),
    Column("status", String(20), nullable=False),
    Column("rows_loaded", Integer),
    Column("rows_rejected", Integer),
    Column("detail", Text),
)
