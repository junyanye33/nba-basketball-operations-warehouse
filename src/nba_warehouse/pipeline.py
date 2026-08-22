"""Pipeline orchestration: ingest -> bronze -> silver -> gold -> reconcile.

Each step is a pure function over (settings, logical_date) so the same code
path serves daily runs, replays, and backfills.
"""
import json
import time
from collections import defaultdict

from nba_warehouse.bronze.writer import latest_bronze_file, write_bronze
from nba_warehouse.config import Settings
from nba_warehouse.extract.client import (
    fetch_full_season_game_log,
    fetch_league_game_log,
)
from nba_warehouse.gold.build import build_gold
from nba_warehouse.quality.reconciliation import reconcile_date
from nba_warehouse.silver.loader import get_engine, init_db, load_silver
from nba_warehouse.silver.parser import (
    derive_games,
    parse_player_game_log,
    parse_team_game_log,
)

ENDPOINT_PLAYER = "leaguegamelog_player"
ENDPOINT_TEAM = "leaguegamelog_team"


def ingest_date(settings: Settings, logical_date: str) -> dict:
    """Fetch raw payloads from the NBA Stats API and land them in bronze."""
    player_payload = fetch_league_game_log(settings.season, logical_date, "P")
    time.sleep(1.5)  # polite pacing between API calls
    team_payload = fetch_league_game_log(settings.season, logical_date, "T")
    write_bronze(settings, player_payload, ENDPOINT_PLAYER, logical_date)
    write_bronze(settings, team_payload, ENDPOINT_TEAM, logical_date)
    return {"date": logical_date, "ingested": [ENDPOINT_PLAYER, ENDPOINT_TEAM]}


def split_payload_by_game_date(payload: dict) -> dict[str, dict]:
    """Split one season response into replayable daily NBA API payloads."""
    result_set = payload["resultSets"][0]
    headers = result_set["headers"]
    game_date_index = headers.index("GAME_DATE")
    rows_by_date: dict[str, list] = defaultdict(list)
    for row in result_set["rowSet"]:
        rows_by_date[str(row[game_date_index])].append(row)

    return {
        logical_date: {
            "resource": payload.get("resource", "leaguegamelog"),
            "parameters": {
                **payload.get("parameters", {}),
                "DateFrom": logical_date,
                "DateTo": logical_date,
            },
            "resultSets": [
                {
                    "name": result_set.get("name", "LeagueGameLog"),
                    "headers": headers,
                    "rowSet": rows,
                }
            ],
        }
        for logical_date, rows in rows_by_date.items()
    }


def ingest_full_season(settings: Settings) -> list[str]:
    """Fetch the regular season twice, then persist daily bronze snapshots."""
    player_payload = fetch_full_season_game_log(settings.season, "P")
    time.sleep(1.5)
    team_payload = fetch_full_season_game_log(settings.season, "T")

    players_by_date = split_payload_by_game_date(player_payload)
    teams_by_date = split_payload_by_game_date(team_payload)
    if players_by_date.keys() != teams_by_date.keys():
        missing_player_dates = sorted(teams_by_date.keys() - players_by_date.keys())
        missing_team_dates = sorted(players_by_date.keys() - teams_by_date.keys())
        raise ValueError(
            "Season payload date mismatch. "
            f"Missing player dates: {missing_player_dates}; "
            f"missing team dates: {missing_team_dates}"
        )

    logical_dates = sorted(players_by_date)
    for logical_date in logical_dates:
        write_bronze(
            settings,
            players_by_date[logical_date],
            ENDPOINT_PLAYER,
            logical_date,
        )
        write_bronze(
            settings,
            teams_by_date[logical_date],
            ENDPOINT_TEAM,
            logical_date,
        )
    return logical_dates


def load_date(settings: Settings, logical_date: str) -> dict:
    """Parse the latest bronze snapshots for a date and upsert into silver."""
    player_file = latest_bronze_file(settings, ENDPOINT_PLAYER, logical_date)
    team_file = latest_bronze_file(settings, ENDPOINT_TEAM, logical_date)
    if player_file is None or team_file is None:
        raise FileNotFoundError(
            f"No bronze snapshot for {logical_date}; run ingest first."
        )

    player_result = parse_player_game_log(
        json.loads(player_file.read_text(encoding="utf-8"))
    )
    team_result = parse_team_game_log(json.loads(team_file.read_text(encoding="utf-8")))
    games = derive_games(team_result.rows, settings.season)

    rejects = [dict(r, endpoint=ENDPOINT_PLAYER) for r in player_result.rejects] + [
        dict(r, endpoint=ENDPOINT_TEAM) for r in team_result.rejects
    ]

    engine = get_engine(settings.database_url)
    init_db(settings.database_url)
    return load_silver(
        engine,
        logical_date,
        games,
        team_result.rows,
        player_result.rows,
        rejects,
    )


def run_date(settings: Settings, logical_date: str, skip_ingest: bool = False) -> dict:
    """Full pipeline for one logical date."""
    if not skip_ingest:
        ingest_date(settings, logical_date)
    load_stats = load_date(settings, logical_date)
    gold_stats = build_gold(settings)
    report = reconcile_date(settings, logical_date)
    return {
        "date": logical_date,
        "silver": load_stats,
        "gold": gold_stats,
        "reconciliation_status": report["status"],
    }


def run_full_season(settings: Settings, skip_ingest: bool = False) -> dict:
    """Load and reconcile every regular-season game date, then build gold once."""
    if skip_ingest:
        season_dir = (
            settings.bronze_dir
            / f"season={settings.season}"
            / f"endpoint={ENDPOINT_TEAM}"
        )
        logical_dates = sorted(
            path.name.removeprefix("game_date=")
            for path in season_dir.glob("game_date=*")
            if path.is_dir()
        )
    else:
        logical_dates = ingest_full_season(settings)

    if not logical_dates:
        raise FileNotFoundError("No regular-season bronze snapshots were found.")

    total_loaded = 0
    total_rejected = 0
    failed_dates = []
    for logical_date in logical_dates:
        load_stats = load_date(settings, logical_date)
        total_loaded += load_stats["rows_loaded"]
        total_rejected += load_stats["rows_rejected"]
        report = reconcile_date(settings, logical_date)
        if report["status"] != "pass":
            failed_dates.append(logical_date)

    gold_stats = build_gold(settings)
    return {
        "season": settings.season,
        "first_game_date": logical_dates[0],
        "last_game_date": logical_dates[-1],
        "game_dates": len(logical_dates),
        "rows_loaded": total_loaded,
        "rows_rejected": total_rejected,
        "reconciliation_passed": len(logical_dates) - len(failed_dates),
        "reconciliation_failed": failed_dates,
        "gold": gold_stats,
    }
