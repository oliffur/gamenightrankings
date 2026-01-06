import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Any

# --- Configuration & Types ---

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
    """Helper to find player's team index, rank, and size."""
    for i, team in enumerate(game.teams):
        if player in team:
            return i, game.ranks[i], len(team)
    return None, None, None

def calc_base_bonus(player: str, game: GameResult) -> float:
    g_type = GAME_CONFIG.get(game.game_name)
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
    g_type = GAME_CONFIG.get(game.game_name)
    idx, rank, _ = get_player_context(player, game)
    p_rating = ratings.get(player, 100.0)

    if g_type in [GameType.TEAM_BALANCED, GameType.TEAM_UNBALANCED]:
        bonus = 0.0
        for i, team in enumerate(game.teams):
            if i == idx: continue
            opp_ratings = sorted([ratings.get(p, 100.0) for p in team])
            median_opp = opp_ratings[len(opp_ratings)//2]
            if rank == 0 and median_opp > p_rating: bonus += 0.5
            elif rank != 0 and median_opp < p_rating: bonus -= 0.5
        return bonus

    if g_type == GameType.INDIVIDUAL_WINNER:
        if rank == 0:
            losers = [p for j, t in enumerate(game.teams) if j != idx for p in t]
            return 0.5 * sum(1 for lp in losers if ratings.get(lp, 100.0) > p_rating)
        
        winner = game.teams[game.ranks.index(0)][0]
        return -0.5 if ratings.get(winner, 100.0) < p_rating else 0.0

    if g_type == GameType.INDIVIDUAL_RANKED:
        worse = [p for j, t in enumerate(game.teams) if game.ranks[j] > rank for p in t]
        better = [p for j, t in enumerate(game.teams) if game.ranks[j] < rank for p in t]
        bonus = sum(1 for p_opp in worse if ratings.get(p_opp, 100.0) > p_rating)
        penalty = sum(1 for p_opp in better if ratings.get(p_opp, 100.0) < p_rating)
        return 0.5 * (bonus - penalty)

    return 0.0

# --- Core Engine ---

class RankingEngine:
    def __init__(self):
        self.stats = defaultdict(lambda: {"score": 100.0, "wins": 0, "losses": 0, "games": 0})
        self.history = [] # List of (date, Dict[player, score])

    def process_games(self, games: List[GameResult]):
        for game in games:
            current_ratings = {p: data["score"] for p, data in self.stats.items()}
            
            # Update players in this specific game
            game_players = [p for team in game.teams for p in team]
            for p in game_players:
                idx, rank, _ = get_player_context(p, game)
                
                # Apply scoring components
                self.stats[p]["score"] += calc_base_bonus(p, game)
                self.stats[p]["score"] += calc_upset_bonus(p, game, current_ratings)
                
                if self.stats[p]["games"] < 50:
                    self.stats[p]["score"] += 0.2
                
                self.stats[p]["games"] += 1
                if rank == 0: self.stats[p]["wins"] += 1
                else: self.stats[p]["losses"] += 1
            
            # Record history snapshot
            self.history.append((game.date, {p: d["score"] for p, d in self.stats.items()}))

    def get_stats_df(self) -> pd.DataFrame:
        df = pd.DataFrame.from_dict(self.stats, orient='index')
        df['win_pct'] = (df['wins'] / df['games'] * 100).round(1)
        return df.sort_values("score", ascending=False)

# --- Reporting & Visualization ---

def generate_reports(engine: RankingEngine):
    df = engine.get_stats_df()
    
    # 1. Plotting
    plt.figure(figsize=(12, 6))
    top_players = df.head(15).index
    for player in top_players:
        dates = [h[0] for h in engine.history]
        scores = [h[1].get(player, 100.0) for h in engine.history]
        plt.plot(dates, scores, label=player, marker='o', markersize=3)
    
    plt.xticks(rotation=45)
    plt.legend(bbox_to_anchor=(1.05, 1))
    plt.tight_layout()
    plt.savefig("rankings.png")
    
    # 2. Markdown Generation
    md = ["### Overall Rankings\n", "| Player | Score | Wins | Losses | Win % |", "| --- | --- | --- | --- | --- |"]
    for name, row in df.iterrows():
        md.append(f"| {name} | {row['score']:.2f} | {int(row['wins'])} | {int(row['losses'])} | {row['win_pct']:.0f}% |")
    
    with open("README.md", "w") as f:
        f.write("\n".join(md))

def parse_file(path: str) -> List[GameResult]:
    results = []
    with open(path, "r") as f:
        for line in f:
            if line.startswith("DATE") or not line.strip(): continue
            parts = line.strip().split("|")
            teams = [t.split(",") for t in parts[2].split(";")]
            ranks = [int(r) for r in parts[3].split(";")]
            results.append(GameResult(parts[0], parts[1], teams, ranks))
    return results

if __name__ == "__main__":
    engine = RankingEngine()
    game_data = parse_file("results.txt")
    engine.process_games(game_data)
    generate_reports(engine)
    print(engine.get_stats_df().head(10))
