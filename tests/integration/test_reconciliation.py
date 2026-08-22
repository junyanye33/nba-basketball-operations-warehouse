"""Bronze-vs-silver reconciliation: every raw row must be loaded or quarantined."""
import json

from nba_warehouse.quality.reconciliation import reconcile_date


def test_reconciliation_passes_for_clean_date(pipeline_env):
    report = reconcile_date(pipeline_env, "2026-01-10")
    assert report["status"] == "pass"
    assert report["silver"]["rejected"] == 0
    assert report["silver"]["player_games"] == 4


def test_reconciliation_accounts_for_quarantined_rows(pipeline_env):
    # 2026-01-12 has 5 bronze player rows: 4 loaded + 1 quarantined
    report = reconcile_date(pipeline_env, "2026-01-12")
    assert report["status"] == "pass"
    assert report["bronze"]["player_rows"] == 5
    assert report["silver"]["player_games"] == 4
    assert report["silver"]["rejected"] == 1

    report_file = pipeline_env.reports_dir / "reconciliation_2026-01-12.json"
    assert report_file.exists()
    saved = json.loads(report_file.read_text(encoding="utf-8"))
    assert saved["status"] == "pass"
