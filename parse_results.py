"""Parses results.txt into a markdown leaderboard"""

import logging
from typing import Dict, List, Tuple

from inferent.ratings import TSRating
from matplotlib import pyplot as plt
import pandas as pd

logger = logging.getLogger("ratings")
logger.setLevel(logging.INFO)

LUCK_FACTORS = {
    "What do you Meme": 10.0,
    "Incan Gold": 10.0,
    "Exploding Kittens": 10.0,
    "Love Letter": 10.0,
    "No Thanks": 10.0,
    "Shifty Eyed Spies": 10.0,
    "Cash n Guns": 10.0,
    "Bang": 1.0,
    "Coup": 10.0,
    "Masquerade": 10.0,
    "Camel Up": 10.0,
    "Here to Slay": 10.0,
}


def parse_results(file_path: str = "results.txt"):
    """Parses results.txt into a dataframe"""
    results = []
    with open(file_path, encoding="ascii") as f:
        for line in f:
            if line.startswith("DATE"):
                continue
            date, game, teams, ranks = line.split("|")
            teams = [team.split(",") for team in teams.split(";")]
            ranks = list(map(int, ranks.split(";")))
            results.append((date, game, teams, ranks))

    return pd.DataFrame(results, columns=["date", "game", "teams", "ranks"])


def get_ratings(results_df: pd.DataFrame):
    """From the results dataframe, generates TSRating objects and a time series.

    Returns:
    - overall_df: results_df but enriched with `rating` column which contains
                  a list of list of Player instances in the same shape as
                  `teams`, for time series
    - overall_ts: the final TSRating object, which contains the dictionary of
                  final player ratings, for rankings
    - ts_dict:    a dictionary of 'game' to a TSRating object for that specific
                  game subset, for per-game rankings
    """
    ts_dict = {}  # TSRating classes with latest player information
    for game in results_df["game"].unique():
        ts_dict[game] = TSRating(
                beta_adjustments=LUCK_FACTORS,
                mu=100.0,
                sigma=100.0,
                beta=5.0,
                tau=0.05)
        _ = ts_dict[game].enrich_update(results_df.loc[results_df.game == game])
    overall_ts = TSRating(
            beta_adjustments=LUCK_FACTORS,
            mu=100.0,
            sigma=100.0,
            beta=5.0,
            tau=0.05)
    overall_df = overall_ts.enrich_update(results_df)
    return overall_df, overall_ts, ts_dict


def get_best_game_by_player(ts_dict: Dict[str, TSRating]) -> Dict[str, float]:
    """From ts_dict (per-game rankings), finds the top ranked game per player"""
    best_dict = {}  # Dictionary of player -> (game, min_rating)
    for game, ts in ts_dict.items():
        for player, p in ts.players.items():
            min_rating = p.get_min_rating()
            if player not in best_dict or min_rating > best_dict[player][1]:
                best_dict[player] = (game, min_rating)
    return best_dict


def add_ranking_rows(
    game: str,
    overall_ts: TSRating,
    markdown: str,
    infrequent_threshold: int = -1,
) -> Tuple[List, str]:
    """Adds ranking row markdown strings to markdown (and returns it).

    If infrequent_threshold is set to a reasonable value, also returns a list
    of players who have played fewer than `infrequent_threshold` games.
    """
    # fmt: off
    markdown +=\
f"""

### {game}

| Player | ELO | Wins | Losses | Win % |
| --- | --- | --- | --- | --- |
"""
    # fmt: on

    infrequent_players = []  # players with <10 games
    for player, p in sorted(
        overall_ts.players.items(),
        key=lambda item: item[1].get_min_rating(),
        reverse=True,
    ):
        if player.startswith("dummy"):  # skip dummies
            continue

        # fmt: off
        markdown +=\
f"""\
| {player} | {p.get_min_rating():.2f} | {p.wins} | {p.losses} | {p.wins / (p.wins + p.losses):.0%} |
"""
        # fmt: on

        if p.wins + p.losses < infrequent_threshold:
            infrequent_players.append(player)

    return markdown, infrequent_players


def flatten(xss):
    """Flattens a list of lists into one single list, maintaining order"""
    return [x for xs in xss for x in xs]


def plot_rankings_over_time(df: pd.DataFrame, infrequent_players: List[str]):
    """From a dataframe with enriched ratings, plot a time series of rankings.

    TODO: make rankings.png a parameter I guess
    """
    plt.style.use("ggplot")
    chart_df = pd.DataFrame()

    for date, ps in zip(df["date"], df["ratings"]):
        for p in flatten(ps):
            if p.name.startswith("dummy"):
                continue
            chart_df.at[date, p.name] = p.get_min_rating()
            logger.info("%s : %s : %s", p.name, p.get_min_rating(), p.rtg.sigma)

    chart_df = chart_df.ffill().drop(columns=infrequent_players)
    if not chart_df.empty:
        chart_df.plot.line().legend(
            loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.3)
        )
    plt.xticks(rotation="vertical")
    plt.subplots_adjust(bottom=0.25)
    plt.savefig("rankings.png")


def main():
    """
    Calls parse_results() and then updates README.md based on return value.
    """

    results_df = parse_results()
    overall_df, overall_ts, ts_dict = get_ratings(results_df)

    # pylint: disable=line-too-long
    # fmt: off
    markdown =\
"""
![Image](https://media.architecturaldigest.com/photos/618036966ba9675f212cc805/16:9/w_2560%2Cc_limit/SquidGame_Season1_Episode1_00_44_44_16.jpg)
"""
    # fmt: on
    # pylint: enable=line-too-long

    best_dict = get_best_game_by_player(ts_dict)
    logger.info(best_dict)
    markdown, infrequent_players = add_ranking_rows(
        "Overall Rankings", overall_ts, markdown, infrequent_threshold=0
    )
    plot_rankings_over_time(overall_df, infrequent_players)

    # fmt: off
    markdown +=\
"""

### Rankings over Time
![Image](rankings.png)

"""
    # fmt: on
    for game, ts in ts_dict.items():
        markdown, _ = add_ranking_rows(game, ts, markdown)

    with open("README.md", "w", encoding="ascii") as f:
        f.write(markdown)


if __name__ == "__main__":
    main()
