"""Unittests for parse_results"""

import unittest
from unittest.mock import patch, mock_open, MagicMock

import pandas as pd
from parse_results import (
    parse_results,
    get_ratings,
    get_best_game_by_player,
    add_ranking_rows,
    flatten,
    plot_rankings_over_time,
    main,
)


class TestParseResults(unittest.TestCase):

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="DATE|GAME|TEAMS|RANKS\n"
        "2023-09-01|Incan Gold|Team1,Team2,Team3;Team4,Team5|1;2\n",
    )
    def test_parse_results(self, mock_file):
        df = parse_results("dummy_path")
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["game"], "Incan Gold")
        self.assertEqual(
            df.iloc[0]["teams"],
            [["Team1", "Team2", "Team3"], ["Team4", "Team5"]],
        )
        self.assertEqual(df.iloc[0]["ranks"], [1, 2])

    @patch("parse_results.TSRating")
    def test_get_ratings(self, MockTSRating):
        mock_ts = MagicMock()
        MockTSRating.return_value = mock_ts
        mock_df = pd.DataFrame(
            {
                "date": ["2023-09-01"],
                "game": ["Incan Gold"],
                "teams": [[["Team1", "Team2", "Team3"], ["Team4", "Team5"]]],
                "ranks": [[1, 2]],
            }
        )
        overall_df, overall_ts, ts_dict = get_ratings(mock_df)
        self.assertTrue(mock_ts.enrich_update.called)
        self.assertIsInstance(ts_dict, dict)

    @patch("parse_results.TSRating")
    def test_get_best_game_by_player(self, MockTSRating):
        mock_ts = MagicMock()
        mock_ts.players = {
            "Player1": MagicMock(get_min_rating=lambda: 1500),
            "Player2": MagicMock(get_min_rating=lambda: 1600),
        }
        ts_dict = {"Incan Gold": mock_ts}
        best_game = get_best_game_by_player(ts_dict)
        self.assertEqual(best_game["Player2"], ("Incan Gold", 1600))

    @patch("parse_results.TSRating")
    def test_add_ranking_rows(self, MockTSRating):
        mock_ts = MagicMock()
        mock_ts.players = {
            "Player1": MagicMock(
                get_min_rating=lambda: 1500, wins=10, losses=5
            ),
            "Player2": MagicMock(
                get_min_rating=lambda: 1600, wins=15, losses=5
            ),
        }
        markdown, infrequent_players = add_ranking_rows(
            "Incan Gold", mock_ts, "", infrequent_threshold=10
        )
        self.assertIn("| Player1 | 1500.00 | 10 | 5 | 67% |", markdown)
        self.assertIn("| Player2 | 1600.00 | 15 | 5 | 75% |", markdown)
        self.assertTrue("Player1" not in infrequent_players)

    def test_flatten(self):
        nested_list = [[1, 2], [3, 4], [5]]
        flat_list = flatten(nested_list)
        self.assertEqual(flat_list, [1, 2, 3, 4, 5])

    @patch("parse_results.plt.savefig")
    def test_plot_rankings_over_time(self, mock_savefig):
        mock_df = pd.DataFrame(
            {
                "date": ["2023-09-01"],
                "ratings": [
                    [
                        MagicMock(get_min_rating=lambda: 1500, name="Player1"),
                        MagicMock(get_min_rating=lambda: 1600, name="Player2"),
                    ]
                ],
            }
        )
        infrequent_players = []
        plot_rankings_over_time(mock_df, infrequent_players)
        self.assertTrue(mock_savefig.called)

    @patch("parse_results.parse_results")
    @patch("parse_results.get_ratings")
    @patch("parse_results.get_best_game_by_player")
    @patch("parse_results.add_ranking_rows")
    @patch("parse_results.plot_rankings_over_time")
    @patch("builtins.open", new_callable=mock_open)
    def test_main(
        self,
        mock_open_file,
        mock_plot,
        mock_add_rows,
        mock_best_game,
        mock_get_ratings,
        mock_parse_results,
    ):
        mock_parse_results.return_value = pd.DataFrame()
        mock_get_ratings.return_value = (pd.DataFrame(), MagicMock(), {})
        mock_add_rows.return_value = ("", [])

        main()

        self.assertTrue(mock_parse_results.called)
        self.assertTrue(mock_get_ratings.called)
        self.assertTrue(mock_best_game.called)
        self.assertTrue(mock_add_rows.called)
        self.assertTrue(mock_plot.called)
        mock_open_file.assert_called_with("README.md", "w", encoding="ascii")


if __name__ == "__main__":
    unittest.main()
