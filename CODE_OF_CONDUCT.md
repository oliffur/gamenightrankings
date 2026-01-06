# Board Game Ranking System Scoring Documentation

This document outlines the logic used by the `RankingCalculator` in `parse_results.py` to determine player scores and rankings.

## 1. Starting Point
- **Initial Score:** Every player starts with a base score of **100.0**.
- **Participation Bonus:** For the first 50 games played, a player receives **+0.2** points per game (capped at a total of +10.0).

---

## 2. Game Classifications
The system categorizes games into four types, each affecting the **Base Bonus** calculation differently:

| Game Type | Description | Examples |
| :--- | :--- | :--- |
| `TEAM_UNBALANCED` | Teams with different sizes/roles. | Bang |
| `TEAM_BALANCED` | Teams of equal size. | Secret Hitler, Avalon, Codenames |
| `INDIVIDUAL_WINNER` | One winner, everyone else loses. | Coup, Love Letter, Exploding Kittens |
| `INDIVIDUAL_RANKED` | Players are ranked 1st, 2nd, 3rd, etc. | Incan Gold, Camel Up, Carcassonne |

---

## 3. Scoring Formula
The total score change for a player after a game is calculated as:
**Δ Score = Base Bonus + Upset Bonus + Participation Bonus**

### A. Base Bonus
This is the fundamental reward or penalty based on the game outcome.

- **Team Balanced:**
  - Win: **+1.0**
  - Loss: **-1.0**
- **Team Unbalanced:**
  - Win: **+1.0**
  - Loss: **-(Winning Team Size / Your Team Size)**
- **Individual Winner (Winner Takes All):**
  - Win: **+1.0 × (Number of Losers)**
  - Loss: **-1.0**
- **Individual Ranked:**
  - Score: **(Total Players Beaten) - (Total Players Lost To)**

### B. Upset Bonus
This bonus rewards players for beating stronger opponents and penalizes them for losing to weaker ones. It is calculated using the ratings of players *before* the current game starts.

- **Team Games (Balanced & Unbalanced):**
  - The player's rating is compared against the **median rating** of the opposing team.
  - **+0.5** if you win against a higher-rated team.
  - **-0.5** if you lose to a lower-rated team.
- **Individual Winner:**
  - Winner: **+0.5** for every loser who had a higher rating than the winner.
  - Loser: **-0.5** if the winner had a lower rating than the loser.
- **Individual Ranked:**
  - **+0.5** for every player ranked below you who had a higher rating than you.
  - **-0.5** for every player ranked above you who had a lower rating than you.

---

## 4. Win/Loss Tracking
- A player is credited with a **Win** if their team rank is `0`.
- A player is credited with a **Loss** if their team rank is `> 0`.

---

## 5. Summary of Game Configurations
The following games are currently mapped in the system:

- **Team Balanced:** Secret Hitler, Codenames, Avalon, Quest.
- **Team Unbalanced:** Bang.
- **Individual Winner:** Exploding Kittens, Love Letter, Shifty Eyed Spies, Cash n Guns, Coup, Masquerade, Monopoly Deal, Night of the Ninja, Clank.
- **Individual Ranked:** Incan Gold, Carcassonne, Camel Up.
