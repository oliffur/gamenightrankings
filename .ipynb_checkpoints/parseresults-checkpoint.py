from trueskill import TrueSkill
import pandas as pd

def get_elo(d, env, player):
    if player not in d:
        d[player] = env.create_rating()
    return d[player]

def calc_elo(df):
    env = TrueSkill(draw_probability=0)
    ratings = {}
    for idx, row in df.iterrows():
        teams = [[get_elo(ratings, env, player) for player in team] for team in row['teams']]
        elos = env.rate(teams, row['ranks'])
        for team, team_elos in zip(row['teams'], elos):
            for player, player_elo in zip(team, team_elos):
                ratings[player] = player_elo
        df.loc[idx, 'elos'] = [elos]

    return ratings, df

def parse_results():
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

    elos = { 'ALL' : calc_elo(res_df) }
    for game in results_df.game.unique():
        elos[game] = calc_elo(res_df.loc[res_df.game == game])
