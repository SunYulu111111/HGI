"""Regression coverage for reusing Cluster analysis across special placement."""

import unittest
from unittest.mock import patch

from theme_math import ThemeMath


class SpinAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.Math = ThemeMath()
        self.OtherColumns = [
            [5, 6, 7, 8, 9],
            [6, 7, 8, 9, 10],
            [7, 8, 9, 10, 11],
            [8, 9, 10, 11, 12],
            [9, 10, 11, 12, 4],
        ]

    def State(self, FirstColumn):
        return {
            "source_type": "normal_rolls",
            "columns": [FirstColumn] + [list(range(5, 10)) for _ in range(5)],
            "top_indexes": [0] * 6,
            "NextReelIndexes": [0] * 6,
            "row": 5,
            "col": 6,
        }

    def test_initial_special_remapped_to_paying_symbol_can_create_a_cluster(self):
        Board = [[3, 3, 3, 3, 4]] + self.OtherColumns
        for Detail in (False, True):
            with self.subTest(Detail=Detail):
                self.Math.last_spin_info = {"spin_type": "normal"}
                self.Math.last_spin_state = self.State([4, 5, 6, 7, 8])
                with (
                    patch.object(self.Math, "FEATURE_ID", 3),
                    patch.object(self.Math, "spin", return_value=Board),
                    patch.object(self.Math, "choose_initial_special_symbol_ids", return_value=[3]),
                    patch.object(self.Math, "choose_drop_special_symbol_id", return_value=None),
                    patch("theme_math.random.randrange", return_value=4),
                ):
                    Result = self.Math.ng_spin(
                        return_detail=Detail, feature_outcome={"activated": False},
                    )
                self.assertEqual(Result["cascade_count"], 1)
                self.assertEqual(Result["total_win"], self.Math.base_bet)
                self.assertEqual(bool(Result["rounds"]), Detail)

    def test_dropped_special_remapped_to_paying_symbol_can_create_next_cascade(self):
        Board = [[3] * 5] + self.OtherColumns
        for Detail in (False, True):
            with self.subTest(Detail=Detail):
                Choices = iter([None, None, None, None, 4])
                with patch.object(
                    self.Math, "choose_drop_special_symbol_id",
                    side_effect=lambda **Keywords: next(Choices, None),
                ):
                    Result = self.Math.evaluate_cascades(
                        Board,
                        self.State([4, 4, 4, 4, 5, 5, 6, 7, 8, 9]),
                        return_detail=Detail,
                        feature_outcome={"activated": False},
                    )
                self.assertEqual(Result["cascade_count"], 2)
                self.assertEqual(Result["total_win"], self.Math.base_bet * 2)
                self.assertEqual(len(Result["rounds"]), 2 if Detail else 0)

    def test_replacing_paying_wild_keeps_original_component_order(self):
        Board = [
            [3, 6, 4, 3, 4], [6, 7, 8, 9, 4], [3, 8, 9, 4, 11],
            [3, 9, 10, 11, 3], [4, 10, 4, 3, 4], [4, 4, 12, 5, 4],
        ]
        PlacedBoard = [Column[:] for Column in Board]
        PlacedBoard[0][3] = 0
        FinalBoard = [[5 + (Column + Row) % 8 for Row in range(5)] for Column in range(6)]
        with patch.object(self.Math, "WILD_ID", 3):
            Before = self.Math.cal_item_list(Board, return_detail=True)
            Expected = self.Math.cal_item_list(PlacedBoard, return_detail=True)
            self.assertNotEqual(Before["items"], Expected["items"])
            CandidateIndex = self.Math.get_nonwinning_symbol_positions(Board).index((0, 3))
            self.Math.last_spin_info = {"spin_type": "normal"}
            self.Math.last_spin_state = self.State([5, 6, 7, 8, 9])
            with (
                patch.object(self.Math, "spin", return_value=Board),
                patch.object(self.Math, "choose_initial_special_symbol_ids", return_value=[0]),
                patch.object(self.Math, "apply_super_scatter_conversion", return_value=(PlacedBoard, [])),
                patch.object(self.Math, "drop_cluster_symbols", return_value=(FinalBoard, {})),
                patch("theme_math.random.randrange", return_value=CandidateIndex),
            ):
                Result = self.Math.ng_spin(return_detail=True, feature_outcome={"activated": False})
        self.assertEqual(Result["total_win"], Expected["total_win"])
        self.assertEqual(Result["rounds"][0]["win_items"], Expected["items"])

    def test_replacing_dropped_paying_wild_keeps_next_component_order(self):
        RefilledBoard = [
            [3, 6, 4, 3, 4], [6, 7, 8, 9, 4], [3, 8, 9, 4, 11],
            [3, 9, 10, 11, 3], [4, 10, 4, 3, 4], [4, 4, 12, 5, 4],
        ]
        PlacedBoard = [Column[:] for Column in RefilledBoard]
        PlacedBoard[0][3] = 0
        FinalBoard = [[5 + (Column + Row) % 8 for Row in range(5)] for Column in range(6)]
        State = self.State(RefilledBoard[0])
        State["columns"] = RefilledBoard
        with patch.object(self.Math, "WILD_ID", 3):
            Expected = self.Math.cal_item_list(PlacedBoard, return_detail=True)
            CandidateIndex = self.Math.get_nonwinning_symbol_positions(RefilledBoard).index((0, 3))
            Choices = iter([None] * CandidateIndex + [0])
            OriginalDrop = self.Math.drop_cluster_symbols
            DropCount = 0

            def Drop(*Arguments, **Keywords):
                nonlocal DropCount
                DropCount += 1
                if DropCount == 1:
                    return OriginalDrop(*Arguments, **Keywords)
                return FinalBoard, {}

            with (
                patch.object(self.Math, "drop_cluster_symbols", side_effect=Drop),
                patch.object(self.Math, "choose_drop_special_symbol_id", side_effect=lambda **Keywords: next(Choices, None)),
                patch.object(self.Math, "apply_super_scatter_conversion", return_value=(PlacedBoard, [])),
            ):
                Result = self.Math.evaluate_cascades(
                    [[12] * 5 for _ in range(6)], State,
                    return_detail=True, feature_outcome={"activated": False},
                )
        self.assertEqual(Result["cascade_count"], 2)
        self.assertEqual(Result["total_win"], self.Math.base_bet // 2 + Expected["total_win"])
        self.assertEqual(Result["rounds"][1]["win_items"], Expected["items"])


if __name__ == "__main__":
    unittest.main()
