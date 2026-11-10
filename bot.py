"""NBAgami: tweets when an NBA player records a points/rebounds/assists line that has
never happened before in league history (a "Ballgami"), and otherwise how rare the
night's top line was.

Runs every few minutes: pulls finished games from the NBA's public live-data CDN, checks
each player's line against scorigami.db, records it, and posts one tweet per game.

    python bot.py                 # process today's finished games and tweet
    python bot.py --test          # dry run for today, prints instead of tweeting
    python bot.py --test 2026-01-05
"""

import sqlite3
import time
import os
import tweepy
import argparse
import requests
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from tweet_text import craft_ballgami_tweet

# --- 0. CONFIGURATION & SETUP ---
load_dotenv()
API_KEY = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")

# --- DATABASE CONFIG ---
DB_FILE = "scorigami.db"  # Holds stats and game history
LOG_DB_FILE = "tweets.db"  # Holds failed tweet queue

# --- RETRY SETTINGS (Editable) ---
RETRY_DELAY_MINUTES = 30  # How long to wait after hitting the threshold
RETRY_THRESHOLD = 2  # How many fails before we force the delay

CURRENT_SEASON_YEAR = "2025-26"
SEASON_START_DATE = "2025-10-01"

CDN_SCOREBOARD = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
CDN_BOXSCORE = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"


def setup_databases():
    """Sets up both the main stats DB and the separate log DB."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS seen_statlines (
        id INTEGER PRIMARY KEY, pts INTEGER, reb INTEGER, ast INTEGER,
        count INTEGER DEFAULT 1, first_player TEXT, first_date TEXT, 
        last_player TEXT, last_date TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS game_log (
        pts INTEGER, reb INTEGER, ast INTEGER,
        player TEXT, date TEXT)""")
    c.execute(
        """CREATE TABLE IF NOT EXISTS processed_games (game_id TEXT PRIMARY KEY, date TEXT)"""
    )
    conn.commit()
    conn.close()

    conn_log = sqlite3.connect(LOG_DB_FILE)
    c_log = conn_log.cursor()
    c_log.execute("""CREATE TABLE IF NOT EXISTS failed_tweets (
        id INTEGER PRIMARY KEY, 
        game_id TEXT, 
        tweet_text TEXT, 
        attempts INTEGER DEFAULT 0,
        last_attempt TEXT
    )""")
    conn_log.commit()
    conn_log.close()


def is_game_processed(game_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM processed_games WHERE game_id=?", (game_id,))
    res = c.fetchone()
    conn.close()
    return res is not None


def mark_game_processed(game_id, date_str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO processed_games (game_id, date) VALUES (?, ?)", (game_id, date_str)
    )
    conn.commit()
    conn.close()


# --- RETRY LOGIC ---
def log_failed_tweet(game_id, text):
    """Adds a failed tweet to the database with 1 attempt count."""
    conn = sqlite3.connect(LOG_DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM failed_tweets WHERE game_id = ? AND tweet_text = ?", (game_id, text))
    if c.fetchone() is None:
        # We start with attempts=1 because the first try just failed
        c.execute(
            "INSERT INTO failed_tweets (game_id, tweet_text, attempts, last_attempt) VALUES (?, ?, 1, ?)",
            (game_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        print(f"⚠️  Tweet failed. Queued in {LOG_DB_FILE} for retry (Game {game_id})")
    conn.close()


def retry_failed_tweets():
    """Retries tweets based on threshold and delay settings."""
    conn = sqlite3.connect(LOG_DB_FILE)
    c = conn.cursor()

    # Get all failed tweets
    c.execute("SELECT id, game_id, tweet_text, attempts, last_attempt FROM failed_tweets")
    rows = c.fetchall()
    conn.close()

    if not rows:
        return

    print(f"🔄 Checking {len(rows)} failed tweets...")

    for row in rows:
        row_id, game_id, text, attempts, last_attempt_str = row

        # Parse the last attempt time
        last_attempt = datetime.strptime(last_attempt_str, "%Y-%m-%d %H:%M:%S")
        time_since_last = datetime.now() - last_attempt

        # LOGIC:
        # 1. If attempts < THRESHOLD (2), retry immediately (on next run).
        # 2. If attempts >= THRESHOLD, check if DELAY (30 mins) has passed.

        should_retry = False

        if attempts < RETRY_THRESHOLD:
            should_retry = True
        elif time_since_last > timedelta(minutes=RETRY_DELAY_MINUTES):
            should_retry = True
        else:
            print(
                f"   ⏳ Skipping Game {game_id} (Attempt {attempts}). Waiting for cooldown ({RETRY_DELAY_MINUTES}m)."
            )
            continue

        if should_retry:
            print(f"   🚀 Retrying Tweet for Game {game_id} (Attempt {attempts + 1})...")
            success = send_tweet(text)

            conn = sqlite3.connect(LOG_DB_FILE)
            c = conn.cursor()

            if success:
                c.execute("DELETE FROM failed_tweets WHERE id = ?", (row_id,))
                print(f"   ✅ Retry successful! Removed from queue.")
            else:
                # Update timestamp and increment attempts
                c.execute(
                    "UPDATE failed_tweets SET attempts = attempts + 1, last_attempt = ? WHERE id = ?",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), row_id),
                )
                print(f"   ❌ Retry failed.")

            conn.commit()
            conn.close()
            time.sleep(2)


def get_history(pts, reb, ast):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    sql = "SELECT player, date FROM game_log WHERE pts=? AND reb=? AND ast=? ORDER BY date ASC"
    c.execute(sql, (pts, reb, ast))
    results = c.fetchall()
    conn.close()
    return results


def get_counts():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM seen_statlines")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM seen_statlines WHERE first_date >= ?", (SEASON_START_DATE,))
    season = c.fetchone()[0]
    conn.close()
    return total + 1, season + 1


def save_game_data(name, date, pts, reb, ast, is_new_scorigami):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO game_log (pts, reb, ast, player, date) VALUES (?,?,?,?,?)",
        (pts, reb, ast, name, date),
    )

    if is_new_scorigami:
        c.execute(
            """INSERT INTO seen_statlines 
                     (pts, reb, ast, count, first_player, first_date, last_player, last_date)
                     VALUES (?, ?, ?, 1, ?, ?, ?, ?)""",
            (pts, reb, ast, name, date, name, date),
        )
    else:
        c.execute(
            """UPDATE seen_statlines 
                     SET count = count + 1, last_player = ?, last_date = ? 
                     WHERE pts=? AND reb=? AND ast=?""",
            (name, date, pts, reb, ast),
        )
    conn.commit()
    conn.close()


def send_tweet(text, dry_run=False):
    if not API_KEY:
        print(f"\n📢 [DRY RUN - NO KEYS]:\n{text}\n")
        return True
    if dry_run:
        print(f"\n📢 [DRY RUN]:\n{text}\n")
        return True

    try:
        client = tweepy.Client(
            consumer_key=API_KEY,
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET,
        )
        client.create_tweet(text=text)
        print(f"🐦 Tweet Sent!")
        time.sleep(10)
        return True
    except Exception as e:
        print(f"❌ Tweet Failed: {e}")
        return False


# --- MAIN LOGIC ---
def process_games(target_date=None, dry_run=False, tweet_scorigamis=False):
    setup_databases()

    # 1. Retry failed tweets first
    if not dry_run:
        retry_failed_tweets()

    if not target_date:
        # Force "NBA Time" (US Eastern) by subtracting 5 hours from UTC
        # This prevents the bot from jumping to "tomorrow" too early
        nba_time = datetime.now(timezone.utc) - timedelta(hours=5)

        # If it is before 12:00 PM (Noon) in NBA time, keep checking "yesterday"
        # This covers the gap where the NBA file hasn't updated to the new day yet
        if nba_time.hour < 12:
            target_date = (nba_time - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            target_date = nba_time.strftime("%Y-%m-%d")

    print(f"🔎 Checking CDN for games on {target_date}...")

    try:
        resp = requests.get(CDN_SCOREBOARD, timeout=10)
        if resp.status_code != 200:
            print(f"❌ CDN Error: {resp.status_code}")
            return
        data = resp.json()
        games = data["scoreboard"]["games"]
    except Exception as e:
        print(f"❌ Failed to fetch scoreboard: {e}")
        return

    if not games:
        print("No games found.")
        return

    for game in games:
        game_id = game["gameId"]
        if game["gameStatus"] != 3:
            continue

        game_date_str = game["gameEt"].split("T")[0]

        if target_date and game_date_str != target_date:
            continue

        if not dry_run and is_game_processed(game_id):
            continue

        print(f"🏀 Processing Game {game_id}...")

        try:
            time.sleep(0.5)
            box_url = CDN_BOXSCORE.format(game_id=game_id)
            box_resp = requests.get(box_url, timeout=10)
            if box_resp.status_code != 200:
                print("   ⚠️ Box score not ready.")
                continue
            box_data = box_resp.json()["game"]
            players = box_data["homeTeam"]["players"] + box_data["awayTeam"]["players"]
        except Exception as e:
            print(f"   ⚠️ Error processing box score: {e}")
            continue

        scorigami_found = None
        top_scorer = {"pts": -1}

        for p in players:
            try:
                stats_data = p["statistics"]
                if stats_data["minutes"] == "PT00M00.00S" or stats_data["minutes"] == "P0M":
                    continue

                name = f"{p['firstName']} {p['familyName']}"
                pts = int(stats_data["points"])
                reb = int(stats_data["reboundsTotal"])
                ast = int(stats_data["assists"])

                matches = get_history(pts, reb, ast)

                is_scorigami = False
                if not matches:
                    is_scorigami = True
                elif dry_run:
                    if len(matches) == 1:
                        first_who, first_when = matches[0]
                        if first_when == target_date:
                            is_scorigami = True

                stats = {"pts": pts, "reb": reb, "ast": ast}

                if is_scorigami:
                    scorigami_found = stats | {"name": name}
                    if not dry_run and not matches:
                        save_game_data(name, target_date, **stats, is_new_scorigami=True)
                else:
                    if not dry_run:
                        save_game_data(name, target_date, **stats, is_new_scorigami=False)

                    if pts > top_scorer["pts"]:
                        past_matches = [m for m in matches if m[1] != target_date]
                        last_who = past_matches[-1][0] if past_matches else None
                        last_when = past_matches[-1][1] if past_matches else None
                        top_scorer = stats | {
                            "name": name,
                            "count": len(past_matches),
                            "last_who": last_who,
                            "last_when": last_when,
                        }
            except Exception:
                continue

        # --- TWEET DECISION ---
        force_it = dry_run and tweet_scorigamis
        should_tweet = (not dry_run) or force_it
        success = True

        if scorigami_found:
            s = scorigami_found
            s["count"] = 0  # never seen before
            txt = craft_ballgami_tweet(s, DB_FILE)

            success = send_tweet(txt, dry_run=not should_tweet)
            if not success and should_tweet:
                log_failed_tweet(game_id, txt)

        elif top_scorer["pts"] > -1:
            txt = craft_ballgami_tweet(top_scorer, DB_FILE)

            success = send_tweet(txt, dry_run=not should_tweet)
            if not success and should_tweet:
                log_failed_tweet(game_id, txt)

        if not dry_run:
            mark_game_processed(game_id, target_date)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA Scorigami Bot")
    parser.add_argument("--test", nargs="?", const="TODAY", help="Run in test mode")
    parser.add_argument("--tweet", action="store_true", help="FORCE tweet")
    args = parser.parse_args()

    if args.test:
        # If user types specific date (e.g. 2026-01-05), use it.
        # If user types just --test (or TODAY), set to None so process_games calculates it.
        date_input = args.test if args.test != "TODAY" else None

        print(f"🧪 TEST MODE (Force Tweet: {args.tweet})")
        # Pass None to let process_games use the smart Timezone logic
        process_games(target_date=date_input, dry_run=True, tweet_scorigamis=args.tweet)
    else:
        process_games()
