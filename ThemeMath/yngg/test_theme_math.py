"""Deterministic tests for yngg without relying on unavailable server RNG."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import build_from_demo
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

    def test_bonus_config_matches_design_weights(self):
        self.assertEqual(
            self.math.BONUS_SYMBOL_TYPES,
            ("coin", "clover", "pot", "jackpot"),
        )
        self.assertEqual(self.math.BONUS_SYMBOL_TYPE_WEIGHTS, (1000, 80, 6, 2))
        self.assertEqual(
            self.math.COIN_VALUE_WEIGHTS,
            (1560, 1240, 1030, 860, 720, 545, 415, 320, 228, 165, 110, 62, 31, 10, 3),
        )
        self.assertEqual(self.math.CLOVER_MULTIPLIER_WEIGHTS, (40, 28, 16, 10, 5, 1))
        self.assertEqual(self.math.JACKPOT_TYPE_WEIGHTS, (80, 25, 8, 1))
        self.assertEqual(
            self.math.JACKPOT_MULTIPLIERS,
            {"mini": 10, "minor": 25, "major": 100, "grand": 5000},
        )
        self.assertEqual(self.math.COIN_MULTI_1, 5)
        self.assertEqual(self.math.COIN_MULTI_2, 25)
        self.assertEqual(self.math.BONUS_MAX_ROUND, 5)

    def test_coin_tiers_follow_server_thresholds(self):
        self.assertEqual(self.math.get_coin_tier(4), "bronze")
        self.assertEqual(self.math.get_coin_tier(5), "silver")
        self.assertEqual(self.math.get_coin_tier(24), "silver")
        self.assertEqual(self.math.get_coin_tier(25), "gold")

    def test_bonus_redraws_without_pot_after_five_pots(self):
        positions = {
            (0, 0),
            (1, 0),
            (2, 0),
            (3, 0),
            (4, 0),
            (5, 0),
            (0, 1),
        }

        def choose_index(weights):
            weights = tuple(weights)
            if weights == self.math.BONUS_SYMBOL_TYPE_WEIGHTS:
                return 2
            return 0

        with patch.object(
            self.math,
            "weighted_random_index",
            side_effect=choose_index,
        ):
            reveals = self.math.generate_golden_round(positions)
        self.assertEqual(
            sum(reveal["type"] == "pot" for reveal in reveals),
            5,
        )
        non_pots = [reveal for reveal in reveals if reveal["type"] != "pot"]
        self.assertEqual([reveal["type"] for reveal in non_pots], ["coin", "coin"])
        self.assertTrue(
            all(reveal["coin_tier"] == "bronze" for reveal in non_pots)
        )

        pot_round = [
            {"position": list(position), "type": "pot"}
            for position in sorted(positions)[:6]
        ]
        with self.assertRaisesRegex(ValueError, "pot limit=5"):
            self.math.resolve_golden_feature(
                [pot_round],
                golden_squares=set(positions),
            )

    def test_super_scatter_rolls_once_and_converts_at_most_one(self):
        self.assertEqual(self.math.config.item_count, 13)
        self.assertEqual(len(self.math.config.item_prizes), 13)
        self.assertEqual(len(self.math.config.use_wilds), 13)
        self.assertEqual(len(self.math.config.base_nums), 13)
        self.assertEqual(self.math.SUPER_SCATTER_SOURCE_ID, 0)
        self.assertEqual(self.math.SUPER_SCATTER_PROBABILITY, 200)
        board = [
            [0, 0, 3, 4, 5],
            [0, 6, 7, 8, 9],
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
        ]
        with patch(
            "theme_math.random.randrange",
            side_effect=[199, 1],
        ) as rng:
            result, positions = self.math.apply_super_scatter_conversion(board)
        self.assertEqual(rng.call_count, 2)
        self.assertEqual(positions, [(0, 1)])
        self.assertEqual(result, board)
        self.assertEqual(result[1][0], 0)
        with patch("theme_math.random.randrange", return_value=200):
            unchanged, positions = self.math.apply_super_scatter_conversion(board)
        self.assertEqual(unchanged, board)
        self.assertEqual(positions, [])

    def test_free_drop_uses_free_weights_without_super_conversion(self):
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
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        win_items = self.math.cal_item_list(
            board,
            return_detail=True,
            free_game=True,
        )["items"]
        with (
            patch.object(
                self.math,
                "weighted_random_index",
                return_value=1,
            ) as chooser,
            patch("theme_math.random.randrange", return_value=0),
        ):
            result, drop_info = self.math.drop_cluster_symbols(
                board,
                win_items,
                state,
                free_game=True,
            )
        self.assertEqual(
            chooser.call_args_list[0].args[0],
            self.math.FREE_DROP_SPECIAL_SYMBOL_WEIGHTS,
        )
        self.assertEqual(
            drop_info["special_placements"][0]["symbol_id"],
            self.math.FREE_SPIN_ID,
        )
        self.assertFalse(
            drop_info["special_placements"][0]["is_super_scatter"]
        )
        self.assertEqual(drop_info["super_scatter_positions"], [])
        self.assertEqual(
            self.math.count_symbol(result, self.math.FREE_SPIN_ID),
            1,
        )

    def test_super_scatter_position_moves_with_surviving_scatter(self):
        board = [
            [0, 12, 12, 12, 4],
            [5, 12, 12, 6, 7],
            [8, 9, 10, 11, 12],
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
        ]
        state = {
            "source_type": "normal",
            "columns": [
                [5, 6, 7],
                [8, 9],
                [3],
                [4],
                [5],
                [6],
            ],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        win_items = self.math.cal_item_list(board, return_detail=True)["items"]
        with patch.object(
            self.math,
            "choose_drop_special_symbol_id",
            return_value=None,
        ):
            result, drop_info = self.math.drop_cluster_symbols(
                board,
                win_items,
                state,
                super_scatter_positions={(0, 0)},
            )
        self.assertEqual(drop_info["super_scatter_positions"], [(0, 3)])
        self.assertEqual(result[0][3], self.math.FREE_SPIN_ID)

    def test_game_config_only_contains_common_math_fields(self):
        game_config = self.math._read_config_file(
            self.math.project_dir / self.math.DEFAULT_GAME_CONFIG_FILE
        )["MAIN"]
        allowed_fields = {
            "VERSION",
            "COL_COUNT",
            "ROW_COUNT",
            "ITEM_COUNT",
            "PRIZE_RATE",
            "LINE_MODE",
            "USE_WILDS",
            "BASE_NUMS",
            "BOTH_SIDES",
            "FULL_WILD_LINE",
            "RULE_COUNT",
            "SCATTER_MODE",
            "SCATTER_ID",
            "SCATTER_COLS",
            "SCATTER_SERIAL",
            "SCATTER_MULTIPLES",
            "SCATTER_PRIZES",
            "GRID_DISABLES",
            "GRID_DISABLES_FREE",
        }
        unexpected_fields = {
            key
            for key in game_config
            if key not in allowed_fields
            and not key.startswith("ITEM_PRIZES_")
            and not key.startswith("LINE_RULES_")
        }
        self.assertEqual(unexpected_fields, set())

        moved_fields = {
            "WILD_ID": 1,
            "FEATURE_ID": 2,
            "BONUS_ID": 2,
            "COIN_ID": 2,
            "CLOVER_ID": 2,
            "POT_ID": 2,
            "MULTIPLIER_ID": 2,
            "COLLECTOR_ID": 2,
            "JACKPOT_ID": 2,
        }
        for key, value in moved_fields.items():
            self.assertNotIn(key, game_config)
            self.assertEqual(getattr(self.math, key), value)

    def test_special_symbol_probability_config(self):
        self.assertEqual(self.math.SCATTER_COUNT_WEIGHTS, (10000, 1000, 500, 57))
        self.assertEqual(
            self.math.FREE_SCATTER_COUNT_WEIGHTS,
            (10000, 1000, 500, 57),
        )
        self.assertEqual(
            self.math.BASE_NO_WIN_BONUS_COUNT_WEIGHTS,
            (98, 2),
        )
        self.assertEqual(self.math.BASE_WIN_BONUS_COUNT_WEIGHTS, (92, 8))
        self.assertEqual(
            self.math.FREE_GOLDEN_BONUS_COUNT_WEIGHTS,
            (60, 40),
        )
        self.assertEqual(
            self.math.FREE_NO_GOLDEN_BONUS_COUNT_WEIGHTS,
            (30, 70),
        )
        self.assertEqual(self.math.DROP_SPECIAL_SYMBOL_WEIGHTS, (998, 1, 1))
        self.assertEqual(
            self.math.FREE_DROP_SPECIAL_SYMBOL_WEIGHTS,
            (998, 1, 1),
        )

    def test_base_bonus_count_uses_win_specific_weights(self):
        no_win_board = [
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
            [8, 9, 10, 11, 12],
        ]
        win_board = [
            [12, 12, 12, 3, 4],
            [12, 12, 5, 6, 7],
            [8, 9, 10, 11, 12],
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
        ]
        with patch.object(
            self.math,
            "weighted_random_index",
            side_effect=[0, 1],
        ) as chooser:
            no_win_symbols = self.math.choose_initial_special_symbol_ids(
                no_win_board,
                free_game=False,
            )
        self.assertEqual(no_win_symbols, [self.math.FEATURE_ID])
        self.assertEqual(
            chooser.call_args_list[1].args[0],
            self.math.BASE_NO_WIN_BONUS_COUNT_WEIGHTS,
        )

        with patch.object(
            self.math,
            "weighted_random_index",
            side_effect=[0, 1],
        ) as chooser:
            win_symbols = self.math.choose_initial_special_symbol_ids(
                win_board,
                free_game=False,
            )
        self.assertEqual(win_symbols, [self.math.FEATURE_ID])
        self.assertEqual(
            chooser.call_args_list[1].args[0],
            self.math.BASE_WIN_BONUS_COUNT_WEIGHTS,
        )

        with patch.object(
            self.math,
            "weighted_random_index",
            side_effect=[2, 1],
        ) as chooser:
            scatter_symbols = self.math.choose_initial_special_symbol_ids(
                no_win_board,
                free_game=False,
            )
        self.assertEqual(scatter_symbols, [0, 0, self.math.FEATURE_ID])
        self.assertEqual(chooser.call_count, 2)
        self.assertEqual(
            chooser.call_args_list[1].args[0],
            self.math.BASE_NO_WIN_BONUS_COUNT_WEIGHTS,
        )

        with patch.object(
            self.math,
            "weighted_random_index",
            return_value=3,
        ) as chooser:
            scatter_only = self.math.choose_initial_special_symbol_ids(
                no_win_board,
                free_game=False,
            )
        self.assertEqual(scatter_only, [0, 0, 0])
        self.assertEqual(chooser.call_count, 1)

    def test_free_bonus_count_uses_golden_state_and_last_spin_guarantee(self):
        board = [
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
            [8, 9, 10, 11, 12],
        ]
        with patch.object(
            self.math,
            "weighted_random_index",
            side_effect=[0, 1],
        ) as chooser:
            symbols = self.math.choose_initial_special_symbol_ids(
                board,
                free_game=True,
                golden_squares={(0, 0)},
            )
        self.assertEqual(symbols, [self.math.FEATURE_ID])
        self.assertEqual(
            chooser.call_args_list[0].args[0],
            self.math.FREE_SCATTER_COUNT_WEIGHTS,
        )
        self.assertEqual(
            chooser.call_args_list[1].args[0],
            self.math.FREE_GOLDEN_BONUS_COUNT_WEIGHTS,
        )

        with patch.object(
            self.math,
            "weighted_random_index",
            side_effect=[0, 0],
        ):
            guaranteed = self.math.choose_initial_special_symbol_ids(
                board,
                free_game=True,
                remaining_spins=1,
                bonus_seen=False,
            )
        self.assertEqual(guaranteed, [self.math.FEATURE_ID])

    def test_special_symbols_replace_only_nonwinning_positions(self):
        board = [
            [12, 12, 12, 3, 4],
            [12, 12, 5, 6, 7],
            [8, 9, 10, 11, 12],
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
        ]
        before = self.math.cal_item_list(board, return_detail=True)
        with patch("theme_math.random.randrange", return_value=0):
            result, placements = self.math.place_special_symbols(
                board,
                [self.math.FREE_SPIN_ID, self.math.FEATURE_ID],
            )
        winning_positions = set(before["win_positions"])
        self.assertEqual(len(placements), 2)
        self.assertTrue(
            all(item["position"] not in winning_positions for item in placements)
        )
        self.assertEqual(
            self.math.cal_item_list(result),
            before["total_win"],
        )

    def test_dropped_scatters_are_counted_from_final_board(self):
        board = [
            [12, 12, 12, 3, 4],
            [12, 12, 5, 6, 7],
            [8, 9, 10, 11, 0],
            [3, 4, 5, 6, 0],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 9],
        ]
        state = {
            "source_type": "normal",
            "columns": [
                [5, 6, 7],
                [8, 9],
                [3],
                [4],
                [5],
                [6],
            ],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        with (
            patch.object(
                self.math,
                "choose_drop_special_symbol_id",
                return_value=0,
            ),
            patch("theme_math.random.randrange", side_effect=[0, 200]),
        ):
            result = self.math.evaluate_cascades(
                board,
                state,
                return_detail=True,
                feature_outcome={"activated": False},
            )
        self.assertEqual(result["scatter_count"], 3)
        self.assertTrue(result["is_trigger_free"])
        self.assertEqual(
            len(result["rounds"][0]["drop_info"]["special_placements"]),
            1,
        )
        self.assertEqual(
            result["next_free_golden_squares"],
            [],
        )

    def test_base_bonus_suppresses_later_drop_scatters(self):
        board = [
            [12, 12, 12, 3, 4],
            [12, 12, 5, 6, 7],
            [8, 9, 10, 11, 12],
            [3, 4, 5, 6, 7],
            [4, 5, 6, 7, 8],
            [5, 6, 7, 8, 2],
        ]
        state = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        win_items = self.math.cal_item_list(board, return_detail=True)["items"]
        with patch.object(
            self.math,
            "choose_drop_special_symbol_id",
            return_value=0,
        ) as chooser:
            result, drop_info = self.math.drop_cluster_symbols(
                board,
                win_items,
                state,
                free_game=False,
            )
        self.assertEqual(drop_info["special_placements"], [])
        self.assertEqual(drop_info["special_block_reason"], "bonus_present")
        chooser.assert_not_called()
        self.assertEqual(self.math.count_symbol(result, self.math.FEATURE_ID), 1)

    def test_base_drop_stops_after_first_special_symbol(self):
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
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        win_items = self.math.cal_item_list(board, return_detail=True)["items"]
        with (
            patch.object(
                self.math,
                "choose_drop_special_symbol_id",
                side_effect=[None, 2, 0],
            ) as chooser,
            patch("theme_math.random.randrange", return_value=0),
        ):
            _, drop_info = self.math.drop_cluster_symbols(
                board,
                win_items,
                state,
                free_game=False,
            )
        self.assertEqual(
            [
                placement["symbol_id"]
                for placement in drop_info["special_placements"]
            ],
            [self.math.FEATURE_ID],
        )
        self.assertEqual(chooser.call_count, 2)
        self.assertIsNone(drop_info["special_block_reason"])

    def test_base_dropped_scatter_can_convert_to_super_scatter(self):
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
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        win_items = self.math.cal_item_list(board, return_detail=True)["items"]
        with (
            patch.object(
                self.math,
                "choose_drop_special_symbol_id",
                return_value=self.math.FREE_SPIN_ID,
            ),
            patch("theme_math.random.randrange", side_effect=[0, 199]),
        ):
            result, drop_info = self.math.drop_cluster_symbols(
                board,
                win_items,
                state,
                free_game=False,
            )
        self.assertEqual(
            drop_info["special_placements"][0]["source_symbol_id"],
            self.math.FREE_SPIN_ID,
        )
        self.assertEqual(
            drop_info["special_placements"][0]["symbol_id"],
            self.math.FREE_SPIN_ID,
        )
        self.assertTrue(
            drop_info["special_placements"][0]["is_super_scatter"]
        )
        self.assertEqual(len(drop_info["super_scatter_positions"]), 1)
        self.assertEqual(
            self.math.count_symbol(result, self.math.FREE_SPIN_ID),
            1,
        )

    def test_base_drop_special_is_blocked_at_three_scatters(self):
        board = [
            [12, 12, 12, 3, 4],
            [12, 12, 5, 6, 7],
            [8, 9, 10, 11, 0],
            [3, 4, 5, 6, 0],
            [4, 5, 6, 7, 0],
            [5, 6, 7, 8, 9],
        ]
        state = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        win_items = self.math.cal_item_list(board, return_detail=True)["items"]
        with patch.object(
            self.math,
            "choose_drop_special_symbol_id",
            return_value=self.math.FEATURE_ID,
        ) as chooser:
            _, drop_info = self.math.drop_cluster_symbols(
                board,
                win_items,
                state,
                free_game=False,
            )
        self.assertEqual(drop_info["special_placements"], [])
        self.assertEqual(drop_info["special_block_reason"], "scatter_limit")
        chooser.assert_not_called()

    def test_last_free_spin_forces_bonus_when_none_was_seen(self):
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
        with patch("theme_math.random.randrange", return_value=0):
            result = self.math.evaluate_cascades(
                board,
                state,
                free_game=True,
                free_mode="free",
                remaining_spins=1,
                bonus_seen=False,
                feature_outcome={"activated": False},
            )
        self.assertEqual(result["bonus_count"], 1)
        self.assertTrue(result["free_bonus_seen"])
        self.assertEqual(len(result["forced_free_bonus_placements"]), 1)
        already_seen = self.math.evaluate_cascades(
            board,
            self.math.clone_spin_state(state),
            free_game=True,
            free_mode="free",
            remaining_spins=1,
            bonus_seen=True,
            feature_outcome={"activated": False},
        )
        self.assertEqual(already_seen["bonus_count"], 0)
        self.assertEqual(already_seen["forced_free_bonus_placements"], [])

    def test_last_free_spin_skips_guarantee_without_candidate(self):
        board = [[self.math.FREE_SPIN_ID] * 5 for _ in range(6)]
        state = {
            "source_type": "normal",
            "columns": [[3, 4, 5, 6, 7] for _ in range(6)],
            "top_indexes": [0] * 6,
            "row": 5,
            "col": 6,
        }
        with patch.object(
            self.math,
            "apply_super_scatter_conversion",
            side_effect=lambda item_list: (
                [list(column) for column in item_list],
                [],
            ),
        ):
            result = self.math.evaluate_cascades(
                board,
                state,
                free_game=True,
                free_mode="free",
                remaining_spins=1,
                bonus_seen=False,
                feature_outcome={"activated": False},
            )
        self.assertEqual(result["bonus_count"], 0)
        self.assertFalse(result["free_bonus_seen"])
        self.assertEqual(result["forced_free_bonus_placements"], [])

    @patch.object(ThemeMath, "choose_drop_special_symbol_id", return_value=None)
    def test_fix_results_never_win_and_zero_results_trigger_bonus(self, _drop_choice):
        configs = [
            (
                self.math._load_reel_config(0, 1),
                False,
            ),
            (
                self.math._load_reel_config(
                    0,
                    1,
                    reel_config_dir=self.math.FREE_REEL_CONFIG_DIR,
                    reel_file_template="yngg_free_rand_ex_{index}.conf",
                ),
                True,
            ),
        ]
        for config, free_game in configs:
            self.assertEqual(len(config["fix_results"]), 10)
            self.assertEqual(len(config["zero_results"]), 10)
            for fixed_result in config["fix_results"]:
                self.assertEqual(len(fixed_result), 30)
                board = self.math._split_result(fixed_result, 5, 6)
                self.assertEqual(self.math.cal_item_list(board), 0)
            for zero_result in config["zero_results"]:
                self.assertEqual(len(zero_result), 30)
                board = self.math._split_result(zero_result, 5, 6)
                spin_state = self.math._build_result_spin_state(
                    config["normal_rolls"],
                    5,
                    6,
                    "zero",
                )
                result = self.math.evaluate_cascades(
                    board,
                    spin_state,
                    free_game=free_game,
                    free_mode="free" if free_game else None,
                    feature_outcome={"activated": False},
                )
                self.assertGreaterEqual(result["cascade_count"], 1)
                self.assertEqual(result["bonus_count"], 1)
                self.assertTrue(result["is_trigger_feature"])

    def test_fixed_result_count_selects_only_first_entries(self):
        section = {
            "FIX_NUM": "2",
            "FIX_RESULT_1": "3,4",
            "FIX_RESULT_2": "5,6",
            "FIX_RESULT_3": "7,8",
        }
        self.assertEqual(self.math._collect_enabled_results(section, "FIX"),
                         [[3, 4], [5, 6]])
        section["FIX_NUM"] = "0"
        self.assertEqual(self.math._collect_enabled_results(section, "FIX"), [])
        section["FIX_NUM"] = "4"
        with self.assertRaisesRegex(ValueError, "FIX_RESULT_4"):
            self.math._collect_enabled_results(section, "FIX")

    def test_fixed_result_disorders_columns_and_refills_from_normal_rolls(self):
        for kind, disorder_key, result_key in (
            ("fix", "FixDisorder", "fix_results"),
            ("zero", "ZeroDisorder", "zero_results"),
        ):
            with self.subTest(Kind=kind):
                config = dict(self.math._load_reel_config(0, 1))
                config[disorder_key] = True
                original = self.math._split_result(config[result_key][0], 5, 6)
                with patch.object(self.math, "_load_reel_config", return_value=config), \
                     patch.object(self.math, "_choose_spin_type", return_value=kind), \
                     patch.object(self.math, "_choose_result", return_value=config[result_key][0]), \
                     patch("random.shuffle", side_effect=lambda column: column.reverse()), \
                     patch("random.randrange", return_value=2):
                    board = self.math.spin(0, 1, 5, 6)
                self.assertEqual(board, [list(reversed(column)) for column in original])
                self.assertEqual(self.math.last_spin_state["columns"], config["normal_rolls"])
                self.assertEqual(self.math.last_spin_state["top_indexes"], [2] * 6)
                self.assertEqual(self.math.last_spin_state["source_type"],
                                 f"{kind}_result_normal_rolls")

    @patch.object(
        ThemeMath,
        "weighted_random_index",
        side_effect=[0, 14, 1, 5, 2, 3, 3],
    )
    def test_bonus_position_chooses_type_before_specific_value(self, chooser):
        result = self.math.generate_golden_round(
            {(0, 0), (1, 0), (2, 0), (3, 0)}
        )
        self.assertEqual(
            result,
            [
                {
                    "position": [0, 0],
                    "type": "coin",
                    "value": 500,
                    "coin_tier": "gold",
                },
                {"position": [1, 0], "type": "clover", "multiplier": 20},
                {"position": [2, 0], "type": "pot"},
                {"position": [3, 0], "type": "jackpot", "tier": "grand"},
            ],
        )
        self.assertEqual(
            [item.args[0] for item in chooser.call_args_list],
            [
                self.math.BONUS_SYMBOL_TYPE_WEIGHTS,
                self.math.COIN_VALUE_WEIGHTS,
                self.math.BONUS_SYMBOL_TYPE_WEIGHTS,
                self.math.CLOVER_MULTIPLIER_WEIGHTS,
                self.math.BONUS_SYMBOL_TYPE_WEIGHTS,
                self.math.BONUS_SYMBOL_TYPE_WEIGHTS,
                self.math.JACKPOT_TYPE_WEIGHTS,
            ],
        )

    def test_generated_pot_rerolls_only_non_pot_positions(self):
        first_round = [
            {"position": [0, 0], "type": "pot"},
            {"position": [1, 0], "type": "coin", "value": 1},
        ]
        second_round = [
            {"position": [1, 0], "type": "coin", "value": 5},
        ]
        with patch.object(
            self.math,
            "generate_golden_round",
            side_effect=[first_round, second_round],
        ) as generator:
            rounds = self.math.generate_golden_rounds({(0, 0), (1, 0)})
        self.assertEqual(rounds, [first_round, second_round])
        self.assertEqual(generator.call_args_list[0].args[0], {(0, 0), (1, 0)})
        self.assertEqual(generator.call_args_list[1].args[0], {(1, 0)})

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

    @patch.object(ThemeMath, "choose_drop_special_symbol_id", return_value=None)
    def test_cascade_removes_only_winning_cluster_positions(self, _drop_choice):
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
            self.math.get_triggered_free_spin_mode(1, 2),
            {"name": "super_free", "spins": 10},
        )
        self.assertEqual(
            self.math.get_triggered_free_spin_mode(3, 0),
            {"name": "free", "spins": 10},
        )
        self.assertEqual(self.math.get_retrigger_spins(2), 2)
        self.assertEqual(self.math.get_retrigger_spins(3), 4)
        self.assertEqual(self.math.get_retrigger_spins(4), 4)

    def test_free_counts_are_loaded_from_custom_config(self):
        source = self.math.project_dir / self.math.DEFAULT_GAME_SERVER_CONFIG_FILE
        text = source.read_text().replace("FreeSpinCounts=10,10", "FreeSpinCounts=7,13")
        text = text.replace("FreeSpinRetrigger=0,0,2,4", "FreeSpinRetrigger=0,0,3,6")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "custom.conf"
            path.write_text(text)
            game = ThemeMath(game_server_config_file=str(path))
        self.assertEqual(game.get_triggered_free_spin_mode(3)["spins"], 7)
        self.assertEqual(game.get_triggered_free_spin_mode(2, 1)["spins"], 13)
        self.assertIsNone(game.get_triggered_free_spin_mode(2))
        self.assertEqual([game.get_retrigger_spins(n) for n in range(5)], [0, 0, 3, 6, 6])

    def test_invalid_free_counts_fail_during_loading(self):
        for field, value in [("FreeSpinCounts", "10"), ("FreeSpinCounts", "0,10"),
                             ("FreeSpinRetrigger", "0,2,4"),
                             ("FreeSpinRetrigger", "0,0,-2,4")]:
            with self.subTest(Field=field, Value=value):
                self.math.game_server_config["Game Info"][field] = value
                with self.assertRaisesRegex(ValueError, field):
                    self.math._load_super_scatter_config()
                self.math.game_server_config["Game Info"][field] = (
                    "10,10" if field == "FreeSpinCounts" else "0,0,2,4"
                )

    def test_missing_types_do_not_fall_back_to_zero(self):
        for index in (0, 4, 8, 12, 17):
            with self.subTest(Type=index):
                self.math._load_reel_config(index, 1)
                self.assertEqual(self.math.ActiveTypeIndex, index)
                self.math._load_reel_config(
                    index, 1, "free_reel_config", "yngg_free_rand_ex_{index}.conf"
                )
                self.assertEqual(self.math.ActiveTypeIndex, index)
        for method in (self.math.ng_spin, self.math.fg_spin):
            with self.assertRaisesRegex(ValueError, "TYPE 9"):
                method(index=9)
        self.math.game_server_config.remove_section("0")
        with self.assertRaisesRegex(ValueError, r"TYPE \[0\]"):
            self.math._load_super_scatter_config()

    def test_type_probabilities_follow_selected_reels(self):
        original = self.math.game_server_config["4"]["ScatterCountProbability"]
        self.math.game_server_config["4"]["ScatterCountProbability"] = "1,2,3,4"
        try:
            self.math._load_reel_config(4, 1)
            self.assertEqual(self.math.SCATTER_COUNT_WEIGHTS, (1, 2, 3, 4))
            self.math._load_reel_config(0, 1)
            self.assertEqual(self.math.SCATTER_COUNT_WEIGHTS, (10000, 1000, 500, 57))
        finally:
            self.math.game_server_config["4"]["ScatterCountProbability"] = original

    def test_missing_type_reel_cannot_fall_back(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "special").mkdir()
            (root / "reel_config").mkdir()
            (root / "free_reel_config").mkdir()
            source = Path(__file__).resolve().parent
            for name in ("yngg_game_config.conf", "yngg_game_server.conf", "yngg_bonus.conf"):
                (root / "special" / name).write_bytes((source / "special" / name).read_bytes())
            for name in ("yngg_rand_main.conf", "yngg_rand_ex_0.conf"):
                (root / "reel_config" / name).write_bytes((source / "reel_config" / name).read_bytes())
            game = ThemeMath(project_dir=root)
            with self.assertRaisesRegex(FileNotFoundError, "TYPE 4"):
                game.ng_spin(index=4)

    def test_base_free_trigger_does_not_seed_golden_squares(self):
        board = [
            [0, 3, 4, 5, 6],
            [0, 4, 5, 6, 7],
            [0, 5, 6, 7, 8],
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
            super_scatter_positions={(2, 0)},
        )
        self.assertEqual(result["free_mode"], "super_free")
        self.assertEqual(result["scatter_count"], 2)
        self.assertEqual(result["super_scatter_count"], 1)
        self.assertEqual(result["super_scatter_positions"], [(2, 0)])
        self.assertEqual(result["final_item_list"][2][0], self.math.FREE_SPIN_ID)
        self.assertEqual(
            result["next_free_golden_squares"],
            [],
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

    def test_bonus_is_generated_when_no_outcome_is_injected(self):
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
        with patch.object(
            self.math,
            "generate_golden_rounds",
            return_value=[
                [{"position": [0, 0], "type": "coin", "value": 5}]
            ],
        ):
            result = self.math.evaluate_cascades(
                board,
                state,
                golden_squares={(0, 0)},
            )
        self.assertTrue(result["is_trigger_feature"])
        self.assertTrue(result["feature_outcome_generated"])
        self.assertFalse(result["feature_outcome_injected"])
        self.assertEqual(result["feature_win"], self.math.base_bet * 5)
        self.assertEqual(
            result["golden_rounds"],
            [[{"position": [0, 0], "type": "coin", "value": 5}]],
        )
        self.assertEqual(
            result["feature_cells"],
            [
                {
                    "position": (0, 0),
                    "type": "coin",
                    "value": 5.0,
                    "coin_tier": "silver",
                }
            ],
        )
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


class ServerConfigTest(unittest.TestCase):
    def check_server_config(self, root):
        read = ThemeMath._read_config_file
        server = read(root / "special/yngg_game_server.conf")
        for index in (0, 4, 8, 12, 17):
            self.assertTrue(server.has_section(str(index)))
            self.assertIn("ScatterCountProbability", server[str(index)])
        self.assertNotIn("ScatterCountProbability", server["Game Info"])
        self.assertEqual(server["System Base Info"]["BetScopes"],
                         "10,20,50,100,200,500,1000,2000,2500")
        groups = read(root / "special_config/slot_control_group.conf")
        self.assertEqual(groups.sections(), ["MAIN", "CONTROL_GROUP_0",
                                             "CONTROL_GROUP_4", "CONTROL_GROUP_8",
                                             "CONTROL_GROUP_12", "CONTROL_GROUP_17"])
        expected = [5000, 0, 0, 0, 12000, 0, 0, 0, 1000,
                    0, 0, 0, 20, 0, 0, 0, 0, 1000]
        for key in ("control_group_cut_multiple", "control_group_free_cut_multiple"):
            self.assertEqual(ThemeMath._parse_int_list(groups["MAIN"][key]), expected)
        for section in groups.sections()[1:]:
            values = ThemeMath._parse_int_list(groups[section]["lable_user_control_group_value"])
            rates = ThemeMath._parse_int_list(groups[section]["lable_user_control_group_rate"])
            self.assertEqual(len(values), len(rates))
            for value in values:
                type_index, number = divmod(value, 100)
                self.assertGreater(number, 0)
                self.assertIn(str(type_index), server)
                for directory, prefix in [("reel_config", "yngg"),
                                          ("free_reel_config", "yngg_free")]:
                    path = root / directory / f"{prefix}_rand_ex_{type_index}.conf"
                    reel = read(path)
                    spec = read(root / directory / f"{prefix}_rand_main.conf")["MAIN"]
                    self.assertEqual(int(spec["VERSION"]), 101)
                    self.assertEqual(int(spec["COL_COUNT"]), 6)
                    self.assertEqual(int(spec["ITEM_COM_COUNT"]),
                                     len([s for s in reel if s.startswith("GENERAL_")]))
                    for kind in ("NORMAL_ROLL", "SP_ROLL"):
                        for column in range(1, 7):
                            value = reel["GENERAL_1"][f"{kind}_{column}"]
                            symbols = ThemeMath._parse_int_list(value)
                            self.assertLess(len(value.encode("utf-8")), 400)
                            self.assertLessEqual(len(symbols), 200)
                            self.assertGreaterEqual(len(symbols), 5)
                            self.assertTrue(all(0 <= s < int(spec["ITEM_COUNT"]) for s in symbols))
        global_config = read(root / "special_config/game_server.conf")["Game_Info"]
        self.assertEqual(int(global_config["replay_min_win_money"]), 3_000_000_000)

    def test_published_configs_meet_server_constraints(self):
        self.check_server_config(Path(__file__).resolve().parent)

    def test_reel_compaction_preserves_symbols_and_both_limits(self):
        reel = [12] * 220 + [1, 3]
        result = build_from_demo.fit_server_reel(reel)
        self.assertEqual(set(result), {1, 3, 12})
        self.assertLessEqual(len(result), 200)
        self.assertLess(len(",".join(map(str, result)).encode("utf-8")), 400)
        self.assertEqual(result, build_from_demo.fit_server_reel(reel))
        self.assertEqual(result, build_from_demo.fit_server_reel(result))
        self.assertEqual(build_from_demo.fit_server_reel([3, 4, 5, 6, 7]), [3, 4, 5, 6, 7])

    def test_existing_type_reel_is_shortened_without_other_changes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "yngg_rand_ex_4.conf"
            roll = ",".join(map(str, [12] * 220 + [1, 3]))
            path.write_text(f"[GENERAL_1]\nNORMAL_ROLL_1={roll}\n# retained tuning\n",
                            encoding="utf-8")
            build_from_demo.fit_existing_reel_file(path)
            result = path.read_text(encoding="utf-8")
            self.assertIn("# retained tuning", result)
            value = result.split("NORMAL_ROLL_1=", 1)[1].splitlines()[0]
            self.assertLess(len(value.encode("utf-8")), 400)
            self.assertEqual(set(ThemeMath._parse_int_list(value)), {1, 3, 12})

    def test_regeneration_keeps_server_fixes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "numeric").mkdir()
            (root / "numeric/game-math.json").write_text("{}")
            with patch.object(build_from_demo, "THEME_DIR", root), patch.object(
                build_from_demo, "load_strip", return_value=[[12] * 220 + [1, 3]] * 6
            ):
                build_from_demo.main(["--demo-dir", str(root)])
                server_path = root / "special/yngg_game_server.conf"
                server_text = server_path.read_text(encoding="utf-8")
                server_path.write_text(server_text.replace(
                    "[4]\n", "[4]\n# retained TYPE tuning\n", 1
                ), encoding="utf-8")
                reel_path = root / "reel_config/yngg_rand_ex_4.conf"
                reel_path.write_text(reel_path.read_text(encoding="utf-8") +
                                     "# retained reel tuning\n", encoding="utf-8")
                prop_path = root / "special/slot_prop_config.conf"
                prop_path.write_text(prop_path.read_text(encoding="utf-8") +
                                     "# retained prop config\n", encoding="utf-8")
                group_path = root / "special_config/slot_control_group.conf"
                group_path.write_text(group_path.read_text(encoding="utf-8").replace(
                    "[CONTROL_GROUP_4]\n", "[CONTROL_GROUP_4]\n# retained GROUP tuning\n", 1
                ), encoding="utf-8")
                build_from_demo.main(["--demo-dir", str(root)])
                self.assertIn("# retained TYPE tuning", server_path.read_text(encoding="utf-8"))
                self.assertIn("# retained reel tuning", reel_path.read_text(encoding="utf-8"))
                self.assertIn("# retained prop config", prop_path.read_text(encoding="utf-8"))
                self.assertIn("# retained GROUP tuning", group_path.read_text(encoding="utf-8"))
            self.check_server_config(root)
            game = ThemeMath(project_dir=root)
            self.assertEqual(game.get_triggered_free_spin_mode(3)["spins"], 10)


if __name__ == "__main__":
    unittest.main()
