"""List every line that was a first in NBA history during the current season."""

import sqlite3
import pandas as pd

# --- CONFIGURATION ---
DB_FILE = "scorigami.db"
SEASON_START_DATE = "2025-10-01"

# FLAGS: Set to False to IGNORE that stat when checking for uniqueness.
# Setting these to False makes Scorigamis MUCH rarer/harder to get.
CONFIG = {
    "pts": True,  # Keep True
    "reb": True,  # Keep True
    "ast": True,  # Keep True
}


def get_season_scorigamis():
    print(f"Checking for Scorigamis since {SEASON_START_DATE}")
    print(f"Active Filters: {[k.upper() for k, v in CONFIG.items() if v]}")
    print("-" * 60)

    conn = sqlite3.connect(DB_FILE)

    # 1. Load the entire history
    # We load it into Pandas so we can re-group it dynamically based on your flags
    df = pd.read_sql_query("SELECT * FROM seen_statlines", conn)
    conn.close()

    if df.empty:
        print("Database is empty.")
        return

    # 2. Determine which columns we are grouping by
    group_cols = [k for k, v in CONFIG.items() if v]

    # 3. Find the "First Occurrence" for every combo based on active flags
    # We sort by date so .first() grabs the historical original
    df["first_date"] = pd.to_datetime(df["first_date"])
    df_sorted = df.sort_values("first_date")

    # This creates a new view of history where only the selected stats matter
    # It finds the earliest date ANYONE posted this specific combo
    unique_history = df_sorted.groupby(group_cols, as_index=False).first()

    # 4. Filter for specific Season
    # We only want lines where the "First Time Ever" happened AFTER our season start
    season_scorigamis = unique_history[unique_history["first_date"] >= SEASON_START_DATE]

    # Sort by date descending (newest first)
    season_scorigamis = season_scorigamis.sort_values("first_date", ascending=False)

    if season_scorigamis.empty:
        print("\n0 Scorigamis found with these settings.")
        print("(Try enabling more flags or checking the date).")
        return

    print(f"\nFound {len(season_scorigamis)} Scorigamis:\n")

    # Dynamic header based on config
    header = f"{'DATE':<12} | {'PLAYER':<25}"
    if CONFIG["pts"]:
        header += f" | {'PTS':<3}"
    if CONFIG["reb"]:
        header += f" {'REB':<3}"
    if CONFIG["ast"]:
        header += f" {'AST':<3}"

    print(header)
    print("-" * len(header))

    for _, row in season_scorigamis.iterrows():
        d_str = row["first_date"].strftime("%Y-%m-%d")
        line = f"{d_str:<12} | {row['first_player']:<25}"

        if CONFIG["pts"]:
            line += f" | {row['pts']:<3}"
        if CONFIG["reb"]:
            line += f" {row['reb']:<3}"
        if CONFIG["ast"]:
            line += f" {row['ast']:<3}"

        print(line)


if __name__ == "__main__":
    get_season_scorigamis()
