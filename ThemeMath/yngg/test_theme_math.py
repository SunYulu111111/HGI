"""Deterministic tests for yngg without relying on unavailable server RNG."""

from __future__ import annotations

import unittest

from theme_math import ThemeMath


class ThemeMathTest(unittest.TestCase):
    def setUp(self):
        self.math = ThemeMath()

    def test_five_connected_high_symbol_pays_one_bet(self):
        board = [
            [3, 3, 3, 8, 9],
            [3, 3, 10, 11, 12],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
        ]
        result = self.math.evaluate(board)
        self.assertEqual(result["total_win"], self.math.base_bet)
        self.assertEqual(result["win_items"][0]["count"], 5)

    def test_paytable_matches_design(self):
        expected = {
            3: (1, 2.5, 5, 25),
            4: (1, 2.5, 5, 10),
            5: (0.5, 1, 3, 5),
            6: (0.3, 0.5, 1, 3),
            7: (0.3, 0.5, 1, 3),
            8: (0.1, 0.2, 0.5, 1),
            9: (0.1, 0.2, 0.5, 1),
            10: (0.1, 0.2, 0.3, 0.6),
            11: (0.1, 0.2, 0.3, 0.6),
            12: (0.1, 0.2, 0.3, 0.5),
        }
        for symbol_id, payouts in expected.items():
            row = self.math.config.item_prizes[symbol_id]
            actual = tuple(row[index] / self.math.BET_UNIT for index in (4, 5, 7, 11))
            self.assertEqual(actual, payouts)

    def test_diagonal_symbols_do_not_form_cluster(self):
        board = [
            [12, 3, 4, 5, 6],
            [3, 12, 5, 6, 7],
            [4, 5, 12, 7, 8],
            [5, 6, 7, 12, 9],
            [6, 7, 8, 9, 12],
            [7, 8, 9, 10, 3],
        ]
        self.assertEqual(self.math.evaluate(board)["total_win"], 0)

    def test_cascade_removes_only_winning_cluster_positions(self):
        board = [
            [12, 12, 12, 3, 4],
            [12, 12, 5, 6, 7],
            [8, 9, 10, 11, 12],
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
        ]
        state = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7, 8, 9] for _ in range(6)],
            "top_indexes": [5] * 6,
            "row": 5,
            "col": 6,
        }
        win_items = self.math.cal_item_list(board, return_detail=True)["items"]
        next_board, drop = self.math.drop_cluster_symbols(board, win_items, state)
        self.assertEqual(len(drop["remove_positions"]), 5)
        self.assertIn(12, next_board[2])

    def test_result_contract_and_normal_free_trigger(self):
        board = [
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
            [8, 9, 10, 11, 12],
        ]
        state = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        result = self.math.evaluate_cascades(
            board,
            state,
            return_detail=False,
            feature_outcome={
                "feature_win_multiple": 25_000,
                "scatter_count": 3,
                "super_scatter_count": 0,
                "bonus_count": 1,
                "activated": True,
                "events": [{"type": "JackpotWin", "symbol_id": 2, "tier": "grand"}],
            },
        )
        self.assertEqual(result["total_win"], self.math.base_bet * 25_000)
        self.assertEqual(result["free_mode"], "free")
        self.assertEqual(result["free_times"], 10)
        self.assertIn("final_item_list", result)
        self.assertIn("rounds", result)

    def test_free_mode_golden_square_persistence(self):
        board = [
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
            [8, 9, 10, 11, 12],
        ]
        state = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        persistent = self.math.evaluate_cascades(
            board,
            self.math.clone_spin_state(state),
            free_game=True,
            free_mode="super_free",
            golden_squares={(0, 0)},
            feature_outcome={"activated": True},
        )
        cleared = self.math.evaluate_cascades(
            board,
            self.math.clone_spin_state(state),
            free_game=True,
            free_mode="free",
            golden_squares={(0, 0)},
            feature_outcome={"activated": True},
        )
        self.assertEqual(persistent["golden_squares"], [(0, 0)])
        self.assertEqual(cleared["golden_squares"], [])

    def test_super_free_trigger_and_retrigger(self):
        mode = self.math.get_triggered_free_spin_mode(2, 1)
        self.assertEqual(mode, {"name": "super_free", "spins": 10})
        self.assertEqual(
            self.math.get_triggered_free_spin_mode(3, 0),
            {"name": "free", "spins": 10},
        )
        self.assertEqual(self.math.get_retrigger_spins(2), 2)
        self.assertEqual(self.math.get_retrigger_spins(3), 4)

    def test_trigger_positions_seed_free_game_golden_squares(self):
        board = [
            [0, 3, 4, 5, 6],
            [0, 4, 5, 6, 7],
            [13, 5, 6, 7, 8],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
            [8, 9, 10, 11, 12],
        ]
        state = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        result = self.math.evaluate_cascades(board, state)
        self.assertEqual(result["free_mode"], "super_free")
        self.assertEqual(
            result["next_free_golden_squares"],
            [(0, 0), (1, 0), (2, 0)],
        )

    def test_golden_clover_and_jackpot_resolution(self):
        result = self.math.resolve_golden_feature(
            [
                [
                    {"position": [0, 0], "type": "coin", "value": 5},
                    {"position": [1, 0], "type": "clover", "multiplier": 2},
                    {"position": [2, 0], "type": "coin", "value": 10},
                    {"position": [0, 1], "type": "jackpot", "tier": "mini"},
                ]
            ],
            golden_squares={(0, 0), (1, 0), (2, 0), (0, 1)},
        )
        self.assertEqual(result["area_multiple"], 30)
        self.assertEqual(result["jackpot_multiple"], 10)
        self.assertEqual(result["total_win"], self.math.base_bet * 40)

    def test_bonus_activates_existing_golden_area(self):
        board = [
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
            [8, 9, 10, 11, 2],
        ]
        state = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        result = self.math.evaluate_cascades(
            board,
            state,
            golden_squares={(0, 0)},
            feature_outcome={
                "bonus_count": 1,
                "golden_rounds": [
                    [{"position": [0, 0], "type": "coin", "value": 5}]
                ],
            },
        )
        self.assertTrue(result["is_trigger_feature"])
        self.assertEqual(result["feature_win"], self.math.base_bet * 5)
        self.assertEqual(result["golden_squares"], [])

    def test_multiple_pots_collect_top_to_bottom_then_left_to_right(self):
        result = self.math.resolve_golden_feature(
            [
                [
                    {"position": [0, 0], "type": "coin", "value": 5},
                    {"position": [0, 1], "type": "pot"},
                    {"position": [1, 1], "type": "pot"},
                ]
            ],
            golden_squares={(0, 0), (0, 1), (1, 1)},
        )
        collects = [event for event in result["events"] if event["type"] == "Collect"]
        self.assertEqual([event["position"] for event in collects], [(0, 1), (1, 1)])
        self.assertEqual([event["value"] for event in collects], [5, 10])

    def test_jackpot_values_follow_design(self):
        self.assertEqual(self.math.jackpot_win("mini"), self.math.base_bet * 10)
        self.assertEqual(self.math.jackpot_win("minor"), self.math.base_bet * 25)
        self.assertEqual(self.math.jackpot_win("major"), self.math.base_bet * 100)
        self.assertEqual(self.math.jackpot_win("grand"), self.math.base_bet * 5000)


if __name__ == "__main__":
    unittest.main()
