"""Bronze layer: immutable raw JSON snapshots + manifest with checksums.

Layout:
    bronze/season=<season>/endpoint=<endpoint>/game_date=<date>/snapshot-<ts>.json
Manifest (JSONL, append-only):
    metadata/manifest.jsonl
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from nba_warehouse.config import Settings


def sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record_count(payload: dict) -> int:
    try:
        return sum(len(rs.get("rowSet", [])) for rs in payload.get("resultSets", []))
    except (TypeError, AttributeError):
        return 0


def write_bronze(
    settings: Settings, payload: dict, endpoint: str, game_date: str
) -> Path:
    """Persist a raw API payload and append a manifest entry. Returns file path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target_dir = (
        settings.bronze_dir
        / f"season={settings.season}"
        / f"endpoint={endpoint}"
        / f"game_date={game_date}"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"snapshot-{ts}.json"
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    path.write_text(text, encoding="utf-8")

    manifest_entry = {
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": settings.season,
        "endpoint": endpoint,
        "game_date": game_date,
        "file": str(path.relative_to(settings.bronze_dir).as_posix()),
        "sha256": sha256_of_text(text),
        "bytes": len(text.encode("utf-8")),
        "record_count": _record_count(payload),
    }
    manifest_path = settings.metadata_dir / "manifest.jsonl"
    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest_entry) + "\n")
    return path


def latest_bronze_file(settings: Settings, endpoint: str, game_date: str) -> Path | None:
    """Latest snapshot for an endpoint/date, or None if never ingested."""
    target_dir = (
        settings.bronze_dir
        / f"season={settings.season}"
        / f"endpoint={endpoint}"
        / f"game_date={game_date}"
    )
    if not target_dir.exists():
        return None
    files = sorted(target_dir.glob("snapshot-*.json"))
    return files[-1] if files else None


def read_manifest(settings: Settings) -> list[dict]:
    manifest_path = settings.metadata_dir / "manifest.jsonl"
    if not manifest_path.exists():
        return []
    entries = []
    with manifest_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
