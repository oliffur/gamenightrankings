"""V2 scoring engine: Elo with harmonic team model + pairwise FFA/ranked.

Runs in parallel to parse_results.py (which stays the live pipeline):
- Reads the same results.txt via the shared parser. GAME_CONFIG is a
  v2-local copy: config edits here never affect the live v1 pipeline.
- Writes only v2-suffixed artifacts: README_v2.md, rankings_v2.png,
  game_history_v2.txt (full per-game delta decomposition for debugging).
- __main__ also runs the v1 engine in-memory and prints an old-vs-new
  leaderboard comparison plus calibration stats.

Model:
- State per player: mu (start 100.0) + games played. Display score = mu - sigma,
  where sigma decays with games played so brand-new players cannot top the
  leaderboard; after ~PROV_GAMES games volume stops mattering.
- Team games: each player plays pairwise Elo against the opposing team's
  collective rating (harmonic_mean(strengths) * N^EPS, sub-additive: a 2-team
  beating a 4-team is near 50-50 for equal players, not heroic), so stronger
  members of a team gain less and lose more than weaker members.
- Individual games (FFA and ranked): pairwise results vs every other player
  (ties = 0.5), so upsets pay more and co-winners/co-losers split credit.
- delta = K_i * mult * f(actual - expected) with f(x) = x*(|2x|**UPSET_AMP):
  surprising results are amplified, expected ones damped (f(0.5) = 0.5 keeps
  the Quest anchor); zero-sum normalized per game.
  Stakes are anchored to a 2-team game (Quest): a unique winner gains and a
  unique last-place loses ~mult x a Quest win/loss; ties and middle ranks
  pay fractions. Winner side is the anchor; co-losers split the cost.
"""

import math
from collections import defaultdict
from typing import Dict, List

from parse_results import (
    GameResult,
    GameType,
    RankingCalculator,
    ResultFormatter,
    parse_game_data,
)

# --- Tunables ---

K_PROV, K_STD, PROV_GAMES = 8.0, 6.0, 30   # elo k-factor: provisional vs established
SIGMA0, SIGMA_FLOOR, TAU = 16.0, 2.0, 10.0  # display-uncertainty decay by games played
SCALE = 400.0                               # rating -> strength scale (chess std; wider = flatter, upsets pay less)
UPSET_AMP = 1.0                             # surprise amplifier: x -> x*(|2x|**UPSET_AMP); 0.5->0.5 keeps Quest anchor
EPS = 0.20                                  # team-size tilt: 2v4 equal-quality -> E ~= 46.5%

# Game config: game -> (GameType, mult = multiple of Quest stakes). This is
# v2's own copy of v1's GAME_CONFIG - edit types/multipliers here freely;
# parse_results.py keeps its own dict and v1 output is unaffected. A game
# played but missing from this dict raises KeyError.
GAME_CONFIG = {
    "Love Letter": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Cash n Guns": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Carcassone": (GameType.INDIVIDUAL_RANKED, 1.0),
    "Masquerade": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Monopoly Deal": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Night of the Ninja": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Clank": (GameType.INDIVIDUAL_WINNER, 1.0),

    "Coup": (GameType.INDIVIDUAL_WINNER, 1.50),
    "Shifty Eyed Spies": (GameType.INDIVIDUAL_WINNER, 1.50),
    "Uno": (GameType.INDIVIDUAL_WINNER, 1.00),
    "Bang": (GameType.INDIVIDUAL_WINNER, 1.50),
    "Exploding Kittens": (GameType.INDIVIDUAL_WINNER, 1.00),
    "Secret Hitler": (GameType.TEAM_BALANCED, 1.0),
    "Avalon": (GameType.TEAM_BALANCED, 1.0),
    "Quest": (GameType.TEAM_BALANCED, 1.0),
    "Wavelength": (GameType.TEAM_BALANCED, 1.0),
    "Codenames": (GameType.TEAM_BALANCED, 1.0),
    "Incan Gold": (GameType.INDIVIDUAL_RANKED, 1.0),
    "Camel Up": (GameType.INDIVIDUAL_RANKED, 1.0),
}


# --- Scoring Logic ---


def sigma(games_played: int) -> float:
    return SIGMA_FLOOR + (SIGMA0 - SIGMA_FLOOR) * math.exp(-games_played / TAU)


def strength(mu: float) -> float:
    return 10.0 ** ((mu - 100.0) / SCALE)


def p_win(mu_a: float, mu_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((mu_b - mu_a) / SCALE))


def team_quality(mus: List[float], size: int) -> float:
    """Harmonic mean of member strengths, tilted by team size."""
    harmonic = len(mus) / sum(1.0 / strength(m) for m in mus)
    return harmonic * (size ** EPS)


def team_rating(mus: List[float], size: int) -> float:
    """A team's collective rating: its quality converted back to the elo scale."""
    return 100.0 + SCALE * math.log10(team_quality(mus, size))


def team_of(player: str, game: GameResult) -> int:
    for i, team in enumerate(game.teams):
        if player in team:
            return i
    return -1


def rank_of(player: str, game: GameResult) -> int:
    return game.ranks[team_of(player, game)]


def game_breakdown(
    game: GameResult, mu: Dict[str, float], games_played: Dict[str, int]
):
    """One game fully decomposed per player: actual/expected scores,
    k-factor, surprise, raw delta and the zero-sum renormed delta. Feeds
    both the engine and the debug history. Returns (details, meta)."""
    g_type, mult = GAME_CONFIG[game.game_name]
    players = [p for team in game.teams for p in team]

    actual: Dict[str, float] = {}
    expected: Dict[str, float] = {}

    if g_type in (GameType.TEAM_BALANCED, GameType.TEAM_UNBALANCED):
        # Team model: pairwise Elo vs the opposing team's collective rating
        # (harmonic mean of strengths, size-tilted) - individual elo
        # differentiates deltas within a team.
        winner_teams = sum(1 for r in game.ranks if r == 0)
        for i, team in enumerate(game.teams):
            a_team = (1.0 / winner_teams) if game.ranks[i] == 0 else 0.0
            opp_ratings = [
                team_rating([mu[o] for o in t], len(t))
                for j, t in enumerate(game.teams)
                if j != i
            ]
            for p in team:
                actual[p] = a_team
                expected[p] = sum(p_win(mu[p], r) for r in opp_ratings) / len(opp_ratings)
    else:
        # Pairwise model: 1.0 beat / 0.5 tied rank / 0.0 lost, vs everyone.
        for p in players:
            t_p, r_p = team_of(p, game), rank_of(p, game)
            results, exps = [], []
            for o in players:
                if o == p or team_of(o, game) == t_p:
                    continue
                w = 1.0 if r_p < rank_of(o, game) else (0.0 if r_p > rank_of(o, game) else 0.5)
                results.append(w)
                exps.append(p_win(mu[p], mu[o]))
            actual[p] = sum(results) / len(results)
            expected[p] = sum(exps) / len(exps)

    details = {}
    for p in players:
        k = K_PROV if games_played.get(p, 0) < PROV_GAMES else K_STD
        x = actual[p] - expected[p]
        surprise = x * abs(2.0 * x) ** UPSET_AMP
        details[p] = {
            "mu": mu[p],                      # rating before the game
            "games": games_played.get(p, 0),  # games before
            "k": k,
            "rank": rank_of(p, game),
            "A": actual[p],
            "E": expected[p],
            "x": x,
            "surprise": surprise,
            "raw": k * mult * surprise,       # pre-renorm delta
        }

    # Force zero-sum: subtract the mean raw delta across participants.
    mean_raw = sum(d["raw"] for d in details.values()) / len(details)
    for d in details.values():
        d["delta"] = d["raw"] - mean_raw
    return details, {"type": g_type, "mult": mult}


def calc_deltas(
    game: GameResult, mu: Dict[str, float], games_played: Dict[str, int]
) -> Dict[str, float]:
    """Final zero-sum renormed deltas for one game."""
    details, _ = game_breakdown(game, mu, games_played)
    return {p: d["delta"] for p, d in details.items()}


# --- Engine ---


class RankingCalculatorV2:
    """Mirrors parse_results.RankingCalculator; stats["score"] is the
    conservative display score (mu - sigma)."""

    def __init__(self):
        self.mu = defaultdict(lambda: 100.0)
        self.games_played = defaultdict(int)
        self.stats = defaultdict(lambda: {"score": 100.0, "wins": 0, "losses": 0})
        self.game_rankings = defaultdict(
            lambda: defaultdict(lambda: {"score": 0.0, "wins": 0, "losses": 0})
        )
        self.history = []
        self.log = []
        self.max_swing = 0.0

    def display_score(self, player: str) -> float:
        return self.mu[player] - sigma(self.games_played[player])

    def process_games(self, games: List[GameResult]):
        for game in games:
            details, meta = game_breakdown(game, self.mu, self.games_played)
            deltas = {p: d["delta"] for p, d in details.items()}

            for p, change in deltas.items():
                rank = details[p]["rank"]
                self.mu[p] += change
                self.games_played[p] += 1

                self.stats[p]["score"] = self.display_score(p)
                if rank == 0:
                    self.stats[p]["wins"] += 1
                else:
                    self.stats[p]["losses"] += 1

                gs = self.game_rankings[game.game_name][p]
                gs["score"] += change
                if rank == 0:
                    gs["wins"] += 1
                else:
                    gs["losses"] += 1

            self.max_swing = max(self.max_swing, max(abs(d) for d in deltas.values()))

            snapshot = {"Date": game.date}
            for p, s in self.stats.items():
                snapshot[p] = s["score"]
            self.history.append(snapshot)
            self.log.append((game, details, meta))


# --- Debug history writer ---


def write_history(calc: RankingCalculatorV2, path: str) -> None:
    """game_history_v2.txt: every game as a per-player table decomposing
    each delta into its components (column legend at the top of the file)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"columns: mu = rating before | g = games before | K = k-factor "
            f"({K_PROV:.0f} if g < {PROV_GAMES}, else {K_STD:.0f})\n"
            f"         r = rank (0 = win) | A = actual | E = expected | x = A - E"
            f" | f(x) = x*|2x|^{UPSET_AMP} | raw = K * mult * f(x)\n"
            f"         delta = raw - renorm (zero-sum) | mu+ = rating after"
            f" | disp = mu+ - sigma(g+1) = leaderboard score after\n\n"
        )
        for i, (game, details, meta) in enumerate(calc.log, start=1):
            f.write(game.to_string() + "\n")
            f.write(f"  #{i:>3}  {meta['type'].value}  mult {meta['mult']:.2f}\n")

            if meta["type"] in (GameType.TEAM_BALANCED, GameType.TEAM_UNBALANCED):
                for ti, team in enumerate(game.teams):
                    rating = team_rating(
                        [details[p]["mu"] for p in team], len(team)
                    )
                    members = ", ".join(
                        f"{p} {details[p]['mu']:.1f}" for p in team
                    )
                    wl = "W" if game.ranks[ti] == 0 else "L"
                    f.write(
                        f"    T{ti} {wl} rank {game.ranks[ti]}  "
                        f"rating {rating:6.1f}  {members}\n"
                    )

            f.write(
                f"    {'player':<16}{'mu':>6}{'g':>4}{'K':>5}{'r':>3}"
                f"{'A':>6}{'E':>6}{'x':>6}{'f(x)':>7}{'raw':>7}"
                f"{'delta':>7}{'mu+':>7}{'disp':>7}\n"
            )
            for p in [p for team in game.teams for p in team]:
                d = details[p]
                mu_after = d["mu"] + d["delta"]
                disp = mu_after - sigma(d["games"] + 1)
                bar = ("█" if d["delta"] >= 0 else "░") * min(
                    12, round(abs(d["delta"]))
                )
                f.write(
                    f"    {p:<16}{d['mu']:>6.1f}{d['games']:>4d}{d['k']:>5.1f}"
                    f"{d['rank']:>3d}{d['A']:>6.3f}{d['E']:>6.3f}{d['x']:>6.3f}"
                    f"{d['surprise']:>7.3f}{d['raw']:>7.2f}{d['delta']:>+7.2f}"
                    f"{mu_after:>7.1f}{disp:>7.1f}  {bar}\n"
                )

            raw_sum = sum(d["raw"] for d in details.values())
            renorm = raw_sum / len(details)
            total = sum(d["delta"] for d in details.values())
            f.write(
                f"    sum(delta) {total:+.2f}   renorm {renorm:+.2f}/player"
                f" (raw sum {raw_sum:+.2f})\n\n"
            )


# --- Comparison / calibration report ---


def print_report(v2: RankingCalculatorV2, v1_games: List[GameResult]):
    v1 = RankingCalculator()
    v1.process_games(v1_games)

    v1_scores = {p: s["score"] for p, s in v1.stats.items()}
    v2_scores = {p: v2.display_score(p) for p in v2.mu}
    v1_rank = {p: i for i, (p, _) in enumerate(
        sorted(v1_scores.items(), key=lambda kv: -kv[1]), start=1)}
    v2_sorted = sorted(v2_scores.items(), key=lambda kv: -kv[1])

    print(f"{'rank':>4}  {'player':<16}{'games':>5}{'W-L':>8}"
          f"{'old':>8}{'new':>8}{'diff':>7}{'move':>6}")
    for i, (p, new) in enumerate(v2_sorted, start=1):
        old = v1_scores.get(p)
        old_s = f"{old:.1f}" if old is not None else "-"
        diff_s = f"{new - old:+.1f}" if old is not None else "-"
        move_s = f"{v1_rank[p] - i:+d}" if old is not None else "new"
        print(f"{i:>4}  {p:<16}{v2.games_played[p]:>5}"
              f"{v2.stats[p]['wins']}-{v2.stats[p]['losses']:>3}"
              f"{old_s:>8}{new:>8.1f}{diff_s:>7}{move_s:>6}")

    scores = [s for _, s in v2_sorted]
    top5_games = [v2.games_played[p] for p, _ in v2_sorted[:5]]
    drift = sum(v2.mu.values()) - 100.0 * len(v2.mu)
    print(f"\ncalibration:")
    print(f"  max single-game swing : {v2.max_swing:.2f}  (target < 6.0; v1 worst-case 6.0)")
    print(f"  min games in top 5    : {min(top5_games)}  (target >= 5)")
    print(f"  display spread        : {scores[-1]:.1f} .. {scores[0]:.1f} "
          f"(range {scores[0] - scores[-1]:.1f}, target ~50)")
    print(f"  zero-sum drift        : {drift:+.6f}  (target 0)")


# --- Main Execution ---


if __name__ == "__main__":
    games = parse_game_data("results.txt")

    calc = RankingCalculatorV2()
    if games:
        calc.process_games(games)
        write_history(calc, "game_history_v2.txt")

        ResultFormatter.plot_rankings_over_time(
            calc, calc.stats, output_file="rankings_v2.png"
        )

        md_content = ResultFormatter.generate_markdown(calc.stats, calc.game_rankings)
        md_content = md_content.replace("rankings.png", "rankings_v2.png")
        with open("README_v2.md", "w", encoding="utf-8") as f:
            f.write(md_content)

        print_report(calc, games)
