"""Command-line entry points.

    python -m nba_warehouse.cli smoke                     # offline end-to-end demo
    python -m nba_warehouse.cli init-db
    python -m nba_warehouse.cli run-date --date 2026-01-10
    python -m nba_warehouse.cli replay --start-date ... --end-date ...
    python -m nba_warehouse.cli reconcile --date 2026-01-10
"""
import argparse
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

from nba_warehouse.bronze.writer import write_bronze
from nba_warehouse.config import PROJECT_ROOT, get_settings
from nba_warehouse.pipeline import (
    ENDPOINT_PLAYER,
    ENDPOINT_TEAM,
    load_date,
    run_date,
    run_full_season,
)
from nba_warehouse.gold.build import build_gold
from nba_warehouse.quality.reconciliation import reconcile_date
from nba_warehouse.silver.loader import init_db

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
SMOKE_DATES = ["2026-01-10", "2026-01-12"]


def _daterange(start: str, end: str):
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    current = d0
    while current <= d1:
        yield current.isoformat()
        current += timedelta(days=1)


def cmd_smoke(_args) -> None:
    """Offline end-to-end run against recorded fixtures (no network, no Postgres)."""
    smoke_base = PROJECT_ROOT / "data" / "smoke"
    if smoke_base.exists():
        shutil.rmtree(smoke_base)
    settings = get_settings(smoke=True)
    init_db(settings.database_url)

    for logical_date in SMOKE_DATES:
        for endpoint, prefix in (
            (ENDPOINT_PLAYER, "player_gamelog"),
            (ENDPOINT_TEAM, "team_gamelog"),
        ):
            fixture = FIXTURES_DIR / f"{prefix}_{logical_date}.json"
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            write_bronze(settings, payload, endpoint, logical_date)
        stats = load_date(settings, logical_date)
        print(f"[smoke] silver load {logical_date}: {stats}")

    gold_stats = build_gold(settings)
    print(f"[smoke] gold marts: {gold_stats}")

    for logical_date in SMOKE_DATES:
        report = reconcile_date(settings, logical_date)
        print(f"[smoke] reconciliation {logical_date}: {report['status']}")

    print(f"[smoke] done. Reports in {settings.reports_dir}")


def cmd_init_db(args) -> None:
    settings = get_settings(smoke=args.smoke)
    init_db(settings.database_url)
    print(f"Initialized schema at {settings.database_url}")


def cmd_run_date(args) -> None:
    settings = get_settings(smoke=args.smoke)
    result = run_date(settings, args.date, skip_ingest=args.skip_ingest)
    print(json.dumps(result, indent=2, default=str))


def cmd_replay(args) -> None:
    settings = get_settings(smoke=args.smoke)
    for logical_date in _daterange(args.start_date, args.end_date):
        result = run_date(settings, logical_date, skip_ingest=args.skip_ingest)
        print(json.dumps(result, default=str))


def cmd_reconcile(args) -> None:
    settings = get_settings(smoke=args.smoke)
    report = reconcile_date(settings, args.date)
    print(json.dumps(report, indent=2))


def cmd_run_season(args) -> None:
    settings = get_settings(smoke=False)
    result = run_full_season(settings, skip_ingest=args.skip_ingest)
    print(json.dumps(result, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(prog="nba-warehouse")
    sub = parser.add_subparsers(dest="command", required=True)

    p_smoke = sub.add_parser("smoke", help="offline end-to-end demo on fixtures")
    p_smoke.set_defaults(func=cmd_smoke)

    p_init = sub.add_parser("init-db", help="create silver schema")
    p_init.add_argument("--smoke", action="store_true")
    p_init.set_defaults(func=cmd_init_db)

    p_run = sub.add_parser("run-date", help="ingest+load+transform+reconcile one date")
    p_run.add_argument("--date", required=True)
    p_run.add_argument("--smoke", action="store_true")
    p_run.add_argument(
        "--skip-ingest", action="store_true", help="replay from existing bronze"
    )
    p_run.set_defaults(func=cmd_run_date)

    p_replay = sub.add_parser("replay", help="run a date range (backfill)")
    p_replay.add_argument("--start-date", required=True)
    p_replay.add_argument("--end-date", required=True)
    p_replay.add_argument("--smoke", action="store_true")
    p_replay.add_argument("--skip-ingest", action="store_true")
    p_replay.set_defaults(func=cmd_replay)

    p_rec = sub.add_parser("reconcile", help="bronze-vs-silver reconciliation report")
    p_rec.add_argument("--date", required=True)
    p_rec.add_argument("--smoke", action="store_true")
    p_rec.set_defaults(func=cmd_reconcile)

    p_season = sub.add_parser(
        "run-season",
        help="ingest, load, reconcile, and build the full regular season",
    )
    p_season.add_argument(
        "--skip-ingest",
        action="store_true",
        help="rebuild from existing daily bronze snapshots",
    )
    p_season.set_defaults(func=cmd_run_season)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
