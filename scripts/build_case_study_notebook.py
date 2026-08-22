"""Create, execute, and export the Project 1 case study notebook.

The generated notebook keeps code and outputs together for GitHub review.
The exported classic HTML is the detailed GitHub Pages project view.

Run from the repository root:
    python scripts/build_case_study_notebook.py
"""
from pathlib import Path

import nbformat
from nbconvert import HTMLExporter
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"
NOTEBOOK_PATH = NOTEBOOK_DIR / "nba_basketball_operations_warehouse.ipynb"
HTML_PATH = ROOT / "docs" / "project.html"
NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)


def markdown(source: str):
    return nbformat.v4.new_markdown_cell(source.strip())


def code(source: str):
    return nbformat.v4.new_code_cell(source.strip())


cells = [
    markdown(
        """
# NBA Basketball Operations Warehouse

## Complete 2025 to 2026 Regular Season Case Study

This notebook documents a production style data engineering project built from
official NBA game logs. It combines the business question, executable SQL,
data quality evidence, analytical outputs, and engineering decisions in one
reviewable artifact.

**Business question:** Which players and teams sustained strong form, and how
did rest advantage relate to winning?
"""
    ),
    markdown(
        """
## Executive Summary

The warehouse covers all **1,230 regular season games** from October 21, 2025
through April 12, 2026. It contains **26,651 player game records** and **2,460
team game records**. All **164 game dates** passed reconciliation.

The clearest basketball operations result is the relationship between relative
rest and game outcome:

* Teams with at least two extra rest days won **57.4 percent** of games.
* Teams with at least two fewer rest days won **42.6 percent** of games.
* Equal rest produced an exact **50 percent** split.

This is descriptive evidence rather than a causal claim. Team quality, travel,
injuries, and planned rest may also influence outcomes.
"""
    ),
    markdown("## Environment and Data Connection"),
    code(
        """
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from IPython.display import display

ROOT = Path.cwd()
GOLD = ROOT / "data" / "gold" / "gold.duckdb"
MANIFEST = ROOT / "data" / "metadata" / "manifest.jsonl"

con = duckdb.connect(str(GOLD), read_only=True)

NAVY = "#132238"
BLUE = "#286DA8"
ORANGE = "#E8752E"
GREEN = "#39805B"
RED = "#B74D45"
SLATE = "#607086"
LIGHT = "#E8EDF3"

plt.rcParams.update({
    "figure.figsize": (11, 5.5),
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": LIGHT,
    "axes.labelcolor": SLATE,
    "axes.titlecolor": NAVY,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": LIGHT,
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "text.color": NAVY,
    "xtick.color": SLATE,
    "ytick.color": SLATE,
})

print(f"Connected to {GOLD.name}")
"""
    ),
    markdown(
        """
## Data Coverage

The Gold layer provides analysis ready facts and marts. This first query
confirms the dataset grain and season boundaries before any analysis begins.
"""
    ),
    code(
        """
coverage = con.sql(
    '''
    SELECT
        (SELECT COUNT(*) FROM dim_game) AS games,
        (SELECT COUNT(*) FROM fact_team_game) AS team_game_rows,
        (SELECT COUNT(*) FROM fact_player_game) AS player_game_rows,
        (SELECT COUNT(DISTINCT player_id) FROM fact_player_game) AS players,
        (SELECT COUNT(DISTINCT game_date) FROM dim_game) AS game_dates,
        MIN(game_date) AS first_game_date,
        MAX(game_date) AS last_game_date
    FROM dim_game
    '''
).df()

display(coverage)
"""
    ),
    markdown(
        """
## Pipeline Architecture

The system uses a Bronze, Silver, and Gold design.

| Layer | Responsibility |
| --- | --- |
| Source | NBA Stats API with retry logic and Chrome TLS impersonation |
| Bronze | Immutable daily JSON snapshots with checksums and row counts |
| Silver | Typed relational tables, natural key upserts, quarantine, and run audit |
| Gold | Columnar facts and leakage safe analytical marts in DuckDB |
| Quality | Daily row accounting and game grain reconciliation |

The season backfill uses only two source requests. Player and team responses
are partitioned into daily Bronze snapshots so historical loading remains
efficient without sacrificing daily lineage.
"""
    ),
    markdown("### Bronze Manifest Evidence"),
    code(
        """
manifest = pd.read_json(MANIFEST, lines=True)
latest_manifest = (
    manifest.sort_values("ingested_at_utc")
    .drop_duplicates(["game_date", "endpoint"], keep="last")
    .sort_values(["game_date", "endpoint"])
)

display(
    latest_manifest[
        ["game_date", "endpoint", "record_count", "bytes", "sha256"]
    ].head(8)
)

print(
    f"{len(latest_manifest):,} latest daily endpoint snapshots "
    f"cover {latest_manifest['game_date'].nunique()} game dates."
)
"""
    ),
    markdown(
        """
## Data Quality and Reconciliation

Every game date must satisfy three contracts:

1. Player rows in Bronze equal loaded player rows plus quarantined rows.
2. Team rows in Bronze equal loaded team rows.
3. Every game has exactly two team rows.

The Gold completeness mart provides the final game grain check.
"""
    ),
    code(
        """
daily_quality = con.sql(
    '''
    SELECT
        game_date,
        games,
        team_game_rows,
        expected_team_game_rows,
        status
    FROM mart_data_completeness
    ORDER BY game_date
    '''
).df()

quality_summary = pd.DataFrame({
    "check": [
        "Game dates loaded",
        "Complete game dates",
        "Incomplete game dates",
        "Games loaded",
        "Expected team game rows",
        "Actual team game rows",
    ],
    "result": [
        len(daily_quality),
        (daily_quality["status"] == "complete").sum(),
        (daily_quality["status"] != "complete").sum(),
        daily_quality["games"].sum(),
        daily_quality["expected_team_game_rows"].sum(),
        daily_quality["team_game_rows"].sum(),
    ],
})

assert (daily_quality["status"] == "complete").all()
assert (
    daily_quality["team_game_rows"]
    == daily_quality["expected_team_game_rows"]
).all()

display(quality_summary)
print("PASS: all game dates satisfy the Gold completeness contract.")
"""
    ),
    markdown(
        """
## Analysis 1: Season Scoring Leaders

The appearance threshold matters. A scoring average based on a small number of
games does not represent season long production, so this report requires at
least 55 appearances.
"""
    ),
    code(
        """
scoring_leaders = con.sql(
    '''
    SELECT
        p.player_name,
        t.team_abbreviation AS team,
        COUNT(*) AS games,
        ROUND(AVG(f.points), 1) AS points_per_game,
        SUM(f.points) AS total_points
    FROM fact_player_game f
    JOIN dim_player p USING (player_id)
    JOIN dim_team t ON t.team_id = f.team_id
    GROUP BY 1, 2
    HAVING COUNT(*) >= 55
    ORDER BY points_per_game DESC
    LIMIT 12
    '''
).df()

display(scoring_leaders)

plot = scoring_leaders.iloc[::-1]
fig, ax = plt.subplots(figsize=(11, 6.2))
y = np.arange(len(plot))
ax.hlines(y, 0, plot["points_per_game"], color=LIGHT, linewidth=5)
ax.scatter(plot["points_per_game"], y, s=120, color=ORANGE, zorder=3)

for index, value in enumerate(plot["points_per_game"]):
    ax.text(value + 0.25, index, f"{value:.1f}", va="center", fontweight="bold")

ax.set_yticks(y)
ax.set_yticklabels(
    [
        f"{name}  ·  {team}"
        for name, team in zip(plot["player_name"], plot["team"])
    ]
)
ax.set_xlabel("Points per game")
ax.set_xlim(0, plot["points_per_game"].max() + 3)
ax.set_title("Season scoring leaders", loc="left", pad=14)
ax.grid(axis="y", visible=False)
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)
plt.show()
"""
    ),
    markdown(
        """
## Analysis 2: Rest Advantage Compared With the Opponent

Using a team's rest alone can be misleading because the opponent may have the
same schedule. This query pairs both teams from the same game and calculates
the rest difference directly.
"""
    ),
    code(
        """
rest_advantage = con.sql(
    '''
    WITH paired AS (
        SELECT
            a.game_id,
            a.team_id,
            a.win,
            a.days_rest - b.days_rest AS rest_edge
        FROM mart_team_schedule_context a
        JOIN mart_team_schedule_context b
          ON a.game_id = b.game_id
         AND a.team_id <> b.team_id
        WHERE a.days_rest IS NOT NULL
          AND b.days_rest IS NOT NULL
    )
    SELECT
        CASE
            WHEN rest_edge <= -2 THEN '2+ fewer days'
            WHEN rest_edge = -1 THEN '1 fewer day'
            WHEN rest_edge = 0 THEN 'Equal rest'
            WHEN rest_edge = 1 THEN '1 extra day'
            ELSE '2+ extra days'
        END AS rest_advantage,
        ROUND(AVG(win) * 100, 1) AS win_rate,
        COUNT(*) AS team_games,
        MIN(rest_edge) AS sort_key
    FROM paired
    GROUP BY 1
    ORDER BY sort_key
    '''
).df()

display(rest_advantage.drop(columns="sort_key"))

fig, ax = plt.subplots(figsize=(11, 5.4))
colors = [RED, "#D98A70", SLATE, "#72A58A", GREEN]
bars = ax.barh(
    rest_advantage["rest_advantage"],
    rest_advantage["win_rate"],
    color=colors,
)
ax.axvline(50, color=NAVY, linestyle=(0, (3, 3)), linewidth=1.2)

for bar, win_rate, sample in zip(
    bars, rest_advantage["win_rate"], rest_advantage["team_games"]
):
    ax.text(
        win_rate + 0.5,
        bar.get_y() + bar.get_height() / 2,
        f"{win_rate:.1f}%   n={sample:,}",
        va="center",
        fontweight="bold",
    )

ax.set_xlim(0, 65)
ax.set_xlabel("Win rate")
ax.set_title("Win rate by rest advantage", loc="left", pad=14)
ax.grid(axis="y", visible=False)
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)
plt.show()
"""
    ),
    markdown(
        """
### Business Interpretation

The difference between the two extreme buckets is **14.9 percentage points**.
This supports using relative rest as a scouting and scheduling context feature.
It should not be interpreted as proof that rest alone caused the result.
"""
    ),
    markdown(
        """
## Analysis 3: Leakage Safe Player Form

The rolling form mart stops at the game immediately before the current row:

```sql
ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
```

That boundary prevents the current game's result from leaking into a feature
that is supposed to represent information available before tipoff.
"""
    ),
    code(
        """
player_form = con.sql(
    '''
    WITH eligible AS (
        SELECT player_id
        FROM fact_player_game
        GROUP BY player_id
        HAVING COUNT(*) >= 55
        ORDER BY AVG(points) DESC
        LIMIT 5
    )
    SELECT
        f.game_date,
        p.player_name,
        f.avg_points_prior_10 AS prior_10_game_average
    FROM mart_player_form f
    JOIN eligible e USING (player_id)
    JOIN dim_player p USING (player_id)
    WHERE f.games_prior_10 = 10
    ORDER BY f.game_date
    '''
).df()

fig, ax = plt.subplots(figsize=(11, 5.8))
colors = [ORANGE, BLUE, GREEN, RED, "#7A5AA6"]

for color, (player, group) in zip(colors, player_form.groupby("player_name")):
    ax.plot(
        group["game_date"],
        group["prior_10_game_average"],
        label=player,
        color=color,
        linewidth=2.1,
    )

ax.set_ylabel("Prior 10 game scoring average")
ax.set_xlabel("Regular season date")
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
ax.set_title("How elite scoring form changed through the season", loc="left", pad=14)
ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14))
ax.grid(axis="x", visible=False)
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
plt.show()
"""
    ),
    markdown(
        """
## Analysis 4: Team Wins and Point Differential

Win totals describe outcomes. Average point differential adds context about how
consistently a team controlled games throughout the season.
"""
    ),
    code(
        """
team_performance = con.sql(
    '''
    SELECT
        t.team_abbreviation AS team,
        SUM(f.win) AS wins,
        ROUND(AVG(f.plus_minus), 1) AS average_point_differential
    FROM fact_team_game f
    JOIN dim_team t USING (team_id)
    GROUP BY 1
    ORDER BY wins DESC
    '''
).df()

display(team_performance.head(10))

fig, ax = plt.subplots(figsize=(11, 6.2))
point_colors = np.where(
    team_performance["average_point_differential"] >= 0, BLUE, SLATE
)
ax.scatter(
    team_performance["wins"],
    team_performance["average_point_differential"],
    s=75,
    color=point_colors,
)

for _, row in team_performance.iterrows():
    ax.annotate(
        row["team"],
        (row["wins"], row["average_point_differential"]),
        xytext=(4, 4),
        textcoords="offset points",
        fontsize=8.5,
    )

ax.axhline(0, color=LIGHT, linewidth=1.3)
ax.axvline(team_performance["wins"].median(), color=LIGHT, linewidth=1.3)
ax.set_xlabel("Regular season wins")
ax.set_ylabel("Average point differential per game")
ax.set_title("Team results and sustainable scoring margin", loc="left", pad=14)
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
plt.show()
"""
    ),
    markdown(
        """
## Engineering Evidence

### Idempotent Loading

Silver facts use natural keys such as `(game_id, player_id)` and
`(game_id, team_id)`. Replaying a date updates existing records rather than
creating duplicates. The integration suite verifies unchanged row counts after
replay, including quarantined records.

### Version Controlled Schema Change

Daily reconciliation exposed a real source edge case during the NBA Berlin
game. Both teams were marked as away at the neutral venue, so the original
home and away derivation produced an incomplete game. The fix added
deterministic slot assignment and an `is_neutral` field through Alembic
migration `0002`.

### Observable Failure Handling

Invalid records are never silently discarded. They enter `rejected_record`
with the raw row, endpoint, reason, logical date, and run identifier. Pipeline
runs record loaded and rejected counts for operational review.
"""
    ),
    markdown(
        """
## Conclusion

This project demonstrates more than a successful API pull. It provides a
replayable and testable data product with complete season coverage, explicit
data contracts, trustworthy analytical marts, and visible business results.

The notebook is the analytical deliverable. The repository contains the
pipeline implementation, migrations, automated tests, CI workflow, runbook,
and reproducible notebook build script.
"""
    ),
]

notebook = nbformat.v4.new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    },
)

nbformat.write(notebook, NOTEBOOK_PATH)

executor = ExecutePreprocessor(timeout=240, kernel_name="python3")
executor.preprocess(notebook, {"metadata": {"path": str(ROOT)}})
nbformat.write(notebook, NOTEBOOK_PATH)

exporter = HTMLExporter(template_name="classic")
exporter.exclude_input_prompt = False
exporter.exclude_output_prompt = False
html, _ = exporter.from_notebook_node(notebook)

custom_style = """
<style>
  :root {
    --ink: #132238;
    --muted: #607086;
    --blue: #286da8;
    --orange: #e8752e;
    --line: #dfe5ec;
  }
  body {
    color: var(--ink);
    background: #ffffff;
  }
  .portfolio-nav {
    min-height: 58px;
    padding: 0 28px;
    border-bottom: 1px solid var(--line);
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .portfolio-nav a {
    color: var(--ink);
    font-weight: 700;
    text-decoration: none;
  }
  .portfolio-nav .links {
    display: flex;
    gap: 22px;
    font-size: 13px;
  }
  #notebook-container {
    max-width: 1120px;
    padding: 45px 55px 70px;
    box-shadow: none;
  }
  div.input_prompt, div.output_prompt {
    color: var(--blue);
  }
  div.input_area {
    border: 1px solid var(--line);
    border-radius: 0;
    background: #f7f9fb;
  }
  .rendered_html h1, .rendered_html h2, .rendered_html h3 {
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .rendered_html h1 {
    margin-top: 0.5em;
    font-size: 2.5em;
    letter-spacing: -0.035em;
  }
  .rendered_html h2 {
    margin-top: 2.2em;
    padding-bottom: 0.35em;
    border-bottom: 1px solid var(--line);
  }
  .rendered_html p, .rendered_html li {
    color: #34445a;
    font-size: 15px;
    line-height: 1.7;
  }
  .rendered_html table {
    width: 100%;
  }
  .rendered_html th {
    background: #f3f6f9;
  }
  div.output_subarea {
    max-width: 100%;
  }
  @media (max-width: 720px) {
    .portfolio-nav {
      padding: 0 14px;
    }
    .portfolio-nav .links a:first-child {
      display: none;
    }
    #notebook-container {
      padding: 28px 16px 55px;
    }
    div.input_prompt, div.output_prompt {
      min-width: 55px;
    }
  }
</style>
"""

navigation = """
<div class="portfolio-nav">
  <a href="index.html">Junyan Ye</a>
  <div class="links">
    <a href="index.html">Projects</a>
    <a href="https://github.com/junyanye33/nba-basketball-operations-warehouse">Source code</a>
  </div>
</div>
"""

html = html.replace("</head>", custom_style + "</head>")
html = html.replace("<body>", "<body>" + navigation, 1)
html = html.replace("<title>Notebook</title>", "<title>NBA Basketball Operations Warehouse | Junyan Ye</title>")
HTML_PATH.write_text(html, encoding="utf-8")

print(f"Executed notebook: {NOTEBOOK_PATH}")
print(f"Exported project page: {HTML_PATH}")
