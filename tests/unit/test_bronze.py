import json

from nba_warehouse.bronze.writer import (
    latest_bronze_file,
    read_manifest,
    sha256_of_text,
    write_bronze,
)
from tests.conftest import load_fixture, make_settings


def test_sha256_is_deterministic():
    assert sha256_of_text("abc") == sha256_of_text("abc")
    assert sha256_of_text("abc") != sha256_of_text("abd")


def test_write_bronze_creates_file_and_manifest(tmp_path):
    settings = make_settings(tmp_path)
    payload = load_fixture("player_gamelog", "2026-01-10")

    path = write_bronze(settings, payload, "leaguegamelog_player", "2026-01-10")
    assert path.exists()

    entries = read_manifest(settings)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["record_count"] == 4
    assert entry["endpoint"] == "leaguegamelog_player"
    # Checksum in manifest matches the file on disk
    assert entry["sha256"] == sha256_of_text(path.read_text(encoding="utf-8"))
    # Round-trip: bronze file is valid JSON with the same rows
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert len(reloaded["resultSets"][0]["rowSet"]) == 4


def test_latest_bronze_file_picks_newest(tmp_path):
    settings = make_settings(tmp_path)
    payload = load_fixture("player_gamelog", "2026-01-10")
    write_bronze(settings, payload, "leaguegamelog_player", "2026-01-10")
    second = write_bronze(settings, payload, "leaguegamelog_player", "2026-01-10")
    assert latest_bronze_file(settings, "leaguegamelog_player", "2026-01-10") == second
    assert latest_bronze_file(settings, "leaguegamelog_player", "2026-01-11") is None
