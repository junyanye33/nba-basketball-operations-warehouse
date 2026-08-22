"""Central configuration. Live mode targets PostgreSQL + project data dirs;
smoke mode is fully local (SQLite + DuckDB) so anyone can run it with zero setup."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

SEASON = "2025-26"


@dataclass
class Settings:
    database_url: str
    duckdb_path: Path
    bronze_dir: Path
    metadata_dir: Path
    reports_dir: Path
    season: str = SEASON

    def ensure_dirs(self) -> None:
        for d in (self.bronze_dir, self.metadata_dir, self.reports_dir, self.duckdb_path.parent):
            d.mkdir(parents=True, exist_ok=True)


def get_settings(smoke: bool = False) -> Settings:
    if smoke:
        base = PROJECT_ROOT / "data" / "smoke"
        settings = Settings(
            database_url=os.getenv(
                "SMOKE_DATABASE_URL", f"sqlite:///{(base / 'silver.db').as_posix()}"
            ),
            duckdb_path=base / "gold.duckdb",
            bronze_dir=base / "bronze",
            metadata_dir=base / "metadata",
            reports_dir=base / "reports",
        )
    else:
        base = PROJECT_ROOT / "data"
        settings = Settings(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg2://nba:nba@localhost:5432/nba_warehouse",
            ),
            duckdb_path=base / "gold" / "gold.duckdb",
            bronze_dir=base / "bronze",
            metadata_dir=base / "metadata",
            reports_dir=base / "reports",
        )
    settings.ensure_dirs()
    return settings
