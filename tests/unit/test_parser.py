from datetime import date

import pytest

from nba_warehouse.silver.parser import (
    derive_games,
    parse_game_date,
    parse_minutes,
    parse_player_game_log,
    parse_team_game_log,
)
from nba_warehouse.pipeline import split_payload_by_game_date
from tests.conftest import load_fixture


def test_parse_minutes_formats():
    assert parse_minutes("36:20") == pytest.approx(36.33, abs=0.01)
    assert parse_minutes("05:00") == 5.0
    assert parse_minutes(240) == 240.0
    assert parse_minutes(None) is None
    assert parse_minutes("") is None


def test_parse_game_date_formats():
    assert parse_game_date("2026-01-10") == date(2026, 1, 10)
    assert parse_game_date("JAN 10, 2026") == date(2026, 1, 10)
    with pytest.raises(ValueError):
        parse_game_date("not-a-date")


def test_player_parse_valid_rows():
    result = parse_player_game_log(load_fixture("player_gamelog", "2026-01-10"))
    assert len(result.rows) == 4
    assert len(result.rejects) == 0
    tatum = next(r for r in result.rows if r["player_id"] == 1628369)
    assert tatum["points"] == 30
    assert tatum["game_id"] == "0022500641"
    assert tatum["game_date"] == date(2026, 1, 10)


def test_player_parse_quarantines_bad_row():
    result = parse_player_game_log(load_fixture("player_gamelog", "2026-01-12"))
    assert len(result.rows) == 4
    assert len(result.rejects) == 1
    assert "PLAYER_ID" in result.rejects[0]["reason"]


def test_neutral_site_game_derivation():
    # Real edge case (NBA Europe game 0022500578 on 2026-01-15): the source
    # marks BOTH teams as away, so home/away become deterministic slots.
    def team_row(team_id, points):
        return {
            "game_id": "0022500578",
            "team_id": team_id,
            "game_date": date(2026, 1, 15),
            "is_home": 0,
            "points": points,
        }

    games = derive_games([team_row(1610612763, 111), team_row(1610612753, 118)], "2025-26")
    assert len(games) == 1
    game = games[0]
    assert game["is_neutral"] == 1
    # Deterministic slots: higher team_id takes the home slot
    assert game["home_team_id"] == 1610612763
    assert game["away_team_id"] == 1610612753
    # Replays produce identical output regardless of input order
    assert derive_games([team_row(1610612753, 118), team_row(1610612763, 111)], "2025-26") == games


def test_team_parse_and_game_derivation():
    result = parse_team_game_log(load_fixture("team_gamelog", "2026-01-10"))
    assert len(result.rows) == 2
    games = derive_games(result.rows, "2025-26")
    assert len(games) == 1
    game = games[0]
    assert game["home_team_id"] == 1610612738  # BOS hosted ("vs.")
    assert game["away_team_id"] == 1610612765
    assert game["home_points"] == 112
    assert game["away_points"] == 104


def test_split_full_season_payload_into_daily_snapshots():
    first = load_fixture("player_gamelog", "2026-01-10")
    second = load_fixture("player_gamelog", "2026-01-12")
    payload = {
        **first,
        "resultSets": [
            {
                **first["resultSets"][0],
                "rowSet": (
                    first["resultSets"][0]["rowSet"]
                    + second["resultSets"][0]["rowSet"]
                ),
            }
        ],
    }

    daily = split_payload_by_game_date(payload)

    assert sorted(daily) == ["2026-01-10", "2026-01-12"]
    assert len(daily["2026-01-10"]["resultSets"][0]["rowSet"]) == 4
    assert len(daily["2026-01-12"]["resultSets"][0]["rowSet"]) == 5
    assert daily["2026-01-10"]["parameters"]["DateFrom"] == "2026-01-10"
