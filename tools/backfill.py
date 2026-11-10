"""Build scorigami.db from a CSV of every player box score in NBA history.

Expects player_stats.csv in the working directory with the columns in COLUMN_MAP
(the shape of the public "NBA Database" box-score export). Run from the repo root.
"""

import sqlite3
import pandas as pd
import os

# --- CONFIGURATION ---
CSV_FILE = "player_stats.csv"
DB_FILE = "scorigami.db"

# Column Mapping (CSV Header -> Our Variable)
# We strictly define only these columns to ensure Steals/Blocks are ignored.
COLUMN_MAP = {
    "pts": "points",
    "reb": "reboundsTotal",
    "ast": "assists",
    "date": "gameDateTimeEst",
    "f_name": "firstName",
    "l_name": "lastName",
}


def setup_database():
    print(f"Rebuilding {DB_FILE} from scratch...")

    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print("Deleted old database.")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 1. SUMMARY TABLE
    # Strictly P/R/A
    c.execute("""CREATE TABLE seen_statlines (
        id INTEGER PRIMARY KEY,
        pts INTEGER, reb INTEGER, ast INTEGER,
        count INTEGER DEFAULT 1,
        first_player TEXT, first_date TEXT, 
        last_player TEXT, last_date TEXT
    )""")

    # 2. GAME LOG
    c.execute("""CREATE TABLE game_log (
        pts INTEGER, reb INTEGER, ast INTEGER,
        player TEXT, date TEXT
    )""")

    # Create Indices for speed
    c.execute("CREATE INDEX idx_log_stats ON game_log (pts, reb, ast)")
    c.execute("CREATE UNIQUE INDEX idx_statline ON seen_statlines (pts, reb, ast)")

    conn.commit()
    return conn


def run_backfill():
    if not os.path.exists(CSV_FILE):
        print(f"Error: Could not find {CSV_FILE}.")
        return

    conn = setup_database()

    print("Loading CSV (this might take a moment)...")
    try:
        # We ONLY load the columns defined in COLUMN_MAP
        # This prevents the script from even 'seeing' steals or blocks data
        use_cols = list(COLUMN_MAP.values())
        df = pd.read_csv(CSV_FILE, usecols=use_cols)
    except Exception as e:
        print(f"Failed to read CSV: {e}")
        return

    # 1. CLEANUP & FORMATTING
    print("Processing data...")
    df[COLUMN_MAP["date"]] = pd.to_datetime(df[COLUMN_MAP["date"]], format="mixed", utc=True)

    df["full_name"] = df[COLUMN_MAP["f_name"]] + " " + df[COLUMN_MAP["l_name"]]

    # Rename to match DB columns
    df = df.rename(
        columns={
            COLUMN_MAP["pts"]: "pts",
            COLUMN_MAP["reb"]: "reb",
            COLUMN_MAP["ast"]: "ast",
            COLUMN_MAP["date"]: "date",
        }
    )

    # Ensure integers.
    # Note: In the very early 1940s/50s, rebounds sometimes weren't tracked.
    # fillna(0) will turn those missing stats into 0s.
    stats_cols = ["pts", "reb", "ast"]
    df[stats_cols] = df[stats_cols].fillna(0).astype(int)

    # Sort by date (Critical for First/Last logic)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df.sort_values("date", ascending=True)

    # --- PART 1: SAVE FULL LOG ---
    print("Populating Game Log...")
    log_df = df[["pts", "reb", "ast", "full_name", "date"]].rename(columns={"full_name": "player"})
    log_df.to_sql("game_log", conn, if_exists="replace", index=False)

    # --- PART 2: COLLAPSE DATA ---
    print("Collapsing data to find unique P/R/A combinations...")

    grouped = (
        df.groupby(stats_cols)
        .agg({"full_name": ["first", "last"], "date": ["first", "last"], "pts": "size"})
        .reset_index()
    )

    # Flatten columns
    grouped.columns = [
        "pts",
        "reb",
        "ast",
        "first_player",
        "last_player",
        "first_date",
        "last_date",
        "count",
    ]

    print(f"Found {len(grouped)} unique P/R/A combinations.")
    print("Saving to Summary Table...")

    grouped.to_sql("seen_statlines", conn, if_exists="replace", index=False)

    print("✅ Success! Database rebuilt with full history (P/R/A only).")
    conn.close()


if __name__ == "__main__":
    run_backfill()
