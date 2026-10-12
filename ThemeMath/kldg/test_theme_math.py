"""恐龙帝国结果规则的关键场景检查。"""

import random
import unittest
from unittest.mock import patch

import simulation
from theme_math import Cell, ThemeMath


class ThemeMathTests(unittest.TestCase):
    def setUp(self):
        random.seed(20261010)
        self.game = ThemeMath()
        self.game.SilverFrameChance = 0

    def test_three_column_ways_uses_total_bet_paytable(self):
        board = [
            [Cell(2), Cell(8)],
            [Cell(2), Cell(9)],
            [Cell(2), Cell(10)],
            [Cell(3), Cell(11)],
            [Cell(4), Cell(12)],
            [Cell(5), Cell(7)],
        ]
        win, positions, _ = self.game._evaluate_paths(board)
        self.assertEqual(win, 3 * self.game.base_bet)
        self.assertEqual(positions, {(0, 0), (1, 0), (2, 0)})

    def test_wild_path_pays_only_the_highest_symbol(self):
        board = [
            [Cell(1), Cell(0)],
            [Cell(1), Cell(0)],
            [Cell(1), Cell(0)],
            [Cell(11), Cell(12)],
            [Cell(2), Cell(3)],
            [Cell(4), Cell(5)],
        ]
        win, _, items = self.game._evaluate_paths(board)
        self.assertEqual(win, 3 * self.game.base_bet)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["ItemId"], 2)
        plain_board = [[cell.SymbolId for cell in column] for column in board]
        self.assertEqual(self.game.cal_item_list(plain_board), win)

    def test_frame_moves_with_replacement_then_becomes_wild(self):
        board = [[Cell(8), Cell(9)] for _ in range(6)]
        board[1][0] = Cell(2, 1)
        state = {
            "source_type": "rolls",
            "columns": [[8, 9, 10] for _ in range(6)],
            "top_indexes": [1] * 6,
            "row": 2,
            "col": 6,
        }
        board, _ = self.game._advance_board(board, {(1, 0), (1, 1)}, state)
        self.assertEqual(board[1][1].FrameStage, 2)
        self.assertIn(board[1][1].SymbolId, self.game.OrdinaryIds)
        board, _ = self.game._advance_board(board, {(1, 1)}, state)
        self.assertEqual(board[1][1], Cell(1))

    def test_scatter_counts_initial_and_refill_in_both_modes(self):
        self.game.ReelHeightWeights = [[1, 0, 0, 0, 0] for _ in range(6)]
        raw_board = [
            [2, 0, 8, 9, 10, 11],
            [2, 0, 8, 9, 10, 11],
            [2, 8, 9, 10, 11, 12],
            [3, 9, 10, 11, 12, 8],
            [4, 10, 11, 12, 8, 9],
            [5, 11, 12, 8, 9, 10],
        ]

        def fake_spin(**kwargs):
            self.game.last_spin_state = {
                "source_type": "rolls",
                "columns": [
                    [0, 2, 8, 9], [0, 2, 8, 9], [8, 2, 9, 10],
                    [8, 2, 9, 10], [8, 2, 9, 10], [8, 2, 9, 10],
                ],
                "top_indexes": [1, 1, 1, 1, 1, 1],
                "row": 6,
                "col": 6,
            }
            return raw_board

        self.game.spin = fake_spin
        main = self.game.ng_spin(return_detail=True)
        self.assertEqual(main["ScatterCount"], 4)
        self.assertEqual(main["FreeSpinsAwarded"], 8)
        free = self.game.fg_spin(FreeSpinNumber=3, return_detail=True)
        self.assertEqual(free["ScatterCount"], 4)
        self.assertEqual(free["ExtraFreeSpins"], 4)
        self.assertEqual(free["Rounds"][0]["Multiplier"], 3)

    def test_main_multiplier_caps_at_five_and_free_multiplier_keeps_growing(self):
        self.game.ReelHeightWeights = [[1, 0, 0, 0, 0] for _ in range(6)]

        def fake_spin(**kwargs):
            self.game.last_spin_state = {
                "source_type": "rolls",
                "columns": [[8] for _ in range(6)],
                "top_indexes": [0] * 6,
                "row": 6,
                "col": 6,
            }
            return [[8] * 6 for _ in range(6)]

        self.game.spin = fake_spin
        self.game._advance_board = lambda board, positions, state: (board, 0)

        def run_with_six_cascades(free_spin_number):
            calls = 0

            def fake_evaluate(board):
                nonlocal calls
                calls += 1
                return (
                    self.game.base_bet,
                    {(0, 0)},
                    [{"ItemId": 2, "Win": self.game.base_bet}],
                ) if calls <= 6 else (0, set(), [])

            self.game._evaluate_paths = fake_evaluate
            if free_spin_number is None:
                return self.game.ng_spin(return_detail=True)
            return self.game.fg_spin(FreeSpinNumber=free_spin_number, return_detail=True)

        main = run_with_six_cascades(None)
        self.assertEqual([round_["Multiplier"] for round_ in main["Rounds"]], [1, 2, 3, 4, 5, 5])
        self.assertEqual(main["TotalWin"], 20 * self.game.base_bet)
        self.assertTrue(all(
            round_["Win"] == sum(item["Win"] for item in round_["WinItems"])
            and round_["BaseWin"] == sum(item["BaseWin"] for item in round_["WinItems"])
            for round_ in main["Rounds"]
        ))

        free = run_with_six_cascades(3)
        self.assertEqual([round_["Multiplier"] for round_ in free["Rounds"]], [3, 4, 5, 6, 7, 8])
        self.assertEqual(free["TotalWin"], 33 * self.game.base_bet)

    def test_each_ways_path_pays_once_when_multiple_symbols_match_wild(self):
        board = [
            [Cell(1), Cell(1)],
            [Cell(1)],
            [Cell(1)],
            [Cell(0)],
            [Cell(0)],
            [Cell(0)],
        ]
        win, positions, items = self.game._evaluate_paths(board)
        self.assertEqual(win, 6 * self.game.base_bet)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["ItemId"] == 2 for item in items))
        self.assertEqual(positions, {(0, 0), (0, 1), (1, 0), (2, 0)})

    def test_shared_wild_prefix_pays_only_the_highest_award(self):
        board = [[Cell(1)] for _ in range(4)] + [[Cell(8)], [Cell(0)]]
        win, _, items = self.game._evaluate_paths(board)
        self.assertEqual(win, 4 * self.game.base_bet)
        self.assertEqual([(item["ItemId"], item["HitCount"]) for item in items], [(2, 4)])

    def test_all_ordinary_symbol_prizes_are_one_tenth_of_original_table(self):
        OriginalPrizes = [
            [30, 40, 60, 150], [20, 25, 50, 80], [10, 25, 40, 60],
            [8, 15, 20, 30], [6, 10, 12, 15], [6, 10, 12, 15],
            [4, 6, 8, 10], [4, 6, 8, 10], [1, 2, 3, 4],
            [1, 2, 3, 4], [1, 2, 3, 4],
        ]
        for SymbolId, Prizes in enumerate(OriginalPrizes, start=2):
            with self.subTest(SymbolId=SymbolId):
                self.assertEqual(self.game.config.item_prizes[SymbolId][:2], [0, 0])
                self.assertEqual(
                    self.game.config.item_prizes[SymbolId][2:],
                    [Prize * self.game.BET_UNIT // 10 for Prize in Prizes],
                )
        self.assertEqual(self.game.config.item_prizes[0], [0] * 6)
        self.assertEqual(self.game.config.item_prizes[1], [0] * 6)

    def test_free_spin_number_advances_even_without_a_win_or_with_extra_spins(self):
        free_numbers = []

        class FakeGame:
            def __init__(self, base_bet):
                pass

            def ng_spin(self, **kwargs):
                return {"TotalWin": 0, "FreeSpinsAwarded": 2}

            def fg_spin(self, FreeSpinNumber, **kwargs):
                free_numbers.append(FreeSpinNumber)
                return {"TotalWin": 0, "ExtraFreeSpins": 1 if FreeSpinNumber == 1 else 0}

        with patch.object(simulation, "ThemeMath", FakeGame):
            result = simulation.simulate(1)
        self.assertEqual(free_numbers, [1, 2, 3])
        self.assertEqual(result["FreeSpins"], 3)

    def test_sample_special_fixed_and_zero_results_load_in_both_modes(self):
        self.game.ReelHeightWeights = [[1, 0, 0, 0, 0] for _ in range(6)]
        for FreeMode in (False, True):
            for SpinType in ("special", "fix", "zero"):
                with self.subTest(FreeMode=FreeMode, SpinType=SpinType):
                    with patch.object(self.game, "_choose_spin_type", return_value=SpinType):
                        Result = (
                            self.game.fg_spin(FreeSpinNumber=1, return_detail=True)
                            if FreeMode else self.game.ng_spin(return_detail=True)
                        )
                    self.assertEqual(self.game.last_spin_info["spin_type"], SpinType)
                    self.assertEqual(Result["ReelHeights"], [2] * 6)
                    if SpinType == "fix":
                        self.assertEqual(
                            [Column[0]["SymbolId"] for Column in Result["InitialBoard"][:3]],
                            [8, 8, 8],
                        )
                        self.assertEqual(Result["Rounds"][0]["BaseWin"], 4000)
                    elif SpinType == "zero":
                        self.assertEqual(Result["TotalWin"], 0)
                        self.assertEqual(Result["CascadeCount"], 0)
                        self.assertEqual(Result["ScatterCount"], 0)


if __name__ == "__main__":
    unittest.main()
