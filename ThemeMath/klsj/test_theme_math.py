"""恐龙世界结算、图标生成和免费倍数的场景测试。"""

from configparser import ConfigParser
import random
import shutil
import tempfile
import unittest
from pathlib import Path
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

    def test_numeric_controls_are_loaded_from_game_server(self):
        source_dir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            for directory in ("special", "reel_config", "free_reel_config"):
                shutil.copytree(source_dir / directory, project_dir / directory)
            server_path = project_dir / "special/klsj_game_server.conf"
            server_text = server_path.read_text(encoding="utf-8")
            server_text = server_text.replace("MainMultiplierCap=5", "MainMultiplierCap=7")
            server_text = server_text.replace(
                "FreeSpinMultiplierIncrementCap=4", "FreeSpinMultiplierIncrementCap=6"
            )
            server_text = server_text.replace("FreeTriggerScatterCount=4", "FreeTriggerScatterCount=5")
            server_text = server_text.replace("BaseFreeSpins=8", "BaseFreeSpins=10")
            server_text = server_text.replace(
                "MainExtraFreeSpinsPerScatter=2", "MainExtraFreeSpinsPerScatter=3"
            )
            server_text = server_text.replace("BaseMaxEliTimes = 100", "BaseMaxEliTimes = 7")
            server_text = server_text.replace("Free_Max_EliTimes = 100", "Free_Max_EliTimes = 9")
            Server = ConfigParser(inline_comment_prefixes=("#", ";"))
            Server.optionxform = str
            Server.read_string(server_text)
            Server["Game Info"]["Free_Max_Times"] = "37"
            with server_path.open("w") as Output:
                Server.write(Output)

            game = ThemeMath(project_dir=project_dir)

        self.assertEqual(game.MainMultiplierCap, 7)
        self.assertEqual(game.FreeSpinMultiplierIncrementCap, 6)
        self.assertEqual(game.FreeTriggerScatterCount, 5)
        self.assertEqual(game.BaseFreeSpins, 10)
        self.assertEqual(game.MainExtraFreeSpinsPerScatter, 3)
        self.assertEqual(game.FreeExtraSpinsPerScatter, 1)
        self.assertEqual(game.BaseMaxEliTimes, 7)
        self.assertEqual(game.FreeMaxEliTimes, 9)
        self.assertEqual(game.FreeMaxTimes, 37)

    def test_reference_elimination_limits_are_used_in_both_modes(self):
        self.game.BaseMaxEliTimes = 2
        self.game.FreeMaxEliTimes = 3
        for FreeMode, Limit in ((False, 2), (True, 3)):
            with self.subTest(FreeMode=FreeMode):
                with (
                    patch.object(self.game, "_evaluate_paths", return_value=(100, {(0, 0)}, [])) as Evaluate,
                    patch.object(self.game, "_advance_board", side_effect=lambda Board, Wins, State: (Board, 0)),
                ):
                    with self.assertRaisesRegex(RuntimeError, f"max_cascades={Limit}"):
                        if FreeMode:
                            self.game.fg_spin()
                        else:
                            self.game.ng_spin()
                self.assertEqual(Evaluate.call_count, Limit + 1)

    def test_game_protocol_rejects_missing_wrong_size_and_unsupported_switches(self):
        Source = Path(__file__).resolve().parent / "special/klsj_game_config.conf"
        Changes = (
            ("BOTH_SIDES", None),
            ("BOTH_SIDES", "0,0"),
            ("BOTH_SIDES", "1," + ",".join(["0"] * 12)),
            ("FULL_WILD_LINE", "1"),
            ("GRID_DISABLES", ",".join(["0"] * 35)),
            ("GRID_DISABLES_FREE", "1," + ",".join(["0"] * 35)),
            ("GRID_DISABLES", "x," + ",".join(["0"] * 35)),
        )
        with tempfile.TemporaryDirectory() as TempDir:
            ConfigPath = Path(TempDir) / "game.conf"
            for Key, Value in Changes:
                with self.subTest(Field=Key, Value=Value):
                    Parser = ConfigParser()
                    Parser.optionxform = str
                    Parser.read(Source)
                    if Value is None:
                        del Parser["MAIN"][Key]
                    else:
                        Parser["MAIN"][Key] = Value
                    with ConfigPath.open("w") as Output:
                        Parser.write(Output)
                    with self.assertRaisesRegex(ValueError, Key):
                        self.game._validate_game_protocol(ConfigPath)
        self.assertEqual(self.game.config.grid_disables, [0] * 36)
        self.assertEqual(self.game.config.grid_disables_free, [0] * 36)

    def test_reel_details_load_from_general_sections_without_main(self):
        for Directory, Template in (
            ("reel_config", "klsj_rand_ex_{index}.conf"),
            ("free_reel_config", "klsj_free_rand_ex_{index}.conf"),
        ):
            with self.subTest(Directory=Directory):
                ConfigPath = self.game.project_dir / Directory / Template.format(index=0)
                Parser = ConfigParser()
                Parser.optionxform = str
                Parser.read(ConfigPath)
                self.assertEqual(Parser.sections(), ["GENERAL_1"])
                for SpinType in ("normal", "special", "fix", "zero"):
                    with patch.object(self.game, "_choose_spin_type", return_value=SpinType):
                        Board = self.game.spin(
                            index=0, general_index=1, row=6, col=6,
                            reel_config_dir=Directory, reel_file_template=Template,
                        )
                    self.assertEqual(self.game.last_spin_info["spin_type"], SpinType)
                    self.assertEqual([len(Column) for Column in Board], [6] * 6)

    def test_reference_height_layout_weights_are_loaded(self):
        self.assertEqual(
            self.game.MainHeightPatterns,
            [(1, 1, 1, 1, 1, 1), (1, 1, 1, 1, 2), (1, 1, 1, 3),
             (1, 1, 2, 2), (1, 1, 4), (1, 2, 3), (2, 2, 2), (2, 4), (3, 3)],
        )
        self.assertEqual(len(self.game.MainHeightWeights), 6)
        self.assertEqual(len(self.game.MainHeightWeights[0]), 9)
        self.assertEqual(len(self.game.MainEliminationHeightWeights[0][6]), 9)
        self.assertEqual(self.game._canonical_patterns(5), [(1, 1, 1, 1, 1), (1, 1, 1, 2), (1, 1, 3), (1, 2, 2), (1, 4), (2, 3)])

    def _server_config(self):
        server = ConfigParser(inline_comment_prefixes=("#", ";"))
        server.optionxform = str
        server.read(Path(__file__).resolve().parent / "special/klsj_game_server.conf")
        return server

    def _scatter_candidate_spin(self, **kwargs):
        self.game.last_spin_state = {
            "source_type": "rolls",
            "columns": [[0] * 12 + [8, 9, 9] for _ in range(6)],
            "top_indexes": [6] * 6,
            "row": 6,
            "col": 6,
        }
        return [[0] * 6 for _ in range(6)]

    def test_yjzr_fields_drive_each_column_height_and_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            source_dir = Path(__file__).resolve().parent
            for directory in ("special", "reel_config", "free_reel_config"):
                shutil.copytree(source_dir / directory, project_dir / directory)
            server = self._server_config()
            info = server["Game Info"]
            for column in range(1, 7):
                for mode in ("base", "free"):
                    # 为不同列和模式指定不同的初始布局。
                    index = column - 1 + (3 if mode == "free" else 0)
                    info[f"{mode}_height_weight_{column}"] = ",".join(
                        "1" if value == index else "0" for value in range(9)
                    )
                    for height in range(2, 7):
                        count = len(self.game._canonical_patterns(height))
                        info[f"{mode}_elim_height_weight_{column}_{height}"] = ",".join(
                            "1" if value == (column + int(mode == "free")) % count else "0"
                            for value in range(count)
                        )
            with (project_dir / "special/klsj_game_server.conf").open("w") as output:
                server.write(output)
            game = ThemeMath(project_dir=project_dir)
            for free_mode in (False, True):
                for column in range(6):
                    with self.subTest(FreeMode=free_mode, Col=column + 1):
                        expected_index = column + (3 if free_mode else 0)
                        self.assertEqual(
                            tuple(sorted(game._select_layout(6, column, free_mode, True))),
                            game._canonical_patterns(6)[expected_index],
                        )
                        for height in range(1, 7):
                            patterns = game._canonical_patterns(height)
                            index = (column + 1 + int(free_mode)) % len(patterns)
                            self.assertEqual(
                                tuple(sorted(game._select_layout(height, column, free_mode, False))),
                                patterns[index],
                            )
                            if height < 6:
                                self.assertEqual(
                                    tuple(sorted(game._select_layout(height, column, free_mode, True))),
                                    patterns[index],
                                )

    def test_yjzr_layouts_shuffle_after_selecting_partition(self):
        def ReverseLayout(layout):
            layout.reverse()

        for free_mode in (False, True):
            for initial in (False, True):
                with self.subTest(FreeMode=free_mode, Initial=initial):
                    with (
                        patch.object(self.game, "_weighted_index", return_value=5),
                        patch("theme_math.random.shuffle", side_effect=ReverseLayout) as shuffle,
                    ):
                        self.assertEqual(
                            self.game._select_layout(6, 0, free_mode, initial), (3, 2, 1)
                        )
                    shuffle.assert_called_once()
        self.assertEqual(self.game._select_layout(0, 0, False, False), ())

    def test_yjzr_layout_configuration_rejects_missing_old_and_bad_index_fields(self):
        changes = (
            ("base_height_weight_1", None),
            ("free_elim_height_weight_6_2", None),
            ("BaseMaxEliTimes", None),
            ("Free_Max_Times", None),
            ("MainHeightWeights1", "1,1,1,1,1,1,1,1,1"),
            ("MainEliminationHeightWeights1", "2:100,0"),
            ("MainHeightPatterns", "111111"),
            ("FreeMaxEliminationTimes", "100"),
            ("base_height_weight_7", "1,1,1,1,1,1,1,1,1"),
            ("free_elim_height_weight_1_1", "1"),
        )
        for key, value in changes:
            with self.subTest(Field=key):
                info = self._server_config()["Game Info"]
                if value is None:
                    del info[key]
                else:
                    info[key] = value
                with self.assertRaisesRegex(ValueError, key):
                    self.game._validate_layout_keys(info)

    def test_yjzr_layout_weights_reject_wrong_length_negative_and_zero(self):
        for value in ("1,1,1,1,1,1,1,1,1", "-1,2", "0,0", "x,1", "2:100,0"):
            with self.subTest(Value=value):
                info = self._server_config()["Game Info"]
                info["free_elim_height_weight_2_2"] = value
                with self.assertRaisesRegex(ValueError, "free_elim_height_weight_2_2"):
                    self.game._parse_elimination_column_weights(info, "free_elim_height_weight")

    def test_physical_height_weights_use_per_column_csv_fields(self):
        info = self._server_config()["Game Info"]
        for column in range(1, 7):
            info[f"ReelHeightWeights{column}"] = f"{column},0,0,0,1"
        self.assertEqual(
            self.game._parse_height_weights(info),
            [[column, 0, 0, 0, 1] for column in range(1, 7)],
        )
        info["ReelHeightWeights"] = "1,1,1,1,1|1,1,1,1,1"
        with self.assertRaisesRegex(ValueError, "per-column"):
            self.game._parse_height_weights(info)
        del info["ReelHeightWeights"]
        del info["ReelHeightWeights6"]
        with self.assertRaisesRegex(ValueError, "ReelHeightWeights6"):
            self.game._parse_height_weights(info)

    def test_server_values_are_flat_csv_and_have_reference_layout_fields(self):
        info = self._server_config()["Game Info"]
        self.assertTrue(all("|" not in value and ":" not in value for value in info.values()))
        self.game._validate_layout_keys(info)

    def test_height_layout_keeps_column_physical_height_after_refill(self):
        board = [[Cell(8, 0, 3), Cell(9, 0, 3)] for _ in range(6)]
        state = {
            "source_type": "rolls",
            "columns": [[8, 9, 10] for _ in range(6)],
            "top_indexes": [1] * 6,
            "row": 6,
            "col": 6,
        }
        next_board, _ = self.game._advance_board(board, {(0, 0)}, state)
        self.assertEqual([cell.Height for cell in next_board[0]], [1, 1, 1, 3])
        self.assertEqual(sum(cell.Height for cell in next_board[0]), 6)

    def test_silver_frame_uses_symbol_height_in_columns_two_to_five(self):
        self.game.SilverFrameChance = self.game.ChanceBase
        self.assertEqual(
            self.game._initial_cell(2, 1, height=4).FrameStage,
            1,
        )
        self.assertEqual(
            self.game._initial_cell(2, 1, height=1).FrameStage,
            0,
        )
        with self.assertRaises(ValueError):
            self.game._initial_cell(2, 1, height=5)
        self.assertEqual(
            self.game._initial_cell(2, 0, height=3).FrameStage,
            0,
        )
        self.assertEqual(self.game._initial_cell(self.game.WildId, 1, height=3).FrameStage, 0)
        self.assertEqual(self.game._initial_cell(self.game.ScatterId, 1, height=2).FrameStage, 0)

    def test_invalid_wild_columns_and_scatter_heights_are_rejected(self):
        for Col in (0, 5):
            with self.subTest(Col=Col):
                with self.assertRaises(ValueError):
                    self.game._initial_cell(self.game.WildId, Col, height=1)
        for Height in (3, 4):
            with self.subTest(Height=Height):
                with self.assertRaises(ValueError):
                    self.game._initial_cell(self.game.ScatterId, 1, height=Height)
        for Col in (1, 2, 3, 4):
            self.assertEqual(self.game._initial_cell(self.game.WildId, Col, height=4), Cell(1, 0, 4))
        for Height in (1, 2):
            self.assertEqual(
                self.game._initial_cell(self.game.ScatterId, 0, height=Height), Cell(0, 0, Height)
            )

    def test_initial_silver_frames_use_symbol_height_in_both_modes(self):
        self.game.SilverFrameChance = self.game.ChanceBase
        self.game.ReelHeightWeights = [[0, 0, 0, 0, 1] for _ in range(6)]
        Layouts = [(3, 3), (1, 2, 3), (1, 1, 2, 2), (1, 1, 1, 1, 2), (1,) * 6]

        def FakeSpin(**kwargs):
            Columns = [
                [2, 3, 0, 4 if Col in (0, 5) else 1, 4, 5]
                for Col in range(6)
            ]
            self.game.last_spin_state = {
                "source_type": "rolls",
                "columns": Columns,
                "top_indexes": [0] * 6,
                "row": 6,
                "col": 6,
            }
            return Columns

        for FreeMode in (False, True):
            for Layout in Layouts:
                with self.subTest(FreeMode=FreeMode, SymbolCount=len(Layout)):
                    with (
                        patch.object(self.game, "spin", side_effect=FakeSpin),
                        patch.object(
                            self.game, "_select_layout",
                            side_effect=lambda total_height, col, free_game, initial: (
                                Layout if initial else (total_height,)
                            ),
                        ),
                        patch.object(self.game, "_evaluate_paths", return_value=(0, set(), [])),
                    ):
                        Result = self.game.fg_spin() if FreeMode else self.game.ng_spin()
                    for Col, Column in enumerate(Result["InitialBoard"]):
                        self.assertEqual(sum(Item["Height"] for Item in Column), sum(Layout))
                        self.assertEqual(
                            len(Column), len(Layout) + int(len(Layout) > 2 and Layout[2] > 2)
                        )
                        for Item in Column:
                            ExpectedFrame = int(
                                Col in (1, 2, 3, 4)
                                and Item["Height"] in (2, 3, 4)
                                and Item["SymbolId"] in self.game.OrdinaryIds
                            )
                            self.assertEqual(Item["FrameStage"], ExpectedFrame)

    def test_initial_tall_scatter_splits_only_its_slot_in_both_modes(self):
        self.game.ReelHeightWeights = [[0, 0, 0, 0, 1] for _ in range(6)]

        def FakeSpin(**kwargs):
            Columns = [[0, 2, 3, 4, 5, 6] for _ in range(6)]
            self.game.last_spin_state = {
                "source_type": "rolls",
                "columns": Columns,
                "top_indexes": [0] * 6,
                "row": 6,
                "col": 6,
            }
            return Columns

        for FreeMode in (False, True):
            for ScatterHeight in (3, 4):
                with self.subTest(FreeMode=FreeMode, ScatterHeight=ScatterHeight):
                    def LayoutForHeight(total_height, col, free_game, initial):
                        return (ScatterHeight, 6 - ScatterHeight) if initial else (total_height,)

                    with (
                        patch.object(self.game, "spin", side_effect=FakeSpin),
                        patch.object(self.game, "_select_layout", side_effect=LayoutForHeight),
                        patch.object(self.game, "_evaluate_paths", return_value=(0, set(), [])),
                    ):
                        Result = self.game.fg_spin() if FreeMode else self.game.ng_spin()
                    for Col, Column in enumerate(Result["InitialBoard"]):
                        self.assertEqual(
                            [(Item["SymbolId"], Item["Height"]) for Item in Column],
                            [(3, ScatterHeight - 2), (0, 2), (2, 6 - ScatterHeight)],
                        )
                        self.assertEqual(sum(Item["Height"] for Item in Column), 6)
                        self.assertEqual(Result["ReelLayouts"][Col], [Item["Height"] for Item in Column])
                        self.assertEqual(Result["ReelCellCounts"][Col], len(Column))
                    self.assertEqual(Result["ScatterCount"], 6)
                    self.assertEqual(Result["ExtraFreeSpins"] if FreeMode else Result["FreeSpinsAwarded"],
                                     6 if FreeMode else 12)

    def test_refill_tall_scatter_keeps_pairing_height_and_new_scatter_count(self):
        for FreeMode in (False, True):
            self.game._CurrentFreeGame = FreeMode
            for ScatterHeight in (3, 4):
                with self.subTest(FreeMode=FreeMode, ScatterHeight=ScatterHeight):
                    Board = [[Cell(8, 0, 3), Cell(9, 0, 2), Cell(0)] for _ in range(6)]
                    State = {
                        "source_type": "rolls",
                        "columns": [[3, 0, 2, 8, 9, 10] for _ in range(6)],
                        "top_indexes": [3] * 6,
                        "row": 6,
                        "col": 6,
                    }

                    def LayoutForHeight(total_height, col, free_game, initial):
                        return ((ScatterHeight, 5 - ScatterHeight)
                                if total_height == 5 else (total_height,))

                    with patch.object(self.game, "_select_layout", side_effect=LayoutForHeight):
                        NextBoard, NewScatterCount = self.game._advance_board(
                            Board, {(Col, Row) for Col in range(6) for Row in (0, 1)}, State
                        )
                    for Column in NextBoard:
                        self.assertEqual(
                            [(Item.SymbolId, Item.Height) for Item in Column],
                            [(3, ScatterHeight - 2), (0, 2), (2, 5 - ScatterHeight), (0, 1)],
                        )
                        self.assertEqual(sum(Item.Height for Item in Column), 6)
                    self.assertEqual(State["top_indexes"], [0] * 6)
                    self.assertEqual(NewScatterCount, 6)
                    self.assertEqual(self.game._count_scatter(NextBoard), 12)

    def test_reel_sources_reject_outer_column_wild_in_both_modes(self):
        SourceDir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as TempDir:
            ProjectDir = Path(TempDir)
            for Directory in ("special", "reel_config", "free_reel_config"):
                shutil.copytree(SourceDir / Directory, ProjectDir / Directory)
            for Directory, Filename in (
                ("reel_config", "klsj_rand_ex_0.conf"),
                ("free_reel_config", "klsj_free_rand_ex_0.conf"),
            ):
                ConfigPath = ProjectDir / Directory / Filename
                OriginalText = ConfigPath.read_text(encoding="utf-8")
                for Field, Offset in (
                    ("NORMAL_ROLL_1", 0), ("SP_ROLL_6", 0),
                    ("FIX_RESULT_1", 0), ("ZERO_RESULT_1", 35),
                ):
                    with self.subTest(Directory=Directory, Field=Field):
                        Parser = ConfigParser()
                        Parser.optionxform = str
                        Parser.read_string(OriginalText)
                        Values = Parser["GENERAL_1"][Field].split(",")
                        Values[Offset] = "1"
                        Parser["GENERAL_1"][Field] = ",".join(Values)
                        with ConfigPath.open("w") as Output:
                            Parser.write(Output)
                        try:
                            Game = ThemeMath(project_dir=ProjectDir)
                            with self.assertRaisesRegex(ValueError, Field):
                                if Directory == "free_reel_config":
                                    Game.fg_spin()
                                else:
                                    Game.ng_spin()
                        finally:
                            ConfigPath.write_text(OriginalText, encoding="utf-8")

    def test_real_source_results_keep_special_symbols_and_physical_height_valid(self):
        self.game.ReelHeightWeights = [[0, 0, 0, 0, 1] for _ in range(6)]
        RefillCount = 0
        for FreeMode in (False, True):
            for SpinType in ("normal", "special", "fix", "zero"):
                with self.subTest(FreeMode=FreeMode, SpinType=SpinType):
                    with patch.object(self.game, "_choose_spin_type", return_value=SpinType):
                        Result = (
                            self.game.fg_spin(
                                FreeSpinNumber=12, FreeStartMultiplier=12, return_detail=True
                            )
                            if FreeMode else self.game.ng_spin(return_detail=True)
                        )
                    Boards = [Result["InitialBoard"], Result["FinalBoard"]]
                    for Round in Result["Rounds"]:
                        Boards.extend((Round["Board"], Round["NextBoard"]))
                        RefillCount += 1
                    for Board in Boards:
                        for Col, Column in enumerate(Board):
                            self.assertEqual(sum(Item["Height"] for Item in Column), 6)
                            for Item in Column:
                                if Item["SymbolId"] == self.game.WildId:
                                    self.assertIn(Col, (1, 2, 3, 4))
                                if Item["SymbolId"] == self.game.ScatterId:
                                    self.assertIn(Item["Height"], (1, 2))
                    self.assertEqual(
                        Result["ScatterCount"],
                        sum(Item["SymbolId"] == self.game.ScatterId
                            for Column in Result["InitialBoard"] for Item in Column)
                        + sum(Round["NewScatterCount"] for Round in Result["Rounds"]),
                    )
        self.assertGreater(RefillCount, 0)

    def test_refill_silver_frames_use_new_symbol_height_without_rerolling(self):
        self.game.SilverFrameChance = self.game.ChanceBase
        for FreeMode in (False, True):
            self.game._CurrentFreeGame = FreeMode
            for RefillLayout in ((1, 2, 3), (1, 4, 1)):
                with self.subTest(FreeMode=FreeMode, RefillLayout=RefillLayout):
                    Survivors = [Cell(8)]
                    Board = [[Cell(2, 0, sum(RefillLayout))] + Survivors for _ in range(6)]
                    State = {
                        "source_type": "rolls",
                        "columns": [[3, 4, 5] for _ in range(6)],
                        "top_indexes": [0] * 6,
                        "row": 6,
                        "col": 6,
                    }
                    Wins = {(Col, 0) for Col in range(6)}
                    with patch.object(
                        self.game,
                        "_select_layout",
                        return_value=RefillLayout,
                    ):
                        NextBoard, _ = self.game._advance_board(Board, Wins, State)
                    for Col, Column in enumerate(NextBoard):
                        ExpectedFrames = [
                            int(Col in (1, 2, 3, 4) and Height in (2, 3, 4))
                            for Height in RefillLayout
                        ]
                        self.assertEqual(
                            [Item.FrameStage for Item in Column[:-1]],
                            ExpectedFrames,
                        )
                        self.assertEqual(Column[-1:], Survivors)

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
        free = self.game.fg_spin(FreeSpinNumber=3, FreeStartMultiplier=3, return_detail=True)
        self.assertEqual(free["ScatterCount"], 4)
        self.assertEqual(free["ExtraFreeSpins"], 4)
        self.assertEqual(free["Rounds"][0]["Multiplier"], 3)

    def test_main_multiplier_caps_at_five_and_free_caps_only_each_spins_increment(self):
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

        def run_with_six_cascades(FreeStartMultiplier):
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
            if FreeStartMultiplier is None:
                return self.game.ng_spin(return_detail=True)
            return self.game.fg_spin(
                FreeSpinNumber=3, FreeStartMultiplier=FreeStartMultiplier, return_detail=True
            )

        main = run_with_six_cascades(None)
        self.assertEqual([round_["Multiplier"] for round_ in main["Rounds"]], [1, 2, 3, 4, 5, 5])
        self.assertEqual(main["TotalWin"], 20 * self.game.base_bet)
        self.assertTrue(all(
            round_["Win"] == sum(item["Win"] for item in round_["WinItems"])
            and round_["BaseWin"] == sum(item["BaseWin"] for item in round_["WinItems"])
            for round_ in main["Rounds"]
        ))

        free = run_with_six_cascades(3)
        self.assertEqual([round_["Multiplier"] for round_ in free["Rounds"]], [3, 4, 5, 6, 7, 7])
        self.assertEqual(free["TotalWin"], 32 * self.game.base_bet)
        self.assertEqual(free["CascadeCount"], 6)
        self.assertEqual(free["Rounds"][-1]["Win"], 7 * self.game.base_bet)

        HighStart = run_with_six_cascades(12)
        self.assertEqual(
            [Round["Multiplier"] for Round in HighStart["Rounds"]], [12, 13, 14, 15, 16, 16]
        )
        self.assertEqual(HighStart["TotalWin"], 86 * self.game.base_bet)
        AnotherHighStart = run_with_six_cascades(13)
        self.assertEqual(
            [Round["Multiplier"] for Round in AnotherHighStart["Rounds"]], [13, 14, 15, 16, 17, 17]
        )
        self.assertEqual(AnotherHighStart["TotalWin"], 92 * self.game.base_bet)

    def test_configured_free_increment_cap_zero_default_and_custom_keep_paying(self):
        SourceDir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as TempDir:
            ProjectDir = Path(TempDir)
            for Directory in ("special", "reel_config", "free_reel_config"):
                shutil.copytree(SourceDir / Directory, ProjectDir / Directory)
            for Cap, ExpectedMultipliers in (
                (0, [3, 3, 3, 3, 3, 3]),
                (4, [3, 4, 5, 6, 7, 7]),
                (2, [3, 4, 5, 5, 5, 5]),
            ):
                with self.subTest(Cap=Cap):
                    Server = self._server_config()
                    Server["Game Info"]["FreeSpinMultiplierIncrementCap"] = str(Cap)
                    with (ProjectDir / "special/klsj_game_server.conf").open("w") as Output:
                        Server.write(Output)
                    Game = ThemeMath(project_dir=ProjectDir)
                    self.assertEqual(Game.FreeSpinMultiplierIncrementCap, Cap)
                    WinningEvaluation = (
                        Game.base_bet, {(0, 0)}, [{"ItemId": 2, "Win": Game.base_bet}]
                    )
                    with (
                        patch.object(
                            Game, "_evaluate_paths",
                            side_effect=[WinningEvaluation] * 6 + [(0, set(), [])],
                        ),
                        patch.object(
                            Game, "_advance_board", side_effect=lambda Board, Wins, State: (Board, 0)
                        ),
                    ):
                        Result = Game.fg_spin(
                            FreeSpinNumber=3, FreeStartMultiplier=3, return_detail=True
                        )
                    self.assertEqual(
                        [Round["Multiplier"] for Round in Result["Rounds"]], ExpectedMultipliers
                    )
                    self.assertEqual(Result["TotalWin"], sum(ExpectedMultipliers) * Game.base_bet)
                    self.assertEqual(Result["CascadeCount"], 6)
                    self.assertTrue(all(
                        Round["Win"] == Expected * Game.base_bet
                        for Round, Expected in zip(Result["Rounds"], ExpectedMultipliers)
                    ))

    def test_free_start_carries_previous_end_plus_one_and_paid_spin_resets_it(self):
        def RunFree(FreeSpinNumber, CascadeCount, FreeStartMultiplier=None):
            WinningEvaluation = (
                self.game.base_bet, {(0, 0)}, [{"ItemId": 2, "Win": self.game.base_bet}]
            )
            Arguments = {"FreeSpinNumber": FreeSpinNumber, "return_detail": True}
            if FreeStartMultiplier is not None:
                Arguments["FreeStartMultiplier"] = FreeStartMultiplier
            with (
                patch.object(
                    self.game, "_evaluate_paths",
                    side_effect=[WinningEvaluation] * CascadeCount + [(0, set(), [])],
                ),
                patch.object(
                    self.game, "_advance_board", side_effect=lambda Board, Wins, State: (Board, 0)
                ),
            ):
                return self.game.fg_spin(**Arguments)

        Third = RunFree(3, 6, FreeStartMultiplier=3)
        self.assertEqual([Round["Multiplier"] for Round in Third["Rounds"]], [3, 4, 5, 6, 7, 7])
        self.assertEqual(Third["FreeSpinNumber"], 3)
        self.assertEqual((Third["FreeStartMultiplier"], Third["FreeEndMultiplier"]), (3, 7))
        self.assertEqual(self.game.NextFreeStartMultiplier, 8)

        Fourth = RunFree(4, 6)
        self.assertEqual([Round["Multiplier"] for Round in Fourth["Rounds"]], [8, 9, 10, 11, 12, 12])
        self.assertEqual(Fourth["FreeSpinNumber"], 4)
        self.assertEqual((Fourth["FreeStartMultiplier"], Fourth["FreeEndMultiplier"]), (8, 12))
        self.assertEqual(self.game.NextFreeStartMultiplier, 13)

        Fifth = RunFree(5, 0)
        self.assertEqual(Fifth["TotalWin"], 0)
        self.assertEqual((Fifth["FreeStartMultiplier"], Fifth["FreeEndMultiplier"]), (13, 13))
        self.assertEqual(self.game.NextFreeStartMultiplier, 14)

        with patch.object(self.game, "_evaluate_paths", return_value=(0, set(), [])):
            self.game.ng_spin()
        self.assertEqual(self.game.NextFreeStartMultiplier, 1)
        NextFreeRound = RunFree(1, 0)
        self.assertEqual(
            (NextFreeRound["FreeStartMultiplier"], NextFreeRound["FreeEndMultiplier"]), (1, 1)
        )
        self.assertEqual(self.game.NextFreeStartMultiplier, 2)

    def test_free_round_cap_requires_a_positive_integer_server_field(self):
        SourceDir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as TempDir:
            ProjectDir = Path(TempDir)
            for Directory in ("special", "reel_config", "free_reel_config"):
                shutil.copytree(SourceDir / Directory, ProjectDir / Directory)
            for Value in (None, "0", "-1", "2.5", "x"):
                with self.subTest(Value=Value):
                    Server = self._server_config()
                    if Value is None:
                        del Server["Game Info"]["Free_Max_Times"]
                    else:
                        Server["Game Info"]["Free_Max_Times"] = Value
                    with (ProjectDir / "special/klsj_game_server.conf").open("w") as Output:
                        Server.write(Output)
                    with self.assertRaisesRegex(ValueError, "Free_Max_Times"):
                        ThemeMath(project_dir=ProjectDir)

    def test_initial_scatter_generation_keeps_the_complete_award_within_fifty(self):
        self.assertEqual(self.game.FreeMaxTimes, 50)
        self.game.ReelHeightWeights = [[0, 0, 0, 0, 1] for _ in range(6)]

        with (
            patch.object(self.game, "spin", side_effect=self._scatter_candidate_spin),
            patch.object(self.game, "_select_layout",
                         side_effect=lambda total_height, col, free_game, initial: (1,) * total_height),
        ):
            Result = self.game.ng_spin(return_detail=True)
        self.assertEqual(Result["ScatterCount"], 25)
        self.assertEqual(Result["FreeSpinsAwarded"], 50)
        self.assertEqual(Result["FreeSpinsAwarded"], 8 + 2 * (Result["ScatterCount"] - 4))
        self.assertEqual(Result["TotalWin"], 0)

    def test_main_scatter_budget_uses_configured_base_and_complete_extra_awards(self):
        self.game.ReelHeightWeights = [[0, 0, 0, 0, 1] for _ in range(6)]
        for Maximum, Base, Extra, Trigger, ExpectedScatters, ExpectedAward in (
            (50, 46, 3, 4, 5, 49),
            (37, 10, 3, 5, 14, 37),
        ):
            with self.subTest(Maximum=Maximum, Base=Base, Extra=Extra, Trigger=Trigger):
                self.game.FreeMaxTimes = Maximum
                self.game.BaseFreeSpins = Base
                self.game.MainExtraFreeSpinsPerScatter = Extra
                self.game.FreeTriggerScatterCount = Trigger
                with (
                    patch.object(self.game, "spin", side_effect=self._scatter_candidate_spin),
                    patch.object(self.game, "_select_layout",
                                 side_effect=lambda total_height, col, free_game, initial: (1,) * total_height),
                    patch.object(self.game, "_evaluate_paths", return_value=(0, set(), [])),
                ):
                    Result = self.game.ng_spin()
                self.assertEqual(Result["ScatterCount"], ExpectedScatters)
                self.assertEqual(Result["FreeSpinsAwarded"], ExpectedAward)
                self.assertEqual(Result["FreeSpinsAwarded"], Base + Extra * (ExpectedScatters - Trigger))

    def test_base_free_award_configuration_cannot_exceed_the_round_budget(self):
        SourceDir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as TempDir:
            ProjectDir = Path(TempDir)
            for Directory in ("special", "reel_config", "free_reel_config"):
                shutil.copytree(SourceDir / Directory, ProjectDir / Directory)
            Server = self._server_config()
            Server["Game Info"]["BaseFreeSpins"] = "51"
            with (ProjectDir / "special/klsj_game_server.conf").open("w") as Output:
                Server.write(Output)
            with self.assertRaisesRegex(ValueError, "BaseFreeSpins.*Free_Max_Times"):
                ThemeMath(project_dir=ProjectDir)

    def test_extra_free_spins_reserve_the_existing_queue_near_the_cap(self):
        self.game.ReelHeightWeights = [[0, 0, 0, 0, 1] for _ in range(6)]
        for Number, Remaining, ExpectedExtra in (
            (48, 0, 2), (48, 1, 1), (49, 0, 1), (49, 1, 0), (50, 0, 0),
        ):
            with self.subTest(FreeSpinNumber=Number, FreeSpinsRemaining=Remaining):
                with (
                    patch.object(self.game, "spin", side_effect=self._scatter_candidate_spin),
                    patch.object(self.game, "_select_layout",
                                 side_effect=lambda total_height, col, free_game, initial: (1,) * total_height),
                    patch.object(self.game, "_evaluate_paths", return_value=(0, set(), [])),
                ):
                    Result = self.game.fg_spin(
                        FreeSpinNumber=Number, FreeStartMultiplier=73,
                        FreeSpinsRemaining=Remaining, return_detail=True,
                    )
                self.assertEqual(Result["ScatterCount"], ExpectedExtra)
                self.assertEqual(Result["ExtraFreeSpins"], ExpectedExtra)
                self.assertEqual(Result["ExtraFreeSpins"], Result["ScatterCount"])
                self.assertEqual(Result["FreeEndMultiplier"], 73)
                self.assertLessEqual(Number + Remaining + Result["ExtraFreeSpins"], 50)

    def test_initial_and_all_refills_share_scatter_budget_without_recounting_survivors(self):
        self.game.ReelHeightWeights = [[1, 0, 0, 0, 0] for _ in range(6)]

        def FakeSpin(**kwargs):
            self._scatter_candidate_spin(**kwargs)
            Board = [[8] * 6 for _ in range(6)]
            Board[1][0] = 0
            return Board

        Evaluations = [
            (self.game.base_bet, {(1, 1)}, [{"ItemId": 8, "Win": self.game.base_bet}]),
            (self.game.base_bet, {(2, 0)}, [{"ItemId": 8, "Win": self.game.base_bet}]),
            (0, set(), []),
        ]
        with (
            patch.object(self.game, "spin", side_effect=FakeSpin),
            patch.object(self.game, "_select_layout",
                         side_effect=lambda total_height, col, free_game, initial: (1,) * total_height),
            patch.object(self.game, "_evaluate_paths", side_effect=Evaluations),
        ):
            Result = self.game.fg_spin(
                FreeSpinNumber=48, FreeStartMultiplier=5, FreeSpinsRemaining=0, return_detail=True,
            )
        self.assertEqual(sum(Item["SymbolId"] == 0 for Column in Result["InitialBoard"]
                             for Item in Column), 1)
        self.assertEqual([Round["NewScatterCount"] for Round in Result["Rounds"]], [1, 0])
        self.assertEqual(Result["ScatterCount"], 2)
        self.assertEqual(Result["ExtraFreeSpins"], 2)
        self.assertEqual(sum(Item["SymbolId"] == 0 for Column in Result["FinalBoard"]
                             for Item in Column), 2)
        self.assertEqual(Result["TotalWin"], 11 * self.game.base_bet)

    def test_scatter_remainder_slots_share_the_original_symbols_budget(self):
        Generation = {"ScatterBudget": 2, "OrdinaryPools": [[8] for _ in range(6)]}
        with patch.object(self.game, "_select_layout", return_value=(1,)):
            Cells = self.game._build_column(
                [0, 0, 0, 0], (3, 3), 1, True, ScatterGeneration=Generation,
            )
        self.assertEqual([(Item.SymbolId, Item.Height) for Item in Cells],
                         [(8, 1), (0, 2), (8, 1), (0, 2)])
        self.assertEqual(Generation["ScatterBudget"], 0)
        self.assertEqual(sum(Item.Height for Item in Cells), 6)

    def test_overflow_tall_scatter_becomes_framed_ordinary_without_extra_reel_draws(self):
        self.game.SilverFrameChance = self.game.ChanceBase
        for Height in (3, 4):
            with self.subTest(Height=Height):
                Generation = {"ScatterBudget": 0, "OrdinaryPools": [[8, 9, 9] for _ in range(6)]}
                State = {
                    "source_type": "rolls", "columns": [[0, 8, 9, 9] for _ in range(6)],
                    "top_indexes": [1] * 6, "row": 6, "col": 6,
                    "ScatterGeneration": Generation,
                }
                with (
                    patch("theme_math.random.choice", return_value=9) as Choice,
                    patch.object(self.game, "_select_layout") as Layout,
                    patch.object(self.game, "take_symbols_above",
                                 wraps=self.game.take_symbols_above) as Take,
                ):
                    Cells = self.game._build_column([0], (Height,), 1, True, State)
                self.assertEqual(Cells, [Cell(9, 1, Height)])
                Choice.assert_called_once_with([8, 9, 9])
                Layout.assert_not_called()
                Take.assert_called_once_with(State, 1, 1)
                self.assertEqual(State["top_indexes"], [1, 0, 1, 1, 1, 1])
                self.assertEqual(Generation["ScatterBudget"], 0)

    def test_overflow_uses_each_actual_source_columns_ordinary_frequency(self):
        Pools = [[8] + [9] * (Col + 1) for Col in range(6)]
        self.game.ReelHeightWeights = [[0, 0, 0, 0, 1] for _ in range(6)]

        def FakeSpin(**kwargs):
            self._scatter_candidate_spin(**kwargs)
            self.game.last_spin_state["columns"] = [[0] * 12 + Pool for Pool in Pools]
            return [[0] * 6 for _ in range(6)]

        with (
            patch.object(self.game, "spin", side_effect=FakeSpin),
            patch.object(self.game, "_select_layout", return_value=(3, 3)),
            patch.object(self.game, "_evaluate_paths", return_value=(0, set(), [])),
            patch("theme_math.random.choice", return_value=9) as Choice,
            patch.object(self.game, "take_symbols_above", wraps=self.game.take_symbols_above) as Take,
        ):
            Result = self.game.fg_spin(FreeSpinNumber=50, FreeSpinsRemaining=0)
        self.assertEqual([Call.args[0] for Call in Choice.call_args_list],
                         [Pool for Pool in Pools for _ in range(2)])
        Take.assert_not_called()
        self.assertEqual(self.game.last_spin_state["top_indexes"], [6] * 6)
        self.assertEqual(Result["ScatterCount"], 0)
        self.assertTrue(all(Item["SymbolId"] == 9 and Item["Height"] == 3
                            for Column in Result["InitialBoard"] for Item in Column))

    def test_free_scatter_award_must_be_one_and_main_extra_award_must_be_positive(self):
        SourceDir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as TempDir:
            ProjectDir = Path(TempDir)
            for Directory in ("special", "reel_config", "free_reel_config"):
                shutil.copytree(SourceDir / Directory, ProjectDir / Directory)
            for Field, Value in (
                ("FreeExtraSpinsPerScatter", "0"),
                ("FreeExtraSpinsPerScatter", "2"),
                ("MainExtraFreeSpinsPerScatter", "0"),
                ("MainExtraFreeSpinsPerScatter", "-1"),
            ):
                with self.subTest(Field=Field, Value=Value):
                    Server = self._server_config()
                    Server["Game Info"][Field] = Value
                    with (ProjectDir / "special/klsj_game_server.conf").open("w") as Output:
                        Server.write(Output)
                    with self.assertRaisesRegex(ValueError, Field):
                        ThemeMath(project_dir=ProjectDir)

    def test_overflow_scatter_requires_an_ordinary_symbol_in_the_same_source_column(self):
        Generation = {"ScatterBudget": 0, "OrdinaryPools": [[8] for _ in range(6)]}
        Generation["OrdinaryPools"][1] = []
        State = {
            "source_type": "rolls", "columns": [[0] for _ in range(6)],
            "top_indexes": [0] * 6, "row": 6, "col": 6,
            "ScatterGeneration": Generation,
        }
        with self.assertRaisesRegex(ValueError, "column 2.*no ordinary"):
            self.game._build_column([0], (3,), 1, True, State)
        self.assertEqual(State["top_indexes"], [0] * 6)

    def test_fiftieth_free_spin_completes_all_wins_and_does_not_add_more_spins(self):
        WinningEvaluation = (
            self.game.base_bet, {(0, 0)}, [{"ItemId": 2, "Win": self.game.base_bet}]
        )
        with (
            patch.object(self.game, "spin", side_effect=self._scatter_candidate_spin),
            patch.object(self.game, "_evaluate_paths",
                         side_effect=[WinningEvaluation] * 6 + [(0, set(), [])]),
        ):
            Result = self.game.fg_spin(
                FreeSpinNumber=50, FreeStartMultiplier=20, FreeSpinsRemaining=0, return_detail=True,
            )
        self.assertEqual([Round["Multiplier"] for Round in Result["Rounds"]], [20, 21, 22, 23, 24, 24])
        self.assertEqual(Result["CascadeCount"], 6)
        self.assertEqual(Result["TotalWin"], 134 * self.game.base_bet)
        self.assertEqual(Result["ScatterCount"], 0)
        self.assertEqual(Result["ExtraFreeSpins"], 0)
        self.assertEqual([Round["NewScatterCount"] for Round in Result["Rounds"]], [0] * 6)
        self.assertEqual(Result["FreeEndMultiplier"], 24)
        self.assertEqual(self.game.NextFreeStartMultiplier, 25)
        self.assertEqual(self.game.NextFreeSpinNumber, 51)

    def test_invalid_free_progress_is_rejected_before_board_generation_or_state_changes(self):
        self.game.NextFreeStartMultiplier = 99
        for Number, Remaining in ((51, 0), (0, 0), (49, 2), (50, 1), (1, -1)):
            with self.subTest(FreeSpinNumber=Number, FreeSpinsRemaining=Remaining):
                with (
                    patch.object(self.game, "spin") as Spin,
                    patch.object(self.game, "_evaluate_paths") as Evaluate,
                ):
                    with self.assertRaises(ValueError):
                        self.game.fg_spin(FreeSpinNumber=Number, FreeSpinsRemaining=Remaining)
                    Spin.assert_not_called()
                    Evaluate.assert_not_called()
                self.assertEqual(self.game.NextFreeStartMultiplier, 99)
                self.assertEqual(self.game.NextFreeSpinNumber, 1)

    def test_default_free_progress_stops_at_fifty_and_paid_spin_starts_a_new_round(self):
        with (
            patch.object(self.game, "_choose_spin_type", return_value="zero"),
            patch.object(self.game, "_evaluate_paths", return_value=(0, set(), [])),
        ):
            for Number in range(1, 51):
                Result = self.game.fg_spin()
                self.assertEqual(Result["FreeSpinNumber"], Number)
                self.assertEqual(Result["FreeStartMultiplier"], Number)
                self.assertEqual(Result["FreeEndMultiplier"], Number)
                self.assertEqual(self.game.NextFreeSpinNumber, Number + 1)
            with patch.object(self.game, "spin") as Spin:
                with self.assertRaises(ValueError):
                    self.game.fg_spin()
                Spin.assert_not_called()
            self.assertEqual(self.game.NextFreeSpinNumber, 51)
            self.assertEqual(self.game.NextFreeStartMultiplier, 51)
            self.game.ng_spin()
            self.assertEqual(self.game.NextFreeSpinNumber, 1)
            self.assertEqual(self.game.NextFreeStartMultiplier, 1)
            NextRound = self.game.fg_spin()
            self.assertEqual(NextRound["FreeSpinNumber"], 1)
            self.assertEqual(NextRound["FreeStartMultiplier"], 1)

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
        FreeStarts = []
        FreeRemaining = []

        class FakeGame:
            FreeMaxTimes = 50

            def __init__(self, base_bet):
                pass

            def ng_spin(self, **kwargs):
                return {"TotalWin": 0, "FreeSpinsAwarded": 2}

            def fg_spin(self, FreeSpinNumber, FreeStartMultiplier, FreeSpinsRemaining, **kwargs):
                free_numbers.append(FreeSpinNumber)
                FreeStarts.append(FreeStartMultiplier)
                FreeRemaining.append(FreeSpinsRemaining)
                return {
                    "TotalWin": 0,
                    "ExtraFreeSpins": 1 if FreeSpinNumber == 1 else 0,
                    "FreeEndMultiplier": FreeStartMultiplier,
                }

        with patch.object(simulation, "ThemeMath", FakeGame):
            result = simulation.simulate(1)
        self.assertEqual(free_numbers, [1, 2, 3])
        self.assertEqual(FreeStarts, [1, 2, 3])
        self.assertEqual(FreeRemaining, [1, 1, 0])
        self.assertEqual(result["FreeSpins"], 3)

    def test_simulation_extra_spins_keep_multiplier_and_new_paid_round_restarts_at_one(self):
        FreeCalls = []

        class FakeGame:
            FreeMaxTimes = 50

            def __init__(self, base_bet):
                self.BaseBet = base_bet
                self.PaidSpinNumber = 0

            def ng_spin(self, **kwargs):
                self.PaidSpinNumber += 1
                return {"TotalWin": 0, "FreeSpinsAwarded": 2}

            def fg_spin(self, FreeSpinNumber, FreeStartMultiplier, FreeSpinsRemaining, **kwargs):
                FreeCalls.append((self.PaidSpinNumber, FreeSpinNumber,
                                  FreeStartMultiplier, FreeSpinsRemaining))
                Wins = FreeSpinNumber == 1
                return {
                    "TotalWin": self.BaseBet if Wins else 0,
                    "ExtraFreeSpins": 1 if Wins else 0,
                    "FreeEndMultiplier": FreeStartMultiplier + (4 if Wins else 0),
                }

        with patch.object(simulation, "ThemeMath", FakeGame):
            Result = simulation.simulate(2)
        self.assertEqual(FreeCalls, [(1, 1, 1, 1), (1, 2, 6, 1), (1, 3, 7, 0),
                                    (2, 1, 1, 1), (2, 2, 6, 1), (2, 3, 7, 0)])
        self.assertEqual(Result["FreeSpins"], 6)

    def test_simulation_settles_every_awarded_spin_and_restarts_the_next_paid_round(self):
        FreeCalls = []
        BaseBet = 10000

        class FakeGame:
            FreeMaxTimes = 50

            def __init__(self, base_bet):
                self.BaseBet = base_bet
                self.PaidSpinNumber = 0

            def ng_spin(self, **kwargs):
                self.PaidSpinNumber += 1
                return {"TotalWin": 0, "FreeSpinsAwarded": 2 if self.PaidSpinNumber == 1 else 50}

            def fg_spin(self, FreeSpinNumber, FreeStartMultiplier, FreeSpinsRemaining, **kwargs):
                if FreeSpinNumber > self.FreeMaxTimes:
                    raise AssertionError("simulation exceeded the free round cap")
                FreeCalls.append((self.PaidSpinNumber, FreeSpinNumber,
                                  FreeStartMultiplier, FreeSpinsRemaining))
                return {
                    "TotalWin": self.BaseBet * (10 if FreeSpinNumber == 50 else 1),
                    "ExtraFreeSpins": self.FreeMaxTimes - FreeSpinNumber - FreeSpinsRemaining,
                    "FreeEndMultiplier": FreeStartMultiplier + 4,
                }

        with patch.object(simulation, "ThemeMath", FakeGame):
            Result = simulation.simulate(2, base_bet=BaseBet)
        for PaidSpinNumber in (1, 2):
            Calls = [Call for Call in FreeCalls if Call[0] == PaidSpinNumber]
            self.assertEqual([Call[1] for Call in Calls], list(range(1, 51)))
            self.assertEqual([Call[2] for Call in Calls], [1 + 5 * Index for Index in range(50)])
            self.assertEqual(
                [Call[3] for Call in Calls],
                ([1] + list(range(48, -1, -1))) if PaidSpinNumber == 1 else list(range(49, -1, -1)),
            )
        self.assertEqual(Result["FreeSpins"], 100)
        self.assertEqual(Result["FreeTriggers"], 2)
        self.assertEqual(Result["AverageFreeSpinsPerTrigger"], 50)
        self.assertEqual(Result["FreeWin"], 118 * BaseBet)
        self.assertEqual(Result["TotalWin"], 118 * BaseBet)

    def test_simulation_reports_invalid_awards_instead_of_silently_cutting_them(self):
        for InitialAward, ExtraAward, Error in (
            (51, 0, "initial free award"),
            (1, 50, "extra free award"),
        ):
            with self.subTest(InitialAward=InitialAward, ExtraAward=ExtraAward):
                class FakeGame:
                    FreeMaxTimes = 50

                    def __init__(self, base_bet):
                        pass

                    def ng_spin(self, **kwargs):
                        return {"TotalWin": 0, "FreeSpinsAwarded": InitialAward}

                    def fg_spin(self, FreeSpinNumber, FreeStartMultiplier, FreeSpinsRemaining, **kwargs):
                        return {"TotalWin": 0, "ExtraFreeSpins": ExtraAward,
                                "FreeEndMultiplier": FreeStartMultiplier}

                with patch.object(simulation, "ThemeMath", FakeGame):
                    with self.assertRaisesRegex(RuntimeError, Error):
                        simulation.simulate(1)

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
