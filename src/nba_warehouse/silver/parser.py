"""Parse raw NBA Stats leaguegamelog payloads into typed silver rows.

Every raw row either becomes a valid typed row or a quarantine record with an
explicit rejection reason -- nothing is dropped silently.
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class ParseResult:
    rows: list[dict] = field(default_factory=list)
    rejects: list[dict] = field(default_factory=list)  # {"reason":..., "raw_row":...}


def parse_minutes(value) -> float | None:
    """NBA MIN can be 'MM:SS', an int, a float, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    if ":" in text:
        mm, ss = text.split(":", 1)
        return round(int(mm) + int(ss) / 60.0, 2)
    return float(text)


def parse_game_date(value) -> date:
    text = str(value)
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized game date: {value!r}")


def _headers_index(payload: dict) -> tuple[dict, list]:
    result_set = payload["resultSets"][0]
    idx = {h: i for i, h in enumerate(result_set["headers"])}
    return idx, result_set["rowSet"]


def _int_or_none(value):
    return None if value is None else int(value)


def parse_player_game_log(payload: dict) -> ParseResult:
    """Player-level rows -> stg_player_game dicts (plus rejects)."""
    idx, row_set = _headers_index(payload)
    result = ParseResult()
    for raw in row_set:
        try:
            player_id = raw[idx["PLAYER_ID"]]
            game_id = raw[idx["GAME_ID"]]
            if player_id in (None, "") or game_id in (None, ""):
                raise ValueError("missing PLAYER_ID or GAME_ID")
            points = _int_or_none(raw[idx["PTS"]])
            if points is not None and points < 0:
                raise ValueError(f"negative points: {points}")
            result.rows.append(
                {
                    "game_id": str(game_id),
                    "player_id": int(player_id),
                    "player_name": raw[idx["PLAYER_NAME"]],
                    "team_id": int(raw[idx["TEAM_ID"]]),
                    "team_abbreviation": raw[idx["TEAM_ABBREVIATION"]],
                    "team_name": raw[idx["TEAM_NAME"]],
                    "game_date": parse_game_date(raw[idx["GAME_DATE"]]),
                    "minutes": parse_minutes(raw[idx["MIN"]]),
                    "points": points,
                    "fgm": _int_or_none(raw[idx["FGM"]]),
                    "fga": _int_or_none(raw[idx["FGA"]]),
                    "fg3m": _int_or_none(raw[idx["FG3M"]]),
                    "fg3a": _int_or_none(raw[idx["FG3A"]]),
                    "ftm": _int_or_none(raw[idx["FTM"]]),
                    "fta": _int_or_none(raw[idx["FTA"]]),
                    "oreb": _int_or_none(raw[idx["OREB"]]),
                    "dreb": _int_or_none(raw[idx["DREB"]]),
                    "reb": _int_or_none(raw[idx["REB"]]),
                    "ast": _int_or_none(raw[idx["AST"]]),
                    "stl": _int_or_none(raw[idx["STL"]]),
                    "blk": _int_or_none(raw[idx["BLK"]]),
                    "tov": _int_or_none(raw[idx["TOV"]]),
                    "pf": _int_or_none(raw[idx["PF"]]),
                    "plus_minus": (
                        None
                        if raw[idx["PLUS_MINUS"]] is None
                        else float(raw[idx["PLUS_MINUS"]])
                    ),
                }
            )
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            result.rejects.append({"reason": str(exc), "raw_row": json.dumps(raw)})
    return result


def parse_team_game_log(payload: dict) -> ParseResult:
    """Team-level rows -> stg_team_game dicts (plus rejects)."""
    idx, row_set = _headers_index(payload)
    result = ParseResult()
    for raw in row_set:
        try:
            game_id = raw[idx["GAME_ID"]]
            team_id = raw[idx["TEAM_ID"]]
            if game_id in (None, "") or team_id in (None, ""):
                raise ValueError("missing GAME_ID or TEAM_ID")
            matchup = str(raw[idx["MATCHUP"]])
            is_home = 1 if "vs." in matchup else 0
            win_loss = raw[idx["WL"]]
            result.rows.append(
                {
                    "game_id": str(game_id),
                    "team_id": int(team_id),
                    "team_abbreviation": raw[idx["TEAM_ABBREVIATION"]],
                    "team_name": raw[idx["TEAM_NAME"]],
                    "season_id": str(raw[idx["SEASON_ID"]]),
                    "game_date": parse_game_date(raw[idx["GAME_DATE"]]),
                    "is_home": is_home,
                    "win": None if win_loss is None else (1 if win_loss == "W" else 0),
                    "points": _int_or_none(raw[idx["PTS"]]),
                    "fgm": _int_or_none(raw[idx["FGM"]]),
                    "fga": _int_or_none(raw[idx["FGA"]]),
                    "fg3m": _int_or_none(raw[idx["FG3M"]]),
                    "fg3a": _int_or_none(raw[idx["FG3A"]]),
                    "ftm": _int_or_none(raw[idx["FTM"]]),
                    "fta": _int_or_none(raw[idx["FTA"]]),
                    "oreb": _int_or_none(raw[idx["OREB"]]),
                    "dreb": _int_or_none(raw[idx["DREB"]]),
                    "reb": _int_or_none(raw[idx["REB"]]),
                    "ast": _int_or_none(raw[idx["AST"]]),
                    "stl": _int_or_none(raw[idx["STL"]]),
                    "blk": _int_or_none(raw[idx["BLK"]]),
                    "tov": _int_or_none(raw[idx["TOV"]]),
                    "pf": _int_or_none(raw[idx["PF"]]),
                    "plus_minus": (
                        None
                        if raw[idx["PLUS_MINUS"]] is None
                        else float(raw[idx["PLUS_MINUS"]])
                    ),
                }
            )
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            result.rejects.append({"reason": str(exc), "raw_row": json.dumps(raw)})
    return result


def derive_games(team_rows: list[dict], season: str) -> list[dict]:
    """Combine the two team rows per game into one stg_game row."""
    by_game: dict[str, list[dict]] = {}
    for row in team_rows:
        by_game.setdefault(row["game_id"], []).append(row)
    games = []
    for game_id, rows in by_game.items():
        home = next((r for r in rows if r["is_home"] == 1), None)
        away = next((r for r in rows if r["is_home"] == 0), None)
        is_neutral = 0
        if home is None or away is None:
            if len(rows) != 2:
                # Incomplete pair; reconciliation will flag it.
                continue
            # Neutral-site game (e.g. NBA Europe): the source marks both teams
            # as away ("X @ Y" on both rows). Assign home/away slots
            # deterministically by team_id so replays stay idempotent.
            away, home = sorted(rows, key=lambda r: r["team_id"])
            is_neutral = 1
        games.append(
            {
                "game_id": game_id,
                "season": season,
                "game_date": home["game_date"],
                "home_team_id": home["team_id"],
                "away_team_id": away["team_id"],
                "home_points": home["points"],
                "away_points": away["points"],
                "is_neutral": is_neutral,
            }
        )
    return games
