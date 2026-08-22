import duckdb

con = duckdb.connect("data/gold/gold.duckdb", read_only=True)

print("Neutral-site games in the loaded week:")
print(
    con.sql(
        """
        SELECT g.game_id, g.game_date, h.team_abbreviation AS home_slot,
               a.team_abbreviation AS away_slot, g.home_points, g.away_points
        FROM dim_game g
        JOIN dim_team h ON h.team_id = g.home_team_id
        JOIN dim_team a ON a.team_id = g.away_team_id
        WHERE g.is_neutral = 1
        """
    ).df().to_string(index=False)
)

print("\nHottest players entering 2026-01-16 (rolling form, prior games only):")
print(
    con.sql(
        """
        SELECT p.player_name,
               f.games_prior_10,
               ROUND(f.avg_points_prior_10, 1) AS avg_pts_entering,
               f.points AS pts_that_night
        FROM mart_player_form f
        JOIN dim_player p USING (player_id)
        WHERE f.game_date = DATE '2026-01-16' AND f.games_prior_10 >= 2
        ORDER BY f.avg_points_prior_10 DESC
        LIMIT 8
        """
    ).df().to_string(index=False)
)

print("\nSchedule fatigue check: back-to-back team performance that week:")
print(
    con.sql(
        """
        SELECT t.team_abbreviation, c.game_date, c.days_rest, c.is_back_to_back,
               c.points, c.win
        FROM mart_team_schedule_context c
        JOIN dim_team t USING (team_id)
        WHERE c.is_back_to_back = 1
        ORDER BY c.game_date
        LIMIT 8
        """
    ).df().to_string(index=False)
)
