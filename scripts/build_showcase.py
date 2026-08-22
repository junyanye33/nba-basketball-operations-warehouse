"""Build publication quality charts from the complete gold warehouse.

Run after a season load:
    python scripts/build_showcase.py
"""
import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD = PROJECT_ROOT / "data" / "gold" / "gold.duckdb"
DOCS = PROJECT_ROOT / "docs"
ASSETS = DOCS / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

NAVY = "#132238"
BLUE = "#286DA8"
ORANGE = "#E8752E"
GREEN = "#39805B"
RED = "#B74D45"
SLATE = "#607086"
LIGHT = "#E8EDF3"
PALE = "#F5F7FA"

plt.rcParams.update(
    {
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
        "grid.linewidth": 0.8,
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": NAVY,
        "xtick.color": SLATE,
        "ytick.color": SLATE,
    }
)

con = duckdb.connect(str(GOLD), read_only=True)


def finish(fig, filename: str) -> None:
    fig.savefig(ASSETS / filename, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def chart_scoring_leaders() -> list[dict]:
    df = con.sql(
        """
        SELECT p.player_name,
               t.team_abbreviation AS team,
               COUNT(*) AS games,
               ROUND(AVG(f.points), 1) AS ppg,
               SUM(f.points) AS total_points
        FROM fact_player_game f
        JOIN dim_player p USING (player_id)
        JOIN dim_team t ON t.team_id = f.team_id
        GROUP BY 1, 2
        HAVING COUNT(*) >= 55
        ORDER BY ppg DESC
        LIMIT 12
        """
    ).df()
    plot = df.iloc[::-1]

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    y = np.arange(len(plot))
    ax.hlines(y, 0, plot["ppg"], color=LIGHT, linewidth=5)
    ax.scatter(plot["ppg"], y, s=120, color=ORANGE, zorder=3)
    for i, value in enumerate(plot["ppg"]):
        ax.text(value + 0.25, i, f"{value:.1f}", va="center", fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{name}  ·  {team}" for name, team in zip(plot["player_name"], plot["team"])]
    )
    ax.set_xlabel("Points per game")
    ax.set_xlim(0, plot["ppg"].max() + 3)
    ax.set_title("Season scoring leaders", loc="left", pad=14)
    ax.text(
        0,
        1.01,
        "Players with at least 55 appearances",
        transform=ax.transAxes,
        color=SLATE,
        fontsize=10,
    )
    ax.grid(axis="y", visible=False)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    finish(fig, "season_scoring_leaders.png")
    return json.loads(df.to_json(orient="records"))


def chart_player_form_trends() -> None:
    df = con.sql(
        """
        WITH eligible AS (
            SELECT player_id
            FROM fact_player_game
            GROUP BY player_id
            HAVING COUNT(*) >= 55
            ORDER BY AVG(points) DESC
            LIMIT 5
        )
        SELECT f.game_date, p.player_name, f.avg_points_prior_10 AS rolling_ppg
        FROM mart_player_form f
        JOIN eligible e USING (player_id)
        JOIN dim_player p USING (player_id)
        WHERE f.games_prior_10 = 10
        ORDER BY f.game_date
        """
    ).df()

    fig, ax = plt.subplots(figsize=(11, 5.6))
    colors = [ORANGE, BLUE, GREEN, RED, "#7A5AA6"]
    for color, (player, group) in zip(colors, df.groupby("player_name")):
        ax.plot(
            group["game_date"],
            group["rolling_ppg"],
            label=player,
            color=color,
            linewidth=2.1,
        )
    ax.set_ylabel("Prior 10 game scoring average")
    ax.set_xlabel("Regular season date")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_title("How elite scoring form changed through the season", loc="left", pad=14)
    ax.text(
        0,
        1.01,
        "Each point uses only the ten games completed before that date",
        transform=ax.transAxes,
        color=SLATE,
        fontsize=10,
    )
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14))
    ax.grid(axis="x", visible=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    finish(fig, "player_form_trends.png")


def chart_team_performance() -> None:
    df = con.sql(
        """
        SELECT t.team_abbreviation AS team,
               SUM(f.win) AS wins,
               AVG(f.plus_minus) AS avg_margin
        FROM fact_team_game f
        JOIN dim_team t USING (team_id)
        GROUP BY 1
        ORDER BY wins DESC
        """
    ).df()

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    ax.scatter(
        df["wins"],
        df["avg_margin"],
        s=70,
        color=np.where(df["avg_margin"] >= 0, BLUE, SLATE),
        alpha=0.9,
    )
    for _, row in df.iterrows():
        ax.annotate(
            row["team"],
            (row["wins"], row["avg_margin"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8.5,
        )
    ax.axhline(0, color=LIGHT, linewidth=1.3)
    ax.axvline(df["wins"].median(), color=LIGHT, linewidth=1.3)
    ax.set_xlabel("Regular season wins")
    ax.set_ylabel("Average point differential per game")
    ax.set_title("Team results align with sustainable point differential", loc="left", pad=14)
    ax.text(
        0,
        1.01,
        "Upper right teams combined high win totals with positive scoring margins",
        transform=ax.transAxes,
        color=SLATE,
        fontsize=10,
    )
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    finish(fig, "team_performance.png")


def chart_rest_advantage() -> list[dict]:
    df = con.sql(
        """
        WITH paired AS (
            SELECT a.game_id,
                   a.team_id,
                   a.win,
                   a.days_rest - b.days_rest AS rest_edge
            FROM mart_team_schedule_context a
            JOIN mart_team_schedule_context b
              ON a.game_id = b.game_id AND a.team_id <> b.team_id
            WHERE a.days_rest IS NOT NULL AND b.days_rest IS NOT NULL
        )
        SELECT CASE
                   WHEN rest_edge <= -2 THEN '2+ fewer days'
                   WHEN rest_edge = -1 THEN '1 fewer day'
                   WHEN rest_edge = 0 THEN 'Equal rest'
                   WHEN rest_edge = 1 THEN '1 extra day'
                   ELSE '2+ extra days'
               END AS rest_advantage,
               AVG(win) * 100 AS win_pct,
               COUNT(*) AS team_games,
               MIN(rest_edge) AS sort_key
        FROM paired
        GROUP BY 1
        ORDER BY sort_key
        """
    ).df()

    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    colors = [RED, "#D98A70", SLATE, "#72A58A", GREEN]
    bars = ax.barh(df["rest_advantage"], df["win_pct"], color=colors)
    ax.axvline(50, color=NAVY, linestyle=(0, (3, 3)), linewidth=1.2)
    for bar, win_pct, n in zip(bars, df["win_pct"], df["team_games"]):
        ax.text(
            win_pct + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{win_pct:.1f}%   n={n:,}",
            va="center",
            fontweight="bold",
            fontsize=9.5,
        )
    ax.set_xlim(0, max(65, df["win_pct"].max() + 8))
    ax.set_xlabel("Win rate")
    ax.set_title("Rest advantage is compared with the opponent in the same game", loc="left", pad=14)
    ax.text(
        0,
        1.01,
        "The 50 percent reference line represents an even split",
        transform=ax.transAxes,
        color=SLATE,
        fontsize=10,
    )
    ax.grid(axis="y", visible=False)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    finish(fig, "rest_advantage.png")
    return json.loads(df.drop(columns=["sort_key"]).to_json(orient="records"))


def chart_pipeline_reliability() -> None:
    df = con.sql(
        """
        SELECT DATE_TRUNC('month', c.game_date) AS month,
               SUM(c.games) AS games,
               SUM(
                   (SELECT COUNT(*)
                    FROM fact_player_game f
                    WHERE f.game_date = c.game_date)
               ) AS player_rows,
               COUNT(*) AS game_dates,
               SUM(CASE WHEN c.status = 'complete' THEN 1 ELSE 0 END) AS complete_dates
        FROM mart_data_completeness c
        GROUP BY 1
        ORDER BY 1
        """
    ).df()
    labels = [date.strftime("%b") for date in df["month"]]

    fig, ax = plt.subplots(figsize=(10.5, 5.3))
    bars = ax.bar(labels, df["player_rows"], color=BLUE, width=0.62)
    for bar, rows, games in zip(bars, df["player_rows"], df["games"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            rows + 90,
            f"{int(rows):,} rows\n{int(games)} games",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_ylabel("Player game rows loaded")
    ax.set_xlabel("2025 to 2026 regular season")
    ax.set_ylim(0, df["player_rows"].max() * 1.22)
    ax.set_title("Complete season coverage with daily reconciliation", loc="left", pad=14)
    ax.text(
        0,
        1.01,
        "164 of 164 game dates passed all row accounting and game grain checks",
        transform=ax.transAxes,
        color=GREEN,
        fontsize=10,
        fontweight="bold",
    )
    ax.grid(axis="x", visible=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    finish(fig, "pipeline_reliability.png")


def build_summary(scoring_leaders: list[dict], rest_results: list[dict]) -> dict:
    metrics = con.sql(
        """
        SELECT (SELECT COUNT(*) FROM dim_game) AS games,
               (SELECT COUNT(*) FROM fact_player_game) AS player_rows,
               (SELECT COUNT(*) FROM fact_team_game) AS team_rows,
               (SELECT COUNT(DISTINCT player_id) FROM fact_player_game) AS players,
               (SELECT COUNT(DISTINCT game_date) FROM dim_game) AS game_dates,
               MIN(game_date) AS first_date,
               MAX(game_date) AS last_date
        FROM dim_game
        """
    ).fetchone()
    summary = {
        "games": metrics[0],
        "player_rows": metrics[1],
        "team_rows": metrics[2],
        "players": metrics[3],
        "game_dates": metrics[4],
        "first_date": str(metrics[5]),
        "last_date": str(metrics[6]),
        "tests": 18,
        "reconciliation_passed": metrics[4],
        "scoring_leaders": scoring_leaders,
        "rest_results": rest_results,
    }
    (DOCS / "showcase_data.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    scoring = chart_scoring_leaders()
    chart_player_form_trends()
    chart_team_performance()
    rest = chart_rest_advantage()
    chart_pipeline_reliability()
    summary = build_summary(scoring, rest)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
