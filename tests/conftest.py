import json
from pathlib import Path

import pytest

from nba_warehouse.bronze.writer import write_bronze
from nba_warehouse.config import Settings
from nba_warehouse.gold.build import build_gold
from nba_warehouse.pipeline import ENDPOINT_PLAYER, ENDPOINT_TEAM, load_date
from nba_warehouse.silver.loader import init_db

FIXTURES = Path(__file__).parent / "fixtures"
DATES = ["2026-01-10", "2026-01-12"]


def make_settings(base: Path) -> Settings:
    settings = Settings(
        database_url=f"sqlite:///{(base / 'silver.db').as_posix()}",
        duckdb_path=base / "gold.duckdb",
        bronze_dir=base / "bronze",
        metadata_dir=base / "metadata",
        reports_dir=base / "reports",
    )
    settings.ensure_dirs()
    return settings


def load_fixture(prefix: str, logical_date: str) -> dict:
    path = FIXTURES / f"{prefix}_{logical_date}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_full_pipeline(settings: Settings) -> Settings:
    init_db(settings.database_url)
    for logical_date in DATES:
        for endpoint, prefix in (
            (ENDPOINT_PLAYER, "player_gamelog"),
            (ENDPOINT_TEAM, "team_gamelog"),
        ):
            write_bronze(settings, load_fixture(prefix, logical_date), endpoint, logical_date)
        load_date(settings, logical_date)
    build_gold(settings)
    return settings


@pytest.fixture(scope="session")
def pipeline_env(tmp_path_factory) -> Settings:
    base = tmp_path_factory.mktemp("warehouse")
    return run_full_pipeline(make_settings(base))
