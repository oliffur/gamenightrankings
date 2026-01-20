import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Any
import os

# --- Configuration ---


class GameType(Enum):
    TEAM_UNBALANCED = "team uneven"
    TEAM_BALANCED = "team even"
    INDIVIDUAL_WINNER = "winner takes all"
    INDIVIDUAL_RANKED = "ranked"

# Updated CONFIG: Maps Name -> (GameType, Multiplier)
GAME_CONFIG = {
    "Incan Gold": (GameType.INDIVIDUAL_RANKED, 1.0),
    "Love Letter": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Shifty Eyed Spies": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Cash n Guns": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Carcassone": (GameType.INDIVIDUAL_RANKED, 1.0),
    "Coup": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Masquerade": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Camel Up": (GameType.INDIVIDUAL_RANKED, 1.0),
    "Monopoly Deal": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Night of the Ninja": (GameType.INDIVIDUAL_WINNER, 1.0),
    "Clank": (GameType.INDIVIDUAL_WINNER, 1.0),

    "Bang": (GameType.INDIVIDUAL_WINNER, 0.60),
    "Exploding Kittens": (GameType.INDIVIDUAL_WINNER, 0.30),

    "Secret Hitler": (GameType.TEAM_BALANCED, 1.0),
    "Avalon": (GameType.TEAM_BALANCED, 1.0),
    "Quest": (GameType.TEAM_BALANCED, 1.0),
    "Wavelength": (GameType.TEAM_BALANCED, 1.0),
    "Codenames": (GameType.TEAM_BALANCED, 1.0),
}

@dataclass
class GameResult:
    date: str
    game_name: str
    teams: List[List[str]]
    ranks: List[int]

    def to_string(self) -> str:
        teams_str = ";".join([",".join(t) for t in self.teams])
        ranks_str = ";".join(map(str, self.ranks))
        return f"{self.date}|{self.game_name}|{teams_str}|{ranks_str}"


# --- Scoring Logic ---


def get_player_context(player: str, game: GameResult):
    for i, team in enumerate(game.teams):
        if player in team:
            return i, game.ranks[i], len(team)
    return None, None, None

def calc_base_bonus(player: str, game: GameResult) -> float:
    # Unpack GameType and Multiplier (Default to 1.0 if not found)
    g_type, multiplier = GAME_CONFIG[game.game_name]
    idx, rank, size = get_player_context(player, game)
    base_score = 0.0

    if g_type == GameType.TEAM_UNBALANCED:
        # Calculate total count of winners and losers for context
        win_count = sum(len(t) for j, t in enumerate(game.teams) if game.ranks[j] == 0)
        loss_count = sum(len(t) for j, t in enumerate(game.teams) if game.ranks[j] != 0)

        if rank == 0:
            # Reward is shared based on difficulty.
            # If 3 beat 1, reward is small (1/3). If 1 beats 3, reward is big (3/1).
            base_score = float(loss_count) / float(max(1, win_count))
        else:
            # Fixed penalty. Prevents the "lose -3 points because opponent had 3 people" issue.
            base_score = -1.0

    elif g_type == GameType.TEAM_BALANCED:
        base_score = 1.0 if rank == 0 else -1.0

    elif g_type == GameType.INDIVIDUAL_WINNER:
        if rank == 0:
            # Calculate total people who lost
            total_beaten = sum(len(t) for j, t in enumerate(game.teams) if game.ranks[j] != 0)

            # Count how many players share the winning rank (rank 0)
            winner_count = sum(len(t) for j, t in enumerate(game.teams) if game.ranks[j] == 0)

            # Divide total points available by the number of winners
            base_score = float(total_beaten) / float(max(1, winner_count))
        else:
            base_score = -1.0

    elif g_type == GameType.INDIVIDUAL_RANKED:
        beaten = sum(
            len(t) for j, t in enumerate(game.teams) if game.ranks[j] > rank
        )
        lost_to = sum(
            len(t) for j, t in enumerate(game.teams) if game.ranks[j] < rank
        )
        
        # Count how many players share this specific rank (including self)
        tied_count = sum(
            len(t) for j, t in enumerate(game.teams) if game.ranks[j] == rank
        )
        
        # Original: base_score = float(beaten - lost_to)
        # New: Divide by tied_count (e.g., if 3 winners beat 5 losers, score is 5/3)
        base_score = float(beaten - lost_to) / float(max(1, tied_count))

    # Apply the multiplier
    return base_score * multiplier

def calc_upset_bonus(
    player: str, game: GameResult, ratings_before: Dict[str, float]
) -> float:
    """
    Calculates upset bonus based on ratings immediately before this game.
    """
    g_type, _ = GAME_CONFIG[game.game_name]
    idx, rank, _ = get_player_context(player, game)
    p_rating = ratings_before.get(player, 100.0)

    if g_type in [GameType.TEAM_BALANCED, GameType.TEAM_UNBALANCED]:
        bonus = 0.0
        for i, team in enumerate(game.teams):
            if i == idx:
                continue
            opp_ratings = [ratings_before.get(p, 100.0) for p in team]
            if not opp_ratings:
                continue

            # Use median opponent rating for the upset check
            median_opp = sorted(opp_ratings)[len(opp_ratings) // 2]

            if rank == 0 and median_opp > p_rating:
                bonus += 0.5
            elif rank != 0 and median_opp < p_rating:
                bonus -= 0.5
        return bonus
    return 0.0


# --- Engine ---


class RankingCalculator:
    def __init__(self):
        self.stats = defaultdict(
            lambda: {"score": 100.0, "wins": 0, "losses": 0}
        )
        self.game_rankings = defaultdict(
            lambda: defaultdict(lambda: {"score": 0.0, "wins": 0, "losses": 0})
        )
        self.history = []
        self.log = []

    def process_games(self, games: List[GameResult]):
        for game in games:
            # Take a snapshot of ratings BEFORE this specific game starts
            ratings_before_game = {
                p: data["score"] for p, data in self.stats.items()
            }

            deltas = {}
            game_players = [p for team in game.teams for p in team]

            for p in game_players:
                idx, rank, _ = get_player_context(p, game)

                # Calculate change using the ratings from just before this game
                change = calc_base_bonus(p, game) + calc_upset_bonus(
                    p, game, ratings_before_game
                )

                # Experience bonus for newer players
                total_games = self.stats[p]["wins"] + self.stats[p]["losses"]
                if total_games < 50:
                    change += 0.2

                # Update Global Stats
                self.stats[p]["score"] += change
                if rank == 0:
                    self.stats[p]["wins"] += 1
                else:
                    self.stats[p]["losses"] += 1

                # Update Game Specific Stats
                gs = self.game_rankings[game.game_name][p]
                gs["score"] += change
                if rank == 0:
                    gs["wins"] += 1
                else:
                    gs["losses"] += 1

                deltas[p] = change

            # Record history for plotting
            snapshot = {"Date": game.date}
            for p, s in self.stats.items():
                snapshot[p] = s["score"]
            self.history.append(snapshot)

            # Record log for game_history.txt
            self.log.append((game, deltas))


class ResultFormatter:
    @staticmethod
    def get_history_dataframe(
        calculator: RankingCalculator, players: List[str]
    ) -> pd.DataFrame:
        if not calculator.history:
            return pd.DataFrame()

        df = pd.DataFrame(calculator.history)

        # Keep only the last game result for each date to ensure the plot
        # shows the final standing of that day.
        df = df.drop_duplicates(subset="Date", keep="last")

        df = df.set_index("Date")
        cols = [p for p in players if p in df.columns]
        return df[cols]

    @staticmethod
    def generate_markdown(
        overall_stats: Dict[str, Any], game_rankings: Dict[str, Any]
    ) -> str:
        markdown_lines = []
        markdown_lines.append("![Image](https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTTtNPDAP25nEt0xnLCVd3zb1TM6nUw87_Hhg&s)")
        markdown_lines.append("")

        # 1. Overall Rankings
        markdown_lines.append("### Overall Rankings")
        markdown_lines.append("")
        markdown_lines.append("| Player | Score | Wins | Losses | Win % |")
        markdown_lines.append("| --- | --- | --- | --- | --- |")

        sorted_players = sorted(
            overall_stats.items(), key=lambda x: x[1]["score"], reverse=True
        )
        for player, stats in sorted_players:
            total = stats["wins"] + stats["losses"]
            win_pct = stats["wins"] / max(1, total)
            markdown_lines.append(
                f"| {player} | {stats['score']:.2f} | {stats['wins']} | {stats['losses']} | {win_pct:.0%} |"
            )

        markdown_lines.append("")
        markdown_lines.append("### Rankings over Time")
        markdown_lines.append("")
        markdown_lines.append("![Image](rankings.png)")
        markdown_lines.append("")

        # 2. Per-Game Rankings (No score column)
        for game_name in sorted(game_rankings.keys()):
            stats_dict = game_rankings[game_name]
            markdown_lines.append(f"### {game_name}")
            markdown_lines.append("")
            markdown_lines.append("| Player | Wins | Losses | Win % |")
            markdown_lines.append("| --- | --- | --- | --- |")

            # Sort by the internal game score to maintain ranking order
            game_sorted = sorted(
                stats_dict.items(), key=lambda x: x[1]["score"], reverse=True
            )

            for player, row in game_sorted:
                total = row["wins"] + row["losses"]
                win_pct = row["wins"] / max(1, total)
                markdown_lines.append(
                    f"| {player} | {int(row['wins'])} | {int(row['losses'])} | {win_pct:.0%} |"
                )

            markdown_lines.append("")

        return "\n".join(markdown_lines)

    @staticmethod
    def plot_rankings_over_time(
        calculator: RankingCalculator,
        overall_stats: Dict[str, Any],
        output_file: str = "rankings.png",
    ):
        sorted_players = sorted(
            overall_stats.items(), key=lambda x: x[1]["score"], reverse=True
        )
        top_25_players = [player for player, _ in sorted_players[:25]]

        df = ResultFormatter.get_history_dataframe(calculator, top_25_players)
        if df.empty:
            return

        plt.style.use("ggplot")
        plt.figure(figsize=(14, 8))

        for player in top_25_players:
            if player in df.columns:
                plt.plot(
                    df.index,
                    df[player],
                    marker="o",
                    markersize=4,
                    linewidth=2,
                    label=player,
                )

        plt.title("Top 25 Player Rankings (End of Day)")
        plt.xlabel("Date")
        plt.ylabel("Score")
        plt.xticks(rotation=45)
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.tight_layout()
        plt.grid(True, alpha=0.3)
        plt.savefig(output_file, dpi=300, bbox_inches="tight")
        plt.close()


# --- Main Execution ---


def parse_game_data(file_path: str) -> List[GameResult]:
    results = []
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("DATE"):
                continue
            try:
                parts = line.split("|")
                teams = [t.split(",") for t in parts[2].split(";")]
                ranks = [int(r) for r in parts[3].split(";")]
                results.append(GameResult(parts[0], parts[1], teams, ranks))
            except:
                continue
    return results


if __name__ == "__main__":
    calc = RankingCalculator()
    games = parse_game_data("results.txt")

    if games:
        calc.process_games(games)

        # 1. Save detailed delta log
        with open("game_history.txt", "w", encoding="utf-8") as f:
            for game, deltas in calc.log:
                f.write(game.to_string() + "\n")
                sorted_p = sorted(deltas.keys())
                delta_str = ", ".join(
                    [
                        f"{p}: {'+' if deltas[p] >= 0 else ''}{deltas[p]:.2f}"
                        for p in sorted_p
                    ]
                )
                f.write(delta_str + "\n")

        # 2. Generate Plot
        ResultFormatter.plot_rankings_over_time(calc, calc.stats)

        # 3. Save Markdown Report
        md_content = ResultFormatter.generate_markdown(
            calc.stats, calc.game_rankings
        )
        with open("README.md", "w", encoding="utf-8") as f:
            f.write(md_content)
