"""Look up how often a points/rebounds/assists line has happened. Run from the repo root."""

import sqlite3
import os

DB_FILE = "scorigami.db"


def check_statline():
    if not os.path.exists(DB_FILE):
        print(f"❌ Error: Database '{DB_FILE}' not found.")
        return

    print("--- 🏀 NBA Stat Line Search 🏀 ---")
    try:
        pts = input("Points (PTS): ").strip()
        reb = input("Rebounds (REB): ").strip()
        ast = input("Assists (AST): ").strip()

        # Simple validation to ensure numbers were entered
        if not (pts.isdigit() and reb.isdigit() and ast.isdigit()):
            print("❌ Invalid input. Please enter numbers only.")
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Query the database
        print(f"\n🔎 Searching for {pts}/{reb}/{ast}...")
        c.execute(
            "SELECT player, date FROM game_log WHERE pts=? AND reb=? AND ast=? ORDER BY date DESC",
            (pts, reb, ast),
        )
        results = c.fetchall()
        conn.close()

        count = len(results)

        print("-" * 40)
        if count == 0:
            print(f"🚨 BALLGAMI! 🚨")
            print(f"No player has ever recorded {pts}/{reb}/{ast}.")
        else:
            print(f"✅ Found {count} instances:")
            print("-" * 40)
            for player, date in results:
                print(f" - {player} ({date})")
        print("-" * 40)

    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    while True:
        check_statline()
        # Ask to search again
        again = input("\nSearch another? (y/n): ").strip().lower()
        if again != "y":
            break
