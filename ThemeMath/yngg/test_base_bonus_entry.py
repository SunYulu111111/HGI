"""Base Bonus entry depends on this spin's actual cluster wins."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from theme_math import ThemeMath


class BaseBonusEntryTest(unittest.TestCase):
    def setUp(self):
        self.Math = ThemeMath()
        Section = self.Math.game_server_config["Game Info"]
        Section["ScatterCountProbability"] = "1,0,0,0"
        Section["BaseNoWinBonusCountProbability"] = "0,1"
        Section["BaseWinBonusCountProbability"] = "0,1"
        Section["DropSpecialSymbolProbability"] = "1,0,0"
        self.Math._load_super_scatter_config()

    @staticmethod
    def _no_win_board():
        return [
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
            [8, 9, 10, 11, 12],
        ]

    @staticmethod
    def _win_board():
        return [
            [12, 12, 12, 3, 4],
            [12, 12, 5, 6, 7],
            [8, 9, 10, 11, 12],
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
        ]

    def _spin_board(self, Board):
        State = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7, 8, 9, 10, 11] for _ in range(6)],
            "top_indexes": [0] * 6,
            "NextReelIndexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        with (
            patch.object(self.Math, "_choose_spin_type", return_value="normal"),
            patch.object(self.Math, "_spin_from_rolls", return_value=(Board, State)),
            patch("theme_math.random.randrange", return_value=0),
        ):
            return self.Math.ng_spin(return_detail=True)

    def test_no_win_bonus_symbol_is_visible_without_feature_activation(self):
        with patch.object(self.Math, "generate_golden_rounds") as Generate:
            Result = self._spin_board(self._no_win_board())
        self.assertEqual(Result["bonus_count"], 1)
        self.assertEqual(self.Math.count_symbol(Result["final_item_list"], self.Math.FEATURE_ID), 1)
        self.assertEqual(Result["cascade_count"], 0)
        self.assertEqual(Result["total_win"], 0)
        self.assertEqual(Result["golden_squares"], [])
        self.assertFalse(Result["is_trigger_feature"])
        self.assertFalse(Result["feature_outcome_generated"])
        Generate.assert_not_called()

    def test_winning_bonus_placement_preserves_initial_cluster_and_triggers_feature(self):
        Board = self._win_board()
        InitialWin = self.Math.cal_item_list(Board, return_detail=True)
        Result = self._spin_board(Board)
        self.assertEqual(Result["bonus_count"], 1)
        self.assertGreater(Result["cascade_count"], 0)
        self.assertEqual(set(Result["rounds"][0]["win_positions"]), set(InitialWin["win_positions"]))
        self.assertEqual(Result["rounds"][0]["total_win"], InitialWin["total_win"])
        self.assertTrue(Result["is_trigger_feature"])
        self.assertTrue(Result["feature_outcome_generated"])
        self.assertGreater(Result["feature_win"], 0)
        self.assertGreater(Result["total_win"] - Result["feature_win"], 0)

    def test_a_later_no_win_base_does_not_inherit_previous_base_golden_squares(self):
        self.Math.game_server_config["Game Info"]["BaseWinBonusCountProbability"] = "1,0"
        Previous = self._spin_board(self._win_board())
        self.assertTrue(Previous["golden_squares"])
        self.assertFalse(Previous["is_trigger_feature"])
        with patch.object(self.Math, "generate_golden_rounds") as Generate:
            Current = self._spin_board(self._no_win_board())
        self.assertEqual(Current["bonus_count"], 1)
        self.assertEqual(Current["cascade_count"], 0)
        self.assertEqual(Current["golden_squares"], [])
        self.assertFalse(Current["is_trigger_feature"])
        self.assertEqual(Current["feature_win"], 0)
        Generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
