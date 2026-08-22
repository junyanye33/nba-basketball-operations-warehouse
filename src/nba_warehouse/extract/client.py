"""Thin NBA Stats API client with retry/backoff.

stats.nba.com fingerprints TLS handshakes and stalls plain `requests` clients,
so we use curl_cffi with Chrome impersonation. Only used in live mode; smoke
mode and tests never hit the network -- they use recorded fixtures instead.
"""
import os
import time

from curl_cffi import requests as curl_requests

BASE_URL = "https://stats.nba.com/stats"

HEADERS = {
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Accept": "application/json",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

TIMEOUT = int(os.getenv("NBA_API_TIMEOUT_SECONDS", "30"))
MAX_RETRIES = 4


class NbaApiError(RuntimeError):
    pass


def get_json(endpoint: str, params: dict) -> dict:
    """GET an NBA Stats endpoint with exponential backoff."""
    url = f"{BASE_URL}/{endpoint}"
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = curl_requests.get(
                url,
                params=params,
                headers=HEADERS,
                impersonate="chrome",
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            last_err = NbaApiError(f"{endpoint} returned HTTP {resp.status_code}")
        except curl_requests.exceptions.RequestException as exc:
            last_err = exc
        time.sleep(2**attempt)
    raise NbaApiError(f"Failed after {MAX_RETRIES} attempts: {last_err}")


def _league_game_log_params(
    season: str, level: str, date_from: str = "", date_to: str = ""
) -> dict:
    if level not in ("P", "T"):
        raise ValueError("level must be 'P' or 'T'")
    return {
        "Season": season,
        "SeasonType": "Regular Season",
        "PlayerOrTeam": level,
        "DateFrom": date_from,
        "DateTo": date_to,
        "LeagueID": "00",
        "Sorter": "DATE",
        "Direction": "ASC",
        "Counter": "0",
    }


def fetch_league_game_log(season: str, game_date: str, level: str) -> dict:
    """Fetch league-wide player or team game logs for one ISO date."""
    year, month, day = game_date.split("-")
    api_date = f"{month}/{day}/{year}"
    return get_json(
        "leaguegamelog",
        _league_game_log_params(season, level, api_date, api_date),
    )


def fetch_full_season_game_log(season: str, level: str) -> dict:
    """Fetch all regular-season game logs in one request."""
    return get_json(
        "leaguegamelog",
        _league_game_log_params(season, level),
    )
