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

GAME_CONFIG = {
    "Bang": GameType.TEAM_UNBALANCED, "Secret Hitler": GameType.TEAM_BALANCED,
    "Wavelength": GameType.TEAM_BALANCED, "Codenames": GameType.TEAM_BALANCED,
    "Incan Gold": GameType.INDIVIDUAL_RANKED, "Exploding Kittens": GameType.INDIVIDUAL_WINNER,
    "Love Letter": GameType.INDIVIDUAL_WINNER, "Shifty Eyed Spies": GameType.INDIVIDUAL_WINNER,
    "Cash n Guns": GameType.INDIVIDUAL_WINNER, "Carcassone": GameType.INDIVIDUAL_RANKED,
    "Coup": GameType.INDIVIDUAL_WINNER, "Masquerade": GameType.INDIVIDUAL_WINNER,
    "Camel Up": GameType.INDIVIDUAL_RANKED, "Monopoly Deal": GameType.INDIVIDUAL_WINNER,
    "Night of the Ninja": GameType.INDIVIDUAL_WINNER, "Clank": GameType.INDIVIDUAL_WINNER,
    "Avalon": GameType.TEAM_BALANCED, "Quest": GameType.TEAM_BALANCED,
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
    g_type = GAME_CONFIG.get(game.game_name, GameType.TEAM_BALANCED)
    idx, rank, size = get_player_context(player, game)
    if g_type == GameType.TEAM_UNBALANCED:
        if rank == 0: return 1.0
        win_size = len(game.teams[game.ranks.index(0)])
        return -(win_size / size)
    if g_type == GameType.TEAM_BALANCED:
        return 1.0 if rank == 0 else -1.0
    if g_type == GameType.INDIVIDUAL_WINNER:
        if rank == 0:
            return float(sum(len(t) for j, t in enumerate(game.teams) if j != idx))
        return -1.0
    if g_type == GameType.INDIVIDUAL_RANKED:
        beaten = sum(len(t) for j, t in enumerate(game.teams) if game.ranks[j] > rank)
        lost_to = sum(len(t) for j, t in enumerate(game.teams) if game.ranks[j] < rank)
        return float(beaten - lost_to)
    return 0.0

def calc_upset_bonus(player: str, game: GameResult, ratings: Dict[str, float]) -> float:
    g_type = GAME_CONFIG.get(game.game_name, GameType.TEAM_BALANCED)
    idx, rank, _ = get_player_context(player, game)
    # Default to 100.0 if player hasn't been seen in previous days
    p_rating = ratings.get(player, 100.0)
    
    if g_type in [GameType.TEAM_BALANCED, GameType.TEAM_UNBALANCED]:
        bonus = 0.0
        for i, team in enumerate(game.teams):
            if i == idx: continue
            opp_ratings = [ratings.get(p, 100.0) for p in team]
            if not opp_ratings: continue
            
            # Use median opponent rating for the upset check
            median_opp = sorted(opp_ratings)[len(opp_ratings)//2]
            
            if rank == 0 and median_opp > p_rating: bonus += 0.5
            elif rank != 0 and median_opp < p_rating: bonus -= 0.5
        return bonus
    return 0.0

# --- Engine ---

class RankingCalculator:
    def __init__(self):
        self.stats = defaultdict(lambda: {"score": 100.0, "wins": 0, "losses": 0})
        self.game_rankings = defaultdict(lambda: defaultdict(lambda: {"score": 0.0, "wins": 0, "losses": 0}))
        self.history = []
        self.log = []

    def process_games(self, games: List[GameResult]):
        current_date = None
        ratings_at_start_of_day = {}

        for game in games:
            # Update the reference ratings only when the date changes
            if game.date != current_date:
                current_date = game.date
                ratings_at_start_of_day = {p: data["score"] for p, data in self.stats.items()}

            deltas = {}
            game_players = [p for team in game.teams for p in team]
            
            for p in game_players:
                idx, rank, _ = get_player_context(p, game)
                
                # Calculate change using the static daily ratings for upset bonus
                change = calc_base_bonus(p, game) + calc_upset_bonus(p, game, ratings_at_start_of_day)
                
                # Experience bonus
                total_games = self.stats[p]["wins"] + self.stats[p]["losses"]
                if total_games < 50:
                    change += 0.2
                
                # Update Global Stats
                self.stats[p]["score"] += change
                if rank == 0: self.stats[p]["wins"] += 1
                else: self.stats[p]["losses"] += 1
                
                # Update Game Specific Stats
                gs = self.game_rankings[game.game_name][p]
                gs["score"] += change
                if rank == 0: gs["wins"] += 1
                else: gs["losses"] += 1
                
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
    def get_history_dataframe(calculator: RankingCalculator, players: List[str]) -> pd.DataFrame:
        if not calculator.history:
            return pd.DataFrame()
        df = pd.DataFrame(calculator.history)
        df = df.set_index("Date")
        cols = [p for p in players if p in df.columns]
        return df[cols]

    @staticmethod
    def generate_markdown(overall_stats: Dict[str, Any], game_rankings: Dict[str, Any]) -> str:
        markdown_lines = []
        
        markdown_lines.append("![Image]")
        markdown_lines.append("")
        
        # 1. Overall Rankings (Includes Score)
        markdown_lines.append("### Overall Rankings")
        markdown_lines.append("")
        markdown_lines.append("| Player | Score | Wins | Losses | Win % |")
        markdown_lines.append("| --- | --- | --- | --- | --- |")
        
        sorted_players = sorted(overall_stats.items(), key=lambda x: x[1]["score"], reverse=True)
        for player, stats in sorted_players:
            total = stats["wins"] + stats["losses"]
            win_pct = (stats["wins"] / max(1, total))
            markdown_lines.append(f"| {player} | {stats['score']:.2f} | {stats['wins']} | {stats['losses']} | {win_pct:.0%} |")
        
        markdown_lines.append("")
        markdown_lines.append("### Rankings over Time")
        markdown_lines.append("")
        markdown_lines.append("![Image](rankings.png)")
        markdown_lines.append("")
        
        # 2. Per-Game Rankings (No Score column)
        for game_name in sorted(game_rankings.keys()):
            stats_dict = game_rankings[game_name]
            markdown_lines.append(f"### {game_name}")
            markdown_lines.append("")
            markdown_lines.append("| Player | Wins | Losses | Win % |")
            markdown_lines.append("| --- | --- | --- | --- |")
            
            # Still sort by the internal game score to keep the leaderboard meaningful
            game_sorted = sorted(stats_dict.items(), key=lambda x: x[1]["score"], reverse=True)
            
            for player, row in game_sorted:
                total = row["wins"] + row["losses"]
                win_pct = (row["wins"] / max(1, total))
                markdown_lines.append(f"| {player} | {int(row['wins'])} | {int(row['losses'])} | {win_pct:.0%} |")
            
            markdown_lines.append("")
        
        return "\n".join(markdown_lines)

    @staticmethod
    def plot_rankings_over_time(calculator: RankingCalculator, overall_stats: Dict[str, Any], output_file: str = "rankings.png"):
        sorted_players = sorted(overall_stats.items(), key=lambda x: x[1]["score"], reverse=True)
        top_25_players = [player for player, _ in sorted_players[:25]]
        
        df = ResultFormatter.get_history_dataframe(calculator, top_25_players)
        if df.empty: return
        
        plt.style.use("ggplot")
        plt.figure(figsize=(14, 8))
        
        for player in top_25_players:
            if player in df.columns:
                plt.plot(df.index, df[player], marker='o', markersize=3, label=player)
        
        plt.title("Top 25 Player Rankings Over Time")
        plt.xlabel("Date")
        plt.ylabel("Score")
        plt.xticks(rotation=45)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.grid(True, alpha=0.3)
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()

# --- Main Execution ---

def parse_game_data(file_path: str) -> List[GameResult]:
    results = []
    if not os.path.exists(file_path): return []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("DATE"): continue
            try:
                parts = line.split("|")
                teams = [t.split(",") for t in parts[2].split(";")]
                ranks = [int(r) for r in parts[3].split(";")]
                results.append(GameResult(parts[0], parts[1], teams, ranks))
            except: continue
    return results

if __name__ == "__main__":
    calc = RankingCalculator()
    games = parse_game_data("results.txt")
    
    if games:
        calc.process_games(games)
        
        # Save game_history.txt
        with open("game_history.txt", "w", encoding="utf-8") as f:
            for game, deltas in calc.log:
                f.write(game.to_string() + "\n")
                sorted_p = sorted(deltas.keys())
                delta_str = ", ".join([f"{p}: {'+' if deltas[p] >= 0 else ''}{deltas[p]:.2f}" for p in sorted_p])
                f.write(delta_str + "\n")

        # Generate Plot
        ResultFormatter.plot_rankings_over_time(calc, calc.stats)

        # Save Markdown
        md_content = ResultFormatter.generate_markdown(calc.stats, calc.game_rankings)
        with open("rankings.md", "w", encoding="utf-8") as f:
            f.write(md_content)
            
        print("Processing complete. Files generated: game_history.txt, rankings.md, rankings.png")
    else:
        print("No data found in results.txt")
