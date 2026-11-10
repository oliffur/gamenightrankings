# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal board-game-night leaderboard. `results.txt` is a hand-maintained log of every game played; `parse_results.py` turns it into a ratings table. The repo is published as a GitHub Pages site (Jekyll `cayman` theme via `_config.yml`), and **README.md is the site content — it is generated output, so never hand-edit it**; it gets overwritten on the next parser run.

## Commands

```bash
pipenv run python3 parse_results.py    # regenerate README.md, rankings.png, game_history.txt
./update.command                       # run parser + git add/commit/push ("update rankings") — this is the deploy step
pipenv run python -m unittest discover tests   # run tests (currently broken — see below)
```

Dependencies are managed with Pipenv (pandas, matplotlib, numpy). The `tests/` suite is stale: it imports functions from the old TrueSkill-based parser and fails with `ImportError`. The old implementation lives in `archive/parse_results_OLD.py`; `TUTORIAL.md` also describes that old approach, not the current one.

## Data flow

`results.txt` → `parse_results.py` → three generated artifacts:
- `README.md` — overall + per-game markdown leaderboards
- `rankings.png` — top-25 score-over-time plot
- `game_history.txt` — per-game log with each player's score delta

### results.txt format

One game per line: `MM/DD/YYYY|Game Name|TEAM1_MEM1,TEAM1_MEM2;TEAM2_MEM1|RANK1;RANK2` (header line starts with `DATE`).

- Teams are `;`-separated, members within a team are `,`-separated. Free-for-all games are one player per "team".
- Ranks parallel teams: `0` = winner, higher numbers = worse. Ties share a rank value.
- Malformed lines are **silently skipped** by the bare `try/except` in `parse_game_data` — including games logged without ranks yet (they're picked up once ranks are filled in).

## Scoring engine

All players start at 100.0. For each game (processed in file order), each player's score changes by **base score + upset bonus + 0.3 experience bonus** (experience applies for a player's first 100 games). Upset bonuses (±0.9) compare the player's rating against the *median* opponent rating, using a snapshot of ratings taken immediately before that game.

`GAME_CONFIG` maps each game name to `(GameType, multiplier)`. **Adding a new game to `results.txt` requires adding it to `GAME_CONFIG` first** — otherwise `calc_base_bonus` raises `KeyError`. The multiplier discounts luck-heavy games (e.g. Uno 0.3, Bang/Coup 0.6). The four GameTypes each have their own base-score formula:

- `TEAM_BALANCED` — fixed ±1.0
- `TEAM_UNBALANCED` — reward scales with opponent count beaten; loss is fixed −1.0
- `INDIVIDUAL_WINNER` — winners split points equal to the number of losers; losers −1.0
- `INDIVIDUAL_RANKED` — (players beaten − players lost to) / count of players sharing your rank

## Conventions

- `Alias(RealName)` entries (e.g. `Bosco(Vivian)`, `Adam(Allan)`) are just a display convention — each string is scored as its own distinct player.
- At year end, `results.txt` is copied to `archive/<year>results.txt` (with a rankings snapshot png) and the working file starts fresh.
- `wavelength/` is an unrelated side utility that emails Wavelength card prompts; it depends on a `send_email` module outside this repo.
- Commits are almost exclusively auto-generated "update rankings" messages from `update.command`.
