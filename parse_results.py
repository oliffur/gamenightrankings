import itertools
from   matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from   trueskill import TrueSkill

LUCK_FACTORS = {
        'Exploding Kittens': 10.0,
        'Incan Gold': 10.0,
        }

class RatingsInfo:
    elo = None
    wins = None
    losses = None
    def __init__(self, env):
        self.elo = env.create_rating()
        self.wins, self.losses = 0, 0

    def get_elo(self):
        return self.elo.mu * 4.0  # scale to 100

    def get_rating(self):
        return (self.elo.mu - 2 * self.elo.sigma) * 4.0

def get_elo(d, env, player):
    '''
    Get elo from dict d, if not present, create a new RatingsInfo
    object and return its elo
    '''
    if player not in d: d[player] = RatingsInfo(env)
    return d[player].elo

def calc_elo(df):
    '''
    For a given input dataframe, calculates the running elo of each player
    in each team. Returns a dictionary of players to latest elos, and also
    returns the running df
    '''

    env = TrueSkill(draw_probability=0)
    ratings = {}
    df['elos'] = None
    df['elos'] = df['elos'].astype(object)  # avoid insertion errors later
    for idx, row in df.iterrows():
        teams = [[get_elo(ratings, env, player) for player in team]\
                for team in row['teams']]
        if row['game'] in LUCK_FACTORS:
            env.beta = env.beta * LUCK_FACTORS[row['game']]
            elos = env.rate(teams, row['ranks'])
            env.beta = env.beta / LUCK_FACTORS[row['game']]
        else:
            elos = env.rate(teams, row['ranks'])
        has_winner = sum(row['ranks']) > 0
        for team, team_elos, team_rank in zip(row['teams'], elos, row['ranks']):
            for player, player_elo in zip(team, team_elos):
                ratings[player].elo = player_elo
                if has_winner:
                    if team_rank == 0: ratings[player].wins += 1
                    else: ratings[player].losses += 1
        #df.at[idx, 'elos'] = [elos]
        df.at[idx, 'elos'] = elos
    return ratings, df

def parse_results():
    '''
    Parses results.txt and runs calc_elo on the aggregate df as well
    as per-game dfs
    '''
    results = []
    with open('results.txt') as f:
        for line in f.readlines():
            if line.startswith('DATE'): continue
            date, game, teams, ranks = line.split('|')
            teams, ranks = teams.split(';'), ranks.split(';')
            teams = [team.split(',') for team in teams]
            ranks = [int(rank) for rank in ranks]
            results.append((date, game, teams, ranks))

    res_df = pd.DataFrame(results, columns=['date', 'game', 'teams', 'ranks'])

    elos = {}
    for game in res_df.game.unique():
        elos[game], _ = calc_elo(res_df.loc[res_df.game == game])
        # (DEBUG) if game == "Secret Hitler": _.to_csv('./test.csv')
    return calc_elo(res_df) + (elos,)  # Tuple concatenation

def main():
    '''
    Calls parse_results() and then updates README.md based on return value.
    '''

    all_ratings, all_df, per_game_ratings = parse_results()


    markdown = '''
![Image](https://media.architecturaldigest.com/photos/618036966ba9675f212cc805/16:9/w_2560%2Cc_limit/SquidGame_Season1_Episode1_00_44_44_16.jpg)

### Total Rankings

| Player | ELO | Wins | Losses | Win % | Best Game |
| --- | --- | --- | --- | --- | --- |'''

    best_game = {}
    for game, ratings in per_game_ratings.items():
        for player, rating in ratings.items():
            if player not in best_game or rating.get_rating() > best_game[player][1]:
                best_game[player] = (game, rating.get_rating())

    infrequent_players = []  # players with <10 games
    for player, rating in sorted(
            all_ratings.items(),
            key=lambda item: item[1].get_rating(),
            reverse=True):
        if player.startswith('dummy'): continue
        markdown += '''
| {} | {:.2f} | {} | {} | {:.2f} | {} |'''.format(
        player, rating.get_rating(), rating.wins, rating.losses,
        rating.wins / (rating.wins + rating.losses), best_game[player][0])
        if rating.wins + rating.losses < 10: infrequent_players.append(player)

    chart_df = pd.DataFrame()
    for _, row in all_df.iterrows():
        players = list(np.array(row['teams']).flat)
        ratings = [(elo.mu - 2 * elo.sigma) * 4 for elo in \
                itertools.chain.from_iterable(row['elos'])]
        #ratings = [elo.mu * 4 for elo in np.array(row['elos']).flat]
        for player, rating in zip(players, ratings):
            if player.startswith('dummy'): continue
            chart_df.at[row['date'], player] = rating
    chart_df.ffill(inplace=True)
    chart_df.drop(columns=infrequent_players, inplace=True)
    chart_df.plot.line().legend(
            loc='lower center', ncol=5, bbox_to_anchor=(0.5, -0.3))
    plt.xticks(rotation='vertical')
    plt.subplots_adjust(bottom=0.25)
    plt.savefig('rankings.png')

    markdown += '''

### Rankings over Time
![Image](rankings.png)'''
    
    for game, ratings in per_game_ratings.items():
        markdown += '''

### {}

| Player | ELO | Wins | Losses | Win % |
| --- | --- | --- | --- | --- |'''.format(game)
        for player, rating in sorted(ratings.items(), key=lambda item: item[1].get_rating(), reverse=True):
            if player.startswith('dummy'): continue
            markdown += '''
| {} | {:.2f}  | {} | {} | {:.2f} |'''.format(
            player, rating.get_rating(), rating.wins, rating.losses,
            rating.wins / (rating.wins + rating.losses))

    with open('README.md', 'w') as f:
        f.write(markdown)

if __name__ == "__main__":
    main()
