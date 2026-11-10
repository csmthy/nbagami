# NBAgami

An X (Twitter) bot that watched every NBA game during the 2025–26 season and posted when a player put up a points / rebounds / assists line that had **never happened before in NBA history**: a "Ballgami," borrowing the idea of [Scorigami](https://en.wikipedia.org/wiki/Scorigami) from football scores.

When nobody hit a new line, it posted the night's top line with context on how rare it was: who did it last, whether it was a near miss, or whether a legend owns the same numbers.

Two of the tweet formats, with made-up numbers:

```
🚨 BALLGAMI ALERT 🚨

History has been made. Jane Doe just recorded 61 PTS / 10 REB / 10 AST.

This is the FIRST time this stat line has ever happened in the history of the NBA.
```

```
SO CLOSE to a Ballgami! 🤏
Jane Doe finished with 31 PTS / 14 REB / 9 AST.

If he had recorded just one more assist, it would have been a unique line. Instead,
he becomes the 4th person to hit this mark.
```

## How it works

1. **History:** `tools/backfill.py` loads every player box score in NBA history from a CSV export, then collapses it with pandas into one row per unique points/rebounds/assists combination, recording how often it happened and who did it first and last. Everything goes into SQLite (`scorigami.db`).
2. **Live games:** `bot.py` runs every five minutes on GitHub Actions. It reads the NBA's public live-data CDN for games that have finished, pulls each box score, and checks every player's line against the database. Days roll over on US Eastern time, so late West Coast games still count toward the right date.
3. **Writing the tweet:** `tweet_text.py` classifies each line in priority order: new Ballgami, near miss (one stat away from unique), a retired legend's line, last seen before 2000, 40-point night, triple-double, repeated within 10 days, very common, very rare. It then fills the matching template from `templates.txt`.
4. **Posting:** one tweet per game through the X API with tweepy. Failed posts go into a retry queue with a cooldown so a rate limit doesn't lose a tweet. Processed games are recorded, so reruns never double-post.

## Tools

| Script | What it does |
|---|---|
| `tools/backfill.py` | Rebuild the history database from the box-score CSV |
| `tools/search.py` | Look up how many times a stat line has happened |
| `tools/preview_tweet.py` | Show the tweet the bot would write for any line |
| `tools/season_ballgamis.py` | List every first-ever line recorded this season |
| `tools/tweet_mix.py` | Replay recent games to see how often each tweet type would fire |

## Run it

```bash
pip install -r requirements.txt
python tools/backfill.py         # needs player_stats.csv (full NBA box-score history)
python bot.py --test             # dry run for today: prints tweets instead of posting
python bot.py --test 2026-01-05  # dry run for a past date
```

To post for real, copy `.env.example` to `.env` and add X API credentials. The GitHub Actions workflow reads the same four values from repository secrets.

The database and source CSV aren't in the repo (the CSV is over 300 MB). The bot is retired, so the workflow is now manual-only.

## License

MIT, see [LICENSE](LICENSE).
