import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple
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
    p_rating = ratings.get(player, 100.0)
    
    if g_type in [GameType.TEAM_BALANCED, GameType.TEAM_UNBALANCED]:
        bonus = 0.0
        for i, team in enumerate(game.teams):
            if i == idx: continue
            opp_ratings = sorted([ratings.get(p, 100.0) for p in team])
            median_opp = opp_ratings[len(opp_ratings)//2] if opp_ratings else 100.0
            if rank == 0 and median_opp > p_rating: bonus += 0.5
            elif rank != 0 and median_opp < p_rating: bonus -= 0.5
        return bonus
    return 0.0

# --- Engine ---

class RankingCalculator:
    def __init__(self):
        self.stats = defaultdict(lambda: {"score": 100.0, "wins": 0, "losses": 0, "games": 0})
        self.game_specific_stats = defaultdict(lambda: defaultdict(lambda: {"score": 0.0, "wins": 0, "games": 0}))
        self.history_log = [] # List of (GameResult, deltas_dict)
        self.score_history = defaultdict(list) # For plotting

    def calculate_rankings(self, games: List[GameResult]):
        for game in games:
            # Snapshot of ratings before this game
            ratings_before = {p: self.stats[p]["score"] for p in self.stats}
            deltas = {}
            
            game_players = [p for team in game.teams for p in team]
            for p in game_players:
                idx, rank, _ = get_player_context(p, game)
                
                # Calculate changes
                change = calc_base_bonus(p, game) + calc_upset_bonus(p, game, ratings_before)
                if self.stats[p]["games"] < 50:
                    change += 0.2
                
                # Update Global Stats
                self.stats[p]["score"] += change
                self.stats[p]["games"] += 1
                if rank == 0: self.stats[p]["wins"] += 1
                else: self.stats[p]["losses"] += 1
                
                # Update Game-Specific Stats
                gs = self.game_specific_stats[game.game_name][p]
                gs["score"] += change
                gs["games"] += 1
                if rank == 0: gs["wins"] += 1
                
                deltas[p] = change

            # Record history for plotting (all players)
            for p in set(list(self.stats.keys()) + game_players):
                self.score_history[p].append(self.stats[p]["score"])
            
            self.history_log.append((game, deltas))

    def save_game_history(self, filename: str = "game_history.txt"):
        with open(filename, "w", encoding="utf-8") as f:
            for game, deltas in self.history_log:
                f.write(game.to_string() + "\n")
                # Sort players alphabetically for the delta line
                sorted_players = sorted(deltas.keys())
                delta_str = ", ".join([f"{p}: {'+' if deltas[p] >= 0 else ''}{deltas[p]:.2f}" for p in sorted_players])
                f.write(delta_str + "\n")

    def save_markdown_report(self, filename: str = "rankings.md"):
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# 🏆 Board Game Rankings\n\n")
            
            # Global Table
            f.write("## Overall Leaderboard\n")
            df = self.get_stats_df()
            f.write(df.to_markdown() + "\n\n")
            
            # Game Specific Tables
            f.write("## Rankings by Game\n")
            for game_name in sorted(self.game_specific_stats.keys()):
                f.write(f"### {game_name}\n")
                g_data = []
                for p, s in self.game_specific_stats[game_name].items():
                    g_data.append({
                        "Player": p,
                        "Net Score": round(s["score"], 2),
                        "Wins": s["wins"],
                        "Games": s["games"],
                        "Win %": f"{(s['wins']/s['games']*100):.1f}%"
                    })
                gdf = pd.DataFrame(g_data).sort_values("Net Score", ascending=False)
                f.write(gdf.to_markdown(index=False) + "\n\n")

    def generate_chart(self, filename: str = "player_stats.png"):
        plt.figure(figsize=(12, 7))
        for player, scores in self.score_history.items():
            plt.plot(scores, label=player, marker='o', markersize=4)
        
        plt.title("Player Rating Progression")
        plt.xlabel("Games Played")
        plt.ylabel("Rating Score")
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        plt.savefig(filename)
        print(f"Chart saved as {filename}")

    def get_stats_df(self) -> pd.DataFrame:
        data = []
        for p, s in self.stats.items():
            data.append({
                "Player": p,
                "Rating": round(s["score"], 2),
                "Wins": s["wins"],
                "Losses": s["losses"],
                "Total": s["games"],
                "Win %": f"{(s['wins']/s['games']*100):.1f}%"
            })
        return pd.DataFrame(data).sort_values("Rating", ascending=False)

# --- Main Execution ---

def parse_game_data(file_path: str) -> List[GameResult]:
    results = []
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("DATE"): continue
            try:
                parts = line.split("|")
                teams = [t.split(",") for t in parts[2].split(";")]
                ranks = [int(r) for r in parts[3].split(";")]
                results.append(GameResult(parts[0], parts[1], teams, ranks))
            except Exception as e:
                print(f"Skipping malformed line: {line} ({e})")
    return results

if __name__ == "__main__":
    calc = RankingCalculator()
    games = parse_game_data("results.txt")
    
    if games:
        calc.calculate_rankings(games)
        calc.save_game_history("game_history.txt")
        calc.save_markdown_report("rankings.md")
        calc.generate_chart("player_stats.png")
        
        print("\n--- Current Standings ---")
        print(calc.get_stats_df().to_string(index=False))
    else:
        print("No game data found to process.")
