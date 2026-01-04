import pandas as pd
from collections import defaultdict
from copy import deepcopy
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import matplotlib.pyplot as plt
from datetime import datetime


# Type aliases for clarity - using Union for Python < 3.10 compatibility
PlayerStats = Dict[str, Union[float, int]]
AllPlayerStats = Dict[str, PlayerStats]
Team = List[str]
Teams = List[Team]
Ranks = List[int]
GameHistory = List[Tuple[str, Dict[str, Dict[str, Union[float, int]]]]]  # Store all game details


class GameType(Enum):
    """Enum for different game types."""
    TEAM_UNBALANCED = "team uneven"
    TEAM_BALANCED = "team even"
    INDIVIDUAL_WINNER = "winner takes all"
    INDIVIDUAL_RANKED = "ranked"


GAME_CONFIG = {
    "Bang": GameType.TEAM_UNBALANCED,
    "Secret Hitler": GameType.TEAM_BALANCED,
    "Codenames": GameType.TEAM_BALANCED,
}


def parse_game_data(file_path: str = "results.txt") -> List['GameResult']:
    """Parse the raw data string into a list of GameResult objects."""
    results = []
    with open(file_path, encoding="ascii") as f:
        for line in f:
            if line.startswith("DATE"):
                continue
            parts = line.split("|")
            if len(parts) != 4:
                raise ValueError("Bad input data")

            date = parts[0]
            game_name = parts[1]
            teams = [t.split(",") for t in parts[2].split(";")]
            ranks = [int(r) for r in parts[3].split(";")]

            results.append(GameResult(date, game_name, teams, ranks))

    return results


@dataclass
class GameResult:
    """Represents a parsed game result from the data string."""

    date: str
    game_name: str
    teams: Teams
    ranks: Ranks
    
    def to_string(self) -> str:
        """Convert GameResult back to the original string format."""
        teams_str = ";".join([",".join(team) for team in self.teams])
        ranks_str = ";".join([str(rank) for rank in self.ranks])
        return f"{self.date}|{self.game_name}|{teams_str}|{ranks_str}"


def calc_base_bonus(
    player: str,
    game: GameResult
) -> float:
    """Calculate base score for a player in a game."""
    game_type = GAME_CONFIG[game.game_name]
    
    # Find player's team index and rank
    player_team_idx = -1
    player_rank = -1
    team_size = 0
    
    for i, team in enumerate(game.teams):
        if player in team:
            player_team_idx = i
            player_rank = game.ranks[i]
            team_size = len(team)
            break
    
    if game_type == GameType.TEAM_UNBALANCED:
        if player_rank == 0:
            return 1.0

        # Find the winning team size
        winner_idx = game.ranks.index(0)
        win_team_size = len(game.teams[winner_idx])
        return -(1.0 * (win_team_size / team_size))

    elif game_type == GameType.TEAM_BALANCED:
        return 1.0 if player_rank == 0 else -1.0

    elif game_type == GameType.INDIVIDUAL_WINNER:
        if player_rank == 0:
            # Gain 1 * number of losers
            win_idx = game.ranks.index(0)
            num_losers = sum(
                len(t) for j, t in enumerate(game.teams) if j != win_idx
            )
            return 1.0 * num_losers
        return -1.0

    elif game_type == GameType.INDIVIDUAL_RANKED:
        num_beaten = sum(
            len(t) for j, t in enumerate(game.teams) if game.ranks[j] > player_rank
        )
        num_lost_to = sum(
            len(t) for j, t in enumerate(game.teams) if game.ranks[j] < player_rank
        )
        return num_beaten - num_lost_to

    return 0.0


def calc_upset_bonus(
    player: str,
    game: GameResult,
    current_ratings: Dict[str, float]
) -> float:
    """Calculate skill gap bonus for a player in a game."""
    game_type = GAME_CONFIG[game.game_name]
    
    # Find player's team index and rank
    player_team_idx = -1
    player_rank = -1
    
    for i, team in enumerate(game.teams):
        if player in team:
            player_team_idx = i
            player_rank = game.ranks[i]
            break
    
    if game_type in [GameType.TEAM_BALANCED, GameType.TEAM_UNBALANCED]:
        player_rating = current_ratings.get(player, 0.0)
        bonus = 0.0
        
        # Check all opposing teams
        for i, team in enumerate(game.teams):
            if i == player_team_idx:
                continue  # Skip player's own team
                
            # Compute median rating of the opposing team
            other_ratings = sorted([current_ratings.get(p, 0.0) for p in team])
            median_opp = other_ratings[len(other_ratings) // 2]
            
            if player_rank == 0:  # Player's team won
                if median_opp > player_rating:
                    bonus += 0.5  # Win bonus for beating higher-rated team
            else:  # Player's team lost
                if median_opp < player_rating:
                    bonus -= 0.5  # Penalty for losing to lower-rated team
        
        return bonus

    elif game_type == GameType.INDIVIDUAL_WINNER:
        if player_rank == 0:
            # 0.5 * (number of losers higher than player)
            win_idx = game.ranks.index(0)
            losers = [p for j, t in enumerate(game.teams) if j != win_idx for p in t]
            higher_count = sum(
                1
                for p_opp in losers
                if current_ratings.get(p_opp, 0.0)
                > current_ratings.get(player, 0.0)
            )
            return 0.5 * higher_count

        # -0.5 if winner was lower rated
        win_idx = game.ranks.index(0)
        winner_team = game.teams[win_idx]
        winner_p = winner_team[0]  # Assuming 1 winner in WTA
        return (
            -0.5
            if current_ratings.get(winner_p, 0.0)
            < current_ratings.get(player, 0.0)
            else 0.0
        )

    elif game_type == GameType.INDIVIDUAL_RANKED:
        # People ranked lower than you
        worse_players = [
            p for j, t in enumerate(game.teams) if game.ranks[j] > player_rank for p in t
        ]
        # People ranked higher than you
        better_players = [
            p for j, t in enumerate(game.teams) if game.ranks[j] < player_rank for p in t
        ]

        bonus_count = sum(
            1
            for p_opp in worse_players
            if current_ratings.get(p_opp, 0.0)
            > current_ratings.get(player, 0.0)
        )
        penalty_count = sum(
            1
            for p_opp in better_players
            if current_ratings.get(p_opp, 0.0)
            < current_ratings.get(player, 0.0)
        )

        return 0.5 * (bonus_count - penalty_count)

    return 0.0


class RankingCalculator:
    """Main class for calculating player rankings."""

    def __init__(self):
        self.game_history: GameHistory = []  # Store all game details
        self.game_results: List[GameResult] = []  # Store all game results
        self.processed_games: List[Tuple[GameResult, AllPlayerStats]] = []  # Store interleaved game and ratings

    def process_game(
        self, game: GameResult, player_stats: AllPlayerStats
    ) -> None:
        """Process a single game and update player statistics."""
        current_ratings = {p: player_stats[p]["score"] for p in player_stats}

        # Process each player in the game
        for i, team in enumerate(game.teams):
            rank_i = game.ranks[i]

            for player in team:
                # Initialize player if not exists
                if player not in player_stats:
                    player_stats[player] = {
                        "score": 0.0,
                        "wins": 0,
                        "losses": 0,
                        "games": 0,
                    }

                # Base performance bonus
                player_stats[player]["score"] += calc_base_bonus(player, game)

                # Upset bonus
                player_stats[player]["score"] += calc_upset_bonus(player, game, current_ratings)

                # Participation Bonus (Capped at 10 total)
                if player_stats[player]["games"] < 50:  # 50 * 0.2 = 10
                    player_stats[player]["score"] += 0.2

                player_stats[player]["games"] += 1

                # Win/Loss tracking
                if rank_i == 0:
                    player_stats[player]["wins"] += 1
                else:
                    player_stats[player]["losses"] += 1

    def calculate_rankings(
        self, games: Tuple[GameResult, ...]
    ) -> AllPlayerStats:
        """Calculate rankings from the provided data string."""
        player_stats = defaultdict(
            lambda: {"score": 100.0, "wins": 0, "losses": 0, "games": 0}
        )

        for game in games:
            self.game_results.append(game)
            # Store the ratings before processing this game
            ratings_before = deepcopy(player_stats)
            self.game_history.append((game.date, ratings_before))
            self.processed_games.append((game, ratings_before))
            
            self.process_game(game, player_stats)

        return player_stats

    def get_historical_ratings(self, player: str = None) -> Dict[str, List[Tuple[str, Dict[str, Union[float, int]]]]]:
        """Get historical ratings for all players or a specific player."""
        historical_ratings = defaultdict(list)
        
        for game_record in self.game_history:
            date, ratings = game_record
            
            for player_name, rating in ratings.items():
                historical_ratings[player_name].append((date, rating))
        
        if player:
            return {player: historical_ratings.get(player, [])}
        return dict(historical_ratings)

    def get_game_rankings(self, data_string: str = None, games: List[GameResult] = None) -> Dict[str, AllPlayerStats]:
        """Calculate rankings per game type."""
        if games is None and data_string is None:
            raise ValueError("Either data_string or games must be provided")
        
        if games is None:
            games = parse_game_data(data_string)
        
        unique_games = set(game.game_name for game in games)
        game_rankings = {}

        for game_name in unique_games:
            # Filter games for this specific game type
            game_data = [game for game in games if game.game_name == game_name]
            calculator = RankingCalculator()
            game_stats = calculator.calculate_rankings(tuple(game_data))
            game_rankings[game_name] = game_stats

        return game_rankings

    def save_game_history(self, filename: str = "game_history.txt") -> None:
        """Save the interleaved game history to a file."""
        with open(filename, "w", encoding="utf-8") as f:
            for game, ratings_before in self.processed_games:
                # Get all unique players from all games for consistent ordering
                all_players = set()
                for g, _ in self.processed_games:
                    for team in g.teams:
                        all_players.update(team)
                
                # Sort players alphabetically for consistent output
                sorted_players = sorted(all_players)
                
                # Format ratings line
                rating_lines = []
                for player in sorted_players:
                    if player in ratings_before:
                        score = ratings_before[player].get("score", 0.0)
                        rating_lines.append(f"{player}: {score:.2f}")
                
                # Write ratings line
                f.write(", ".join(rating_lines) + "\n")
                
                # Write game string
                f.write(game.to_string() + "\n")
        
        print(f"Game history saved to {filename}")

class ResultFormatter:
    """Formats and displays results in various views."""

    @staticmethod
    def format_stats(stats_dict: AllPlayerStats) -> pd.DataFrame:
        """Format player statistics into a DataFrame."""
        df = pd.DataFrame.from_dict(stats_dict, orient="index")
        if not df.empty and 'wins' in df.columns and 'losses' in df.columns:
            df["win_pct"] = (df["wins"] / (df["wins"] + df["losses"]) * 100).round(
                1
            )
        return df.sort_values(by="score", ascending=False)

    @staticmethod
    def get_history_dataframe(
        calculator: RankingCalculator, top_players: List[str]
    ) -> pd.DataFrame:
        """Create a DataFrame of ranking history for top players."""
        historical_ratings = calculator.get_historical_ratings()
        
        # Create date-indexed dataframe
        all_dates = set()
        for ratings in historical_ratings.values():
            all_dates.update(date for date, _ in ratings)
        all_dates = sorted(all_dates)
        
        # Initialize dataframe
        history_data = []
        for date in all_dates:
            row = {"Date": date}
            for player in top_players:
                if player in historical_ratings:
                    # Find the latest rating on or before this date
                    player_ratings = historical_ratings[player]
                    rating_at_date = None
                    for rating_date, rating in player_ratings:
                        if rating_date <= date:
                            rating_at_date = rating
                    if rating_at_date is not None:
                        # Get the score from the rating dict
                        row[player] = round(rating_at_date.get("score", 0.0), 2)
            history_data.append(row)
        
        return pd.DataFrame(history_data)

    @staticmethod
    def generate_markdown(overall_stats: AllPlayerStats, game_rankings: Dict[str, AllPlayerStats]) -> str:
        """Generate markdown output similar to parse_results_OLD.py."""
        markdown_lines = []
        
        # Add header image
        markdown_lines.append("![Image](https://media.architecturaldigest.com/photos/618036966ba9675f212cc805/16:9/w_2560%2Cc_limit/SquidGame_Season1_Episode1_00_44_44_16.jpg)")
        markdown_lines.append("")
        
        # Add overall rankings
        markdown_lines.append("### Overall Rankings")
        markdown_lines.append("")
        markdown_lines.append("| Player | Score | Wins | Losses | Win % |")
        markdown_lines.append("| --- | --- | --- | --- | --- |")
        
        # Sort players by score
        sorted_players = sorted(
            overall_stats.items(),
            key=lambda x: x[1]["score"],
            reverse=True
        )
        
        for player, stats in sorted_players:
            total_games = stats["wins"] + stats["losses"]
            win_pct = (stats["wins"] / max(1, total_games)) * 100
            markdown_lines.append(
                f"| {player} | {stats['score']:.2f} | {stats['wins']} | {stats['losses']} | {win_pct:.0%} |"
            )
        
        markdown_lines.append("")
        
        # Add rankings over time
        markdown_lines.append("### Rankings over Time")
        markdown_lines.append("")
        markdown_lines.append("![Image](rankings.png)")
        markdown_lines.append("")
        
        # Add per-game rankings
        for game_name, stats in game_rankings.items():
            markdown_lines.append(f"### {game_name}")
            markdown_lines.append("")
            markdown_lines.append("| Player | Score | Wins | Losses | Win % |")
            markdown_lines.append("| --- | --- | --- | --- | --- |")
            
            # Sort players by score for this game
            game_sorted_players = sorted(
                stats.items(),
                key=lambda x: x[1]["score"],
                reverse=True
            )
            
            for player, row in game_sorted_players:
                total_games = row["wins"] + row["losses"]
                win_pct = (row["wins"] / max(1, total_games)) * 100
                markdown_lines.append(
                    f"| {player} | {row['score']:.2f} | {int(row['wins'])} | {int(row['losses'])} | {win_pct:.0%} |"
                )
            
            markdown_lines.append("")
        
        return "\n".join(markdown_lines)

    @staticmethod
    def plot_rankings_over_time(calculator: RankingCalculator, overall_stats: AllPlayerStats, output_file: str = "rankings.png"):
        """Plot a time series of rankings over time."""
        historical_ratings = calculator.get_historical_ratings()
        
        if not historical_ratings:
            print("No historical data available for plotting.")
            return
        
        # Prepare data for plotting
        chart_data = {}
        all_dates = set()
        
        # Collect all dates
        for ratings in historical_ratings.values():
            all_dates.update(date for date, _ in ratings)
        
        all_dates = sorted(all_dates)
        
        # Initialize chart data
        for player in historical_ratings.keys():
            chart_data[player] = []
        
        # Fill chart data with scores at each date
        for date in all_dates:
            for player in historical_ratings.keys():
                player_ratings = historical_ratings[player]
                score_at_date = None
                
                # Find the latest rating on or before this date
                for rating_date, rating in player_ratings:
                    if rating_date <= date:
                        score_at_date = rating.get("score", 0.0)
                
                if score_at_date is not None:
                    chart_data[player].append(score_at_date)
                else:
                    chart_data[player].append(None)
        
        # Create DataFrame for plotting
        df = pd.DataFrame(chart_data, index=all_dates)
        
        # Forward fill missing values
        df = df.ffill()
        
        # Create the plot
        plt.style.use("ggplot")
        plt.figure(figsize=(12, 8))
        
        # Plot each player's rating history
        for player in df.columns:
            plt.plot(df.index, df[player], marker='o', markersize=3, label=player)
        
        plt.title("Player Rankings Over Time")
        plt.xlabel("Date")
        plt.ylabel("Score")
        plt.xticks(rotation=45)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.grid(True, alpha=0.3)
        
        # Save the plot
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Rankings plot saved to {output_file}")


def run() -> None:
    """Main function to run the ranking calculation and display results."""
    calculator = RankingCalculator()
    formatter = ResultFormatter()
    results = parse_game_data()

    print(results)

    # (1) Calculate Overall Rankings
    stats = calculator.calculate_rankings(tuple(results))
    
    # (2) Save the interleaved game history
    calculator.save_game_history("game_history.txt")
    
    # (3) Calculate per-game rankings using the calculator method
    game_rankings = calculator.get_game_rankings(games=results)
    
    # (4) Generate and save the rankings plot
    formatter.plot_rankings_over_time(calculator, stats, output_file="rankings.png")
    
    # (5) Generate markdown
    markdown = formatter.generate_markdown(stats, game_rankings)
    
    # (6) Write to README.md (similar to old code)
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(markdown)
    
    print("Markdown generated and written to README.md")
    
    # (7) Also print the overall rankings to console
    print("\n--- OVERALL RANKINGS ---")
    overall_df = formatter.format_stats(stats)
    print(overall_df[["score", "wins", "losses"]])

if __name__ == "__main__":
    run()
