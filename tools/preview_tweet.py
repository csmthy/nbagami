"""Preview the tweet the bot would write for any stat line. Run from the repo root."""

import sqlite3
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
from tweet_text import craft_ballgami_tweet  # noqa: E402

# Configuration
DB_FILE = "scorigami.db"


def get_stat_history(pts, reb, ast):
    """Queries the DB to find context for this stat line."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # We retrieve the count and last player info
    c.execute(
        """
        SELECT count, last_player, last_date 
        FROM seen_statlines 
        WHERE pts=? AND reb=? AND ast=?
    """,
        (pts, reb, ast),
    )

    result = c.fetchone()
    conn.close()

    if result:
        return {"count": result[0], "last_who": result[1], "last_when": result[2]}
    else:
        return None


def main():
    print("\n📝 TWEET PREVIEW 📝")
    print("Enter the details of the old game you want to test.")
    print("-" * 40)

    # 1. Get Input
    player_name = input("Player Name: ").strip()
    try:
        pts = int(input("Points (PTS): "))
        reb = int(input("Rebounds (REB): "))
        ast = int(input("Assists (AST): "))
    except ValueError:
        print("❌ Error: Stats must be numbers.")
        return

    # 2. Lookup Data in DB
    history = get_stat_history(pts, reb, ast)

    # 3. Construct Data Dictionary
    if history:
        # If line exists in DB, use that real data
        # Note: We subtract 1 from count to simulate 'before this game happened'
        # if you want to see exactly how it would have looked back then.
        # But usually seeing current stats is fine for formatting tests.
        data = {
            "name": player_name,
            "pts": pts,
            "reb": reb,
            "ast": ast,
            "count": history["count"],
            "last_who": history["last_who"],
            "last_when": history["last_when"],
        }
        print(f"\n🔍 Found in DB! (Seen {history['count']} times)")
    else:
        # If not in DB, assume it would have been a BALLGAMI
        print("\n✨ Not found in DB. Treating as a NEW Ballgami.")
        data = {
            "name": player_name,
            "pts": pts,
            "reb": reb,
            "ast": ast,
            "count": 0,
            "last_who": "N/A",
            "last_when": "N/A",
        }

    # 4. Generate Tweet
    print("-" * 40)
    print("\n🐦 NEW TWEET VERSION:\n")

    try:
        tweet = craft_ballgami_tweet(data, DB_FILE)
        print(tweet)
    except Exception as e:
        print(f"❌ Error generating text: {e}")

    print("\n" + "=" * 40)


if __name__ == "__main__":
    main()
