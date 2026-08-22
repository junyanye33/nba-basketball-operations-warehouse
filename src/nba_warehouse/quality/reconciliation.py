"""Bronze-vs-silver reconciliation.

For a logical date, compares raw record counts (from the bronze manifest)
against silver row counts + quarantined rows, and writes a JSON quality report.
An unexplained gap means data was lost between layers -> report status 'fail'.
"""
import json
from datetime import datetime, timezone

from nba_warehouse.bronze.writer import read_manifest
from nba_warehouse.config import Settings
from nba_warehouse.silver.loader import get_engine, silver_counts


def reconcile_date(settings: Settings, logical_date: str) -> dict:
    manifest = read_manifest(settings)

    def latest_count(endpoint: str) -> int | None:
        entries = [
            e
            for e in manifest
            if e["game_date"] == logical_date and e["endpoint"] == endpoint
        ]
        if not entries:
            return None
        return sorted(entries, key=lambda e: e["ingested_at_utc"])[-1]["record_count"]

    bronze_players = latest_count("leaguegamelog_player")
    bronze_teams = latest_count("leaguegamelog_team")

    engine = get_engine(settings.database_url)
    silver = silver_counts(engine, logical_date)

    checks = []

    def add_check(name: str, expected, actual):
        passed = expected is not None and expected == actual
        checks.append(
            {"check": name, "expected": expected, "actual": actual, "passed": passed}
        )

    add_check(
        "player_rows_accounted_for",
        bronze_players,
        silver["player_games"] + silver["rejected"],
    )
    add_check("team_rows_accounted_for", bronze_teams, silver["team_games"])
    add_check("two_team_rows_per_game", silver["games"] * 2, silver["team_games"])

    report = {
        "logical_date": logical_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bronze": {"player_rows": bronze_players, "team_rows": bronze_teams},
        "silver": silver,
        "checks": checks,
        "status": "pass" if all(c["passed"] for c in checks) else "fail",
    }

    report_path = settings.reports_dir / f"reconciliation_{logical_date}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
