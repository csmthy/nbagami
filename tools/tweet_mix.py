"""How often would each tweet type fire? Replays the top scorers of recent game days
through the same classifier the bot uses and prints the mix.

    python tools/tweet_mix.py        # run from the repo root, after building scorigami.db
"""

import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
from tweet_text import classify  # noqa: E402

DB_FILE = "scorigami.db"
GAMES_TO_ANALYZE = 1000


def get_db_connection():
    return sqlite3.connect(DB_FILE)


def get_history(pts, reb, ast):
    """Every earlier occurrence of this exact line, oldest first."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT player, date FROM game_log WHERE pts=? AND reb=? AND ast=? ORDER BY date ASC",
        (pts, reb, ast),
    ).fetchall()
    conn.close()
    return rows


def classify_statline(data):
    today = datetime.strptime(data["game_date"], "%Y-%m-%d") if data.get("game_date") else None
    return classify(data, DB_FILE, today)


def analyze_recent_games():
    print(f"📊 Analyzing the last {GAMES_TO_ANALYZE} games...")
    print("=" * 60)

    games_processed = 0
    stats_counter = Counter()
    unique_players = set()

    current_date = datetime.now() - timedelta(days=1)

    while games_processed < GAMES_TO_ANALYZE:
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"📅 Checking {date_str}...", end="\r")

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT player, pts, reb, ast FROM game_log WHERE date=?", (date_str,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            current_date -= timedelta(days=1)
            continue

        # Sort by points descending to find "Top Scorers"
        rows.sort(key=lambda x: x[1], reverse=True)

        daily_top_performers = rows[:5]

        for r in daily_top_performers:
            if games_processed >= GAMES_TO_ANALYZE:
                break

            name, pts, reb, ast = r
            unique_players.add(name)

            history = get_history(pts, reb, ast)
            past_matches = [h for h in history if h[1] < date_str]

            count = len(past_matches)
            last_who = past_matches[-1][0] if past_matches else "N/A"
            last_when = past_matches[-1][1] if past_matches else "2000-01-01"

            data = {
                "name": name,
                "pts": pts,
                "reb": reb,
                "ast": ast,
                "count": count,
                "last_who": last_who,
                "last_when": last_when,
                "game_date": date_str,
            }

            category = classify_statline(data)
            stats_counter[category] += 1
            games_processed += 1

        current_date -= timedelta(days=1)

    print("\n" + "=" * 60)
    print(f"📈 FINAL RESULTS (Sample Size: {GAMES_TO_ANALYZE} Tweets)")
    print("-" * 30)

    total = sum(stats_counter.values())

    for category, count in stats_counter.most_common():
        percentage = (count / total) * 100
        print(f"{category:<15} : {count:>2}  ({percentage:.1f}%)")

    print("-" * 30)
    print(f"👥 Unique Players : {len(unique_players)}")
    print(f"🎲 Diversity Rate : {(len(unique_players)/total)*100:.1f}%")


if __name__ == "__main__":
    analyze_recent_games()
