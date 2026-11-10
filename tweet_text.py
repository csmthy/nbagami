"""Turn a player's stat line into tweet text.

Every line is classified into one category (a new Ballgami, a near miss, a repeat of a
legend's line, and so on), then rendered from the matching block in templates.txt.
"""

import os
import sqlite3
from datetime import datetime

TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.txt")

# Retired players (mostly 1990-2020) whose names make a repeat line worth calling out
HOF_PLAYERS = [
    # --- The Pantheon (Top 20) ---
    "Michael Jordan",
    "Kobe Bryant",
    "Shaquille O'Neal",
    "Tim Duncan",
    "Kevin Garnett",
    "Dirk Nowitzki",
    "Dwyane Wade",
    "Allen Iverson",
    "Steve Nash",
    "Jason Kidd",
    "Scottie Pippen",
    "Charles Barkley",
    "Karl Malone",
    "John Stockton",
    "Hakeem Olajuwon",
    "David Robinson",
    "Patrick Ewing",
    "Clyde Drexler",
    "Gary Payton",
    "Reggie Miller",
    # --- 2000s/2010s Superstars ---
    "Paul Pierce",
    "Ray Allen",
    "Vince Carter",
    "Tracy McGrady",
    "Carmelo Anthony",
    "Dwight Howard",
    "Chris Bosh",
    "Tony Parker",
    "Manu Ginobili",
    "Pau Gasol",
    "Yao Ming",
    "Grant Hill",
    "Penny Hardaway",
    "Chris Webber",
    "Dikembe Mutombo",
    "Alonzo Mourning",
    "Shawn Kemp",
    "Dominique Wilkins",
    "James Worthy",
    "Isiah Thomas",
    # --- The "Infamous", Tough Guys & Cult Heroes ---
    "Dennis Rodman",
    "Metta Sandiford-Artest",
    "Rasheed Wallace",
    "Ben Wallace",
    "Gilbert Arenas",
    "Latrell Sprewell",
    "Stephen Jackson",
    "Matt Barnes",
    "Draymond Green",
    "Bill Laimbeer",
    "Joakim Noah",
    "Zach Randolph",
    "Kevin McHale",
    "Robert Horry",
    "Jason Williams",
    "Stephon Marbury",
    "Steve Francis",
    "Baron Davis",
    "Jermaine O'Neal",
    "Amar'e Stoudemire",
    # --- High-Level Stars & Scorers ---
    "Shawn Marion",
    "Peja Stojakovic",
    "Chauncey Billups",
    "Rip Hamilton",
    "Joe Johnson",
    "Jamal Crawford",
    "Lou Williams",
    "LaMarcus Aldridge",
    "Blake Griffin",
    "Rajon Rondo",
    "Derrick Rose",
    "Kemba Walker",
    "Gordon Hayward",
    "Marc Gasol",
    "Andre Iguodala",
    "Deron Williams",
    "Carlos Boozer",
    "Lamar Odom",
    "Antawn Jamison",
    "Jerry Stackhouse",
    # --- 90s/00s Notable Scorers & Shooters ---
    "Mitch Richmond",
    "Tim Hardaway",
    "Kevin Johnson",
    "Glen Rice",
    "Larry Johnson",
    "Allan Houston",
    "Michael Redd",
    "Brandon Roy",
    "Richard Jefferson",
    "Kenyon Martin",
    "Marcus Camby",
    "Vlade Divac",
    "Arvydas Sabonis",
    "Toni Kukoc",
    "Detlef Schrempf",
    "Chris Mullin",
    "Antoine Walker",
    "Vin Baker",
    "Josh Smith",
    "Monta Ellis",
]


def get_ordinal(n):
    """21 -> '21st', 22 -> '22nd', 13 -> '13th'."""
    n = int(n)
    if 11 <= n % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def get_templates():
    """Read templates.txt: [KEY] headers, each followed by its tweet text."""
    templates, current_key = {}, None
    if not os.path.exists(TEMPLATES_FILE):
        return {}
    with open(TEMPLATES_FILE, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_key = stripped[1:-1]
                templates[current_key] = []
            elif current_key is not None:
                templates[current_key].append(line.rstrip("\n"))  # keep blank lines
    return {k: "\n".join(v).strip() for k, v in templates.items()}


def check_near_miss(db_file, pts, reb, ast):
    """Return 'point', 'rebound' or 'assist' if one more or fewer would have been new."""
    variations = [
        (pts + 1, reb, ast, "point"),
        (pts - 1, reb, ast, "point"),
        (pts, reb + 1, ast, "rebound"),
        (pts, reb - 1, ast, "rebound"),
        (pts, reb, ast + 1, "assist"),
        (pts, reb, ast - 1, "assist"),
    ]
    conn = sqlite3.connect(db_file)
    try:
        for p, r, a, label in variations:
            if min(p, r, a) < 0:
                continue
            seen = conn.execute(
                "SELECT 1 FROM seen_statlines WHERE pts=? AND reb=? AND ast=?", (p, r, a)
            ).fetchone()
            if not seen:
                return label
        return None
    finally:
        conn.close()


def classify(data, db_file, today=None):
    """Pick the template key for a stat line, adding any fields that template needs.

    data needs name, pts, reb, ast and count (prior occurrences), and for repeats
    last_who and last_when (YYYY-MM-DD). today defaults to now.
    """
    if data["count"] == 0:
        return "BALLGAMI"

    try:
        last_date = datetime.strptime(data.get("last_when") or "", "%Y-%m-%d")
    except ValueError:
        last_date = datetime(2000, 1, 1)
    days_ago = ((today or datetime.now()) - last_date).days
    near_miss = check_near_miss(db_file, data["pts"], data["reb"], data["ast"])

    if near_miss:
        data["near_miss_type"] = near_miss
        return "NEAR_MISS"
    if data["name"] in HOF_PLAYERS or data.get("last_who") in HOF_PLAYERS:
        return "LEGENDARY"
    if last_date.year < 2000:
        data["last_year"] = last_date.year
        return "TIME_TRAVELER"
    if data["pts"] >= 40:
        return "HIGH_VOLUME"
    if data["pts"] >= 10 and data["reb"] >= 10 and data["ast"] >= 10:
        return "TRIPLE_DOUBLE"
    if days_ago <= 10:
        data["days_ago"] = days_ago
        return "DEJA_VU"
    if data["count"] > 150:
        return "COMMON"
    if data["count"] < 11:
        return "RARE"
    return "DEFAULT"


def craft_ballgami_tweet(data, db_file, today=None):
    """Return the finished tweet for one stat line."""
    templates = get_templates()
    key = classify(data, db_file, today)
    data["player"] = data["name"]
    data["count_plus_one"] = data["count"] + 1
    data["ordinal_rank"] = get_ordinal(data["count"] + 1)
    template = templates.get(
        key, templates.get("DEFAULT", "{player}: {pts} PTS / {reb} REB / {ast} AST")
    )
    return template.format(**data)
