# Making your Own Leaderboard

1) You will need to keep track of your results manually. For example, see **results.txt** as an example of how I have done this. It does not matter what format you do this in, because the next step will be...
2) Parse the results into a dataframe. In **parse_results.py**, I have done so via:

```python3
def parse_results(file_path: str = "results.txt"):
    """
    Parses results.txt into a dataframe
    """
    results = []
    with open(file_path) as f:
        for line in f:
            if line.startswith("DATE"):
                continue
            date, game, teams, ranks = line.split("|")
            teams = [team.split(",") for team in teams.split(";")]
            ranks = list(map(int, ranks.split(";")))
            results.append((date, game, teams, ranks))

    return pd.DataFrame(results, columns=["date", "game", "teams", "ranks"])
```

What's important is that your dataframe has the following columns:

-  ```teams```, which is a list of list of each team (an individual can be his own team, for example in a deathmatch like mahjong or poker, each individual is one team of himself), and
-  ```ranks```, which is a list with the same first-dimensional shape as ```teams``` with the rankings of each teams. If a team is the winner, you must denote it with 0; all other losers must have >0 values according to their ranking. The exact number does not matter; it is easiest to just use the natural numbers 0, 1, 2, .... Again, see **results.txt** for an example.
-  I highly recommend you also have a ```date``` column to keep track of the time series.

3) Call the ranking module. Once you have your parsed ratings into a dataframe, you can call the TSRating module from the inferent library to get the scores:

```python3
from inferent.ratings import TSRating
df = parse_results()
ts = TSRating()
df = overall_ts.enrich_update(df)
```

TSRating is a class that holds a bunch of player objects in a dictionary ```ts.players```. After you call ```enrich_update()```, two things will happen:
- the dataframe you pass in will be enriched by adding a column ```ratings``` which contains a list of trueskill.Rating objects in the same shape as ```teams```. You can look at **parse_results.py** for how to use this output, and consult the trueskill docs at https://trueskill.org/.
- the TrueSkill instance you use to update the ratings will update its ```players``` dictionary, and that dictionary will contain the latest information about its players. The players class is a custom class defined within my ```inferent``` module, but I've pasted it below for your convenience. Again, consult ```parse_results.py``` if you need help on how to use it.

```python3
class Player:
    """Container for player-level data"""

    name: str = ""
    wins: int = 0
    losses: int = 0

    def __init__(
        self, env: trueskill.TrueSkill, name: str, scale=4.0
    ) -> None:
        """
        Initializes DualRating with offensive and defensive ratings.

        :param env: TrueSkill environment
        :param scale: scaling factor for mean (default mean is 25.0)
        """
        self.rtg: trueskill.Rating = env.create_rating()
        self.name = name
        self.scale: float = scale  # TODO: remove scale; change directly

    def get_rating(self) -> float:
        """Get mean rating"""
        return self.rtg.mu * self.scale  # scale to 100

    def get_min_rating(self) -> float:
        """Get value 2 standard deviations below mean"""
        return (self.rtg.mu - 2 * max(0.0, self. mean  [A]      lf.scale
```

In general, use (1) to get a time series of scores (how has Leo's rating changed over time?) and use (2) to get the final up-to-date rankings (who is the highest and lowest ranking person right now?).

4) Nuances: for nuances, e.g. changing the default mean or standard deviation, or adding luck factors (e.g. majhong is more luck-based than poker), or other tweaking, please contact the owner of this repository.
