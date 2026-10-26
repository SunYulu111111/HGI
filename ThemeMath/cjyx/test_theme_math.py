"""超级英雄的判奖、免费会话和配置边界验证。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import random
import re
import tempfile
import unittest
from unittest.mock import patch

try:
    from .theme_math import ThemeMath
    from .build_demo_reels import build_reels
except ImportError:
    from theme_math import ThemeMath
    from build_demo_reels import build_reels


ProjectDir = Path(__file__).resolve().parent
ConfigPath = Path("special/cjyx_game_config.conf")
ServerPath = Path("special/cjyx_game_server.conf")

from slots_math import LinesGame


class ThemeMathTests(unittest.TestCase):
    def setUp(self):
        self.Model = ThemeMath(Seed=373)

    def assert_template_config_schema(self, FileName, RootDir=ProjectDir):
        Relative = FileName.relative_to(RootDir)
        if Relative in (ServerPath, Path("special/cjyx_bonus.conf")):
            return
        TemplateRelative = str(Relative).replace("cjyx", "xxx")
        TemplateRelative = TemplateRelative.replace("xxx_super_free_rand_ex_", "xxx_free_rand_ex_")
        TemplateRelative = re.sub(r"_ex_\d+\.conf$", "_ex_0.conf", TemplateRelative)
        TemplateFile = ProjectDir.parent / "model_linesgame" / TemplateRelative
        self.assertTrue(TemplateFile.is_file(), f"配置没有对应 model：{Relative}")
        Current = self.Model._read_config_file(FileName)
        Template = self.Model._read_config_file(TemplateFile)

        def Family(Name):
            return re.sub(r"_\d+$", "_N", Name)

        AllowedSections = {}
        for Section in Template.sections():
            AllowedSections.setdefault(Family(Section), set()).update(Family(Key) for Key in Template[Section])
        self.assertLessEqual(set(map(Family, Current.defaults())), set(map(Family, Template.defaults())))
        for Section in Current.sections():
            SectionFamily = Family(Section)
            self.assertIn(SectionFamily, AllowedSections, f"{Relative} 含 model 外配置段 [{Section}]")
            Extra = {Key for Key in Current[Section] if Family(Key) not in AllowedSections[SectionFamily]}
            self.assertFalse(Extra, f"{Relative} [{Section}] 含 model 外字段：{sorted(Extra)}")

    @staticmethod
    def blank_board():
        return [[Symbol] * 5 for Symbol in (8, 9, 10, 11, 12)]

    @classmethod
    def scatter_board(cls, Count):
        Board = cls.blank_board()
        for Column in range(Count):
            Board[Column][0] = 0
        return Board

    def force_multiplier(self, Mode, Multiplier):
        Values = self.Model.Config["GameInfo"]["FusionMultipliers"]
        self.Model.Config["GameInfo"][Mode + "FusionWeights"] = [
            int(Value == Multiplier) for Value in Values
        ]

    @staticmethod
    def fusion_board():
        Board = [[3] * 5, [4] * 5, [3] * 5, [6] * 5, [7] * 5]
        Board[1][0], Board[1][4] = 1, 2
        return Board

    @staticmethod
    def set_free_counts(Model, Played, Remaining):
        Model.FreeSpinsPlayed = Played
        Model.FreeSpinsRemaining = Remaining
        Model.FreeSpinsAwarded = Played + Remaining

    def test_nineteen_lines_match_design_positions(self):
        Expected = [
            [0, 5, 10, 15, 20], [1, 6, 11, 16, 21],
            [2, 7, 12, 17, 22], [3, 8, 13, 18, 23],
            [4, 9, 14, 19, 24], [0, 6, 10, 16, 20],
            [1, 5, 11, 15, 21], [1, 7, 11, 17, 21],
            [2, 6, 12, 16, 22], [2, 8, 12, 18, 22],
            [3, 7, 13, 17, 23], [3, 9, 13, 19, 23],
            [4, 8, 14, 18, 24], [0, 6, 12, 18, 24],
            [1, 7, 13, 17, 21], [2, 6, 10, 16, 22],
            [2, 8, 14, 18, 22], [3, 7, 11, 17, 23],
            [4, 8, 12, 16, 20],
        ]
        self.assertEqual(self.Model.Config["GameInfo"]["PayLines"], Expected)

    def test_full_paytable_uses_total_bet_for_three_four_and_five(self):
        Pays = {
            3: (20, 100, 200), 4: (15, 75, 175), 5: (15, 75, 175),
            6: (10, 50, 150), 7: (10, 50, 150), 8: (4, 20, 100),
            9: (3, 15, 75), 10: (3, 15, 75),
            11: (2, 10, 50), 12: (2, 10, 50),
        }
        for Symbol, Values in Pays.items():
            for Count, Pay in zip((3, 4, 5), Values):
                with self.subTest(Symbol=Symbol, Count=Count):
                    Other = 4 if Symbol == 3 else 3
                    Board = [[Symbol if Column < Count else Other] * 5 for Column in range(5)]
                    Result = self.Model.evaluate(Board)
                    self.assertEqual(len(Result["WinItems"]), 19)
                    self.assertEqual(Result["TotalWin"], 19 * 100000 * Pay // 10)
                    self.assertTrue(all(Item["Count"] == Count for Item in Result["WinItems"]))

    def test_two_symbols_do_not_pay_and_scatter_has_no_amount_pay(self):
        Board = [[3] * 5, [3] * 5, [4] * 5, [5] * 5, [6] * 5]
        self.assertEqual(self.Model.evaluate(Board)["TotalWin"], 0)
        self.assertEqual(self.Model.evaluate(self.scatter_board(3))["TotalWin"], 0)

    def test_both_wild_types_form_one_pure_wild_award_per_line(self):
        Board = [[2, 2, 2, 2, 1] for _ in range(5)]
        Result = self.Model.evaluate(Board)
        self.assertEqual(len(Result["WinItems"]), 19)
        self.assertEqual(Result["TotalWin"], 19 * 25 * self.Model.BaseBet)
        self.assertTrue(all(Item["Count"] == 5 for Item in Result["WinItems"]))
        self.assertTrue(all(Item["SymbolId"] in (1, 2) for Item in Result["WinItems"]))
        self.assertTrue(all(not Feature["Extended"] for Feature in Result["WildFeatures"]))

    def test_joint_preview_extends_wilds_that_need_each_other_to_win(self):
        Board = [[3] * 5, [4] * 5, [5] * 5, [6] * 5, [7] * 5]
        Board[1][0] = Board[2][0] = 1
        Result = self.Model.evaluate(Board)
        self.assertGreater(Result["TotalWin"], 0)
        self.assertEqual({Feature["Column"] for Feature in Result["WildFeatures"] if Feature["Extended"]}, {1, 2})
        self.assertEqual(Result["FinalBoard"][5:15], [1] * 10)

    def test_unwinning_special_wild_stays_single_and_does_not_fuse(self):
        Board = self.blank_board()
        Board[4][0], Board[4][4] = 1, 2
        Result = self.Model.evaluate(Board)
        self.assertEqual(Result["TotalWin"], 0)
        self.assertEqual(Result["FinalBoard"], Result["Board"])
        self.assertFalse(Result["WildFeatures"][0]["Extended"])
        self.assertEqual(Result["WildFeatures"][0]["Multiplier"], 0)

    def test_ordinary_wild_above_special_is_not_a_fusion(self):
        Board = [[3] * 5, [4] * 5, [3] * 5, [6] * 5, [7] * 5]
        Board[1][0], Board[1][1] = 2, 1
        Result = self.Model.evaluate(Board)
        self.assertTrue(Result["WildFeatures"][0]["Extended"])
        self.assertEqual(Result["WildFeatures"][0]["Multiplier"], 0)
        self.assertTrue(all(Item["Multiplier"] == 1 for Item in Result["WinItems"]))

    def test_modes_read_separate_fusion_weights(self):
        for Mode, Multiplier in (("Main", 3), ("Free", 5), ("SuperFree", 7)):
            self.force_multiplier(Mode, Multiplier)
        for Mode, Multiplier in (("Main", 3), ("Free", 5), ("SuperFree", 7)):
            with self.subTest(Mode=Mode):
                Result = self.Model.evaluate(self.fusion_board(), Mode=Mode)
                self.assertEqual(Result["WildFeatures"][0]["Multiplier"], Multiplier)
                self.assertTrue(all(Item["Multiplier"] == Multiplier for Item in Result["WinItems"]))

    def test_line_multiplier_adds_features_without_counting_covered_cells(self):
        self.force_multiplier("Main", 3)
        Board = [[3] * 5 for _ in range(5)]
        for Column in (3, 4):
            Board[Column] = [1, 4, 5, 6, 2]
        Result = self.Model.evaluate(Board)
        self.assertEqual(len(Result["WinItems"]), 19)
        self.assertTrue(all(Item["Multiplier"] == 6 for Item in Result["WinItems"]))
        self.assertEqual(Result["TotalWin"], 19 * 20 * 6 * self.Model.BaseBet)

    def test_multiplier_outside_winning_prefix_does_not_apply(self):
        self.force_multiplier("Main", 5)
        Board = [[3] * 5, [3] * 5, [3] * 5, [6] * 5, [1, 4, 5, 6, 2]]
        Board[3][0] = 3
        Result = self.Model.evaluate(Board)
        Top = next(Item for Item in Result["WinItems"] if Item["LineId"] == 1)
        Second = next(Item for Item in Result["WinItems"] if Item["LineId"] == 2)
        self.assertEqual((Top["Count"], Top["Multiplier"]), (5, 5))
        self.assertEqual((Second["Count"], Second["Multiplier"]), (3, 1))

    def test_ultimate_requires_pure_wild_and_multiplier_strictly_above_hundred(self):
        Board = [[1, 3, 4, 5, 2] for _ in range(5)]
        self.force_multiplier("Main", 20)
        ExactlyHundred = self.Model.evaluate(Board)
        self.assertFalse(ExactlyHundred["UltimateHit"])
        self.assertTrue(all(Item["Multiplier"] == 100 for Item in ExactlyHundred["WinItems"]))
        self.force_multiplier("Main", 25)
        AboveHundred = self.Model.evaluate(Board)
        self.assertTrue(AboveHundred["UltimateHit"])
        Ordinary = self.fusion_board()
        self.force_multiplier("Main", 200)
        self.assertFalse(self.Model.evaluate(Ordinary)["UltimateHit"])

    def test_scatter_limit_replaces_exact_excess_with_ordinary_symbols(self):
        for Mode, Limit in (("Main", 4), ("Free", 4), ("SuperFree", 3)):
            with self.subTest(Mode=Mode):
                Result = self.Model.evaluate(self.scatter_board(5), Mode=Mode)
                self.assertEqual(Result["ScatterCount"], Limit)
                Replacements = Result["Replacements"]
                self.assertEqual(len(Replacements), 5 - Limit)
                self.assertEqual(len({Entry["Position"] for Entry in Replacements}), 5 - Limit)
                self.assertTrue(all(Entry["OriginalSymbolId"] == 0 and 3 <= Entry["SymbolId"] <= 12 for Entry in Replacements))

    def test_main_three_and_four_scatters_start_distinct_modes(self):
        for Count, Mode in ((3, "Free"), (4, "SuperFree")):
            with self.subTest(Count=Count):
                Model = ThemeMath(Seed=373)
                Result = Model.ng_spin(Board=self.scatter_board(Count))
                self.assertEqual(Result["NextMode"], Mode)
                self.assertEqual(Result["AwardedFreeSpins"], 10)
                self.assertEqual(Model.FreeSpinsRemaining, 10)
                self.assertEqual(Model.ActivatedColumns, set())

    def test_last_free_spin_retriggers_before_session_finishes(self):
        for Mode in ("Free", "SuperFree"):
            with self.subTest(Mode=Mode):
                Model = ThemeMath(Seed=373)
                Model.start_free(Mode=Mode, FreeSpins=1)
                Result = Model.fg_spin(Board=self.scatter_board(3))
                self.assertEqual(Result["AwardedFreeSpins"], 4)
                self.assertEqual(Model.FreeSpinsRemaining, 4)
                self.assertEqual(Model.FreeSpinsAwarded, 5)
                self.assertEqual(Model.Mode, Mode)

    def test_upgrade_fills_to_ten_or_preserves_existing_balance(self):
        for Before, After, Awarded in ((1, 10, 10), (8, 10, 3), (11, 10, 0), (13, 12, 0)):
            with self.subTest(Before=Before):
                Model = ThemeMath(Seed=373)
                Model.start_free(FreeSpins=Before)
                Result = Model.fg_spin(Board=self.scatter_board(4))
                self.assertTrue(Result["Upgraded"])
                self.assertEqual((Result["Mode"], Result["NextMode"]), ("Free", "SuperFree"))
                self.assertEqual(Model.FreeSpinsRemaining, After)
                self.assertEqual(Result["AwardedFreeSpins"], Awarded)
                self.assertEqual(Model.ActivatedColumns, set())

    def test_retrigger_at_ninety_nine_is_suppressed_without_partial_grant(self):
        for Played, ExpectedScatters, Awarded in ((93, 3, 4), (94, 2, 0)):
            with self.subTest(Played=Played):
                Model = ThemeMath(Seed=373)
                Model.start_free()
                self.set_free_counts(Model, Played, 1)
                Result = Model.fg_spin(Board=self.scatter_board(3))
                self.assertEqual(Result["ScatterCount"], ExpectedScatters)
                self.assertEqual(Result["AwardedFreeSpins"], Awarded)
                self.assertEqual(Model.FreeSpinsAwarded, Played + 1 + Awarded)

    def test_upgrade_at_ninety_nine_replaces_two_scatters_instead_of_retrigger(self):
        self.Model.start_free()
        self.set_free_counts(self.Model, 88, 1)
        Result = self.Model.fg_spin(Board=self.scatter_board(4))
        self.assertFalse(Result["Upgraded"])
        self.assertEqual(Result["ScatterCount"], 2)
        self.assertEqual(Result["AwardedFreeSpins"], 0)
        self.assertEqual(len(Result["Replacements"]), 2)
        self.assertEqual(self.Model.Mode, "Main")

    def test_activated_column_preserves_natural_special_wild(self):
        self.Model.ActivatedColumns = {2}
        Board = self.blank_board()
        Board[2][3] = 1
        Result = self.Model.evaluate(Board, Mode="SuperFree")
        self.assertEqual(Result["Board"][13], 1)
        self.assertEqual(Result["Board"].count(1), 1)
        self.assertEqual(Result["Replacements"], [])

    def test_fill_uses_only_positions_below_scatter_and_their_weights(self):
        self.Model.ActivatedColumns = {0}
        Weights = self.Model.Config["GameInfo"]["SuperFreeWildFillWeights"]
        Weights[:5] = [100000, 100000, 100000, 0, 1]
        Board = self.blank_board()
        Board[0][2] = 0
        Result = self.Model.evaluate(Board, Mode="SuperFree")
        self.assertEqual(Result["Board"][2], 0)
        self.assertEqual(Result["Board"][4], 1)
        self.assertEqual(Result["Replacements"][0]["Position"], 4)

    def test_bottom_scatter_is_replaced_without_weight_draw(self):
        self.Model.ActivatedColumns = {0}
        Board = self.blank_board()
        Board[0][4] = 0
        with patch.object(self.Model.Rng, "randrange", side_effect=AssertionError("本分支不应抽取位置")):
            Result = self.Model.evaluate(Board, Mode="SuperFree")
        self.assertEqual(Result["Board"][4], 1)
        self.assertEqual(Result["ScatterCount"], 0)

    def test_fill_allows_multiple_ordinary_wilds_above_scatter(self):
        self.Model.ActivatedColumns = {0}
        Board = self.blank_board()
        Board[0] = [2, 2, 3, 0, 4]
        Result = self.Model.evaluate(Board, Mode="SuperFree")
        self.assertEqual(Result["Board"][:5], [2, 2, 3, 0, 1])
        self.assertEqual(Result["Replacements"][0]["Position"], 4)
        self.assertEqual(Result["ScatterCount"], 1)

    def test_fill_candidate_can_replace_ordinary_wild_itself(self):
        self.Model.ActivatedColumns = {0}
        Board = self.blank_board()
        Board[0] = [2, 3, 3, 3, 2]
        with patch.object(self.Model.Rng, "randrange", return_value=0):
            Result = self.Model.evaluate(Board, Mode="SuperFree")
        self.assertEqual(Result["Board"][:5], [1, 3, 3, 3, 2])
        self.assertEqual(Result["Replacements"][0]["Position"], 0)

    def test_fill_rejects_any_candidate_with_two_ordinary_wilds_below(self):
        self.Model.ActivatedColumns = {0}
        Board = self.blank_board()
        Board[0] = [3, 2, 3, 3, 2]
        with self.assertRaises(ValueError):
            self.Model.evaluate(Board, Mode="SuperFree")

    def test_bottom_scatter_fill_preserves_multiple_wilds_above(self):
        self.Model.ActivatedColumns = {0}
        Board = self.blank_board()
        Board[0] = [2, 2, 3, 4, 0]
        with patch.object(self.Model.Rng, "randrange", side_effect=AssertionError("底行直接替换无需抽样")):
            Result = self.Model.evaluate(Board, Mode="SuperFree")
        self.assertEqual(Result["Board"][:5], [2, 2, 3, 4, 1])
        self.assertEqual(Result["ScatterCount"], 0)

    def test_unextended_wild_activates_column_and_multiplier_does_not_persist(self):
        self.Model.start_free(Mode="SuperFree", FreeSpins=3)
        Board = self.blank_board()
        Board[4][0] = 1
        First = self.Model.fg_spin(Board=Board, ReturnDetail=True)
        self.assertFalse(First["WildFeatures"][0]["Extended"])
        self.assertEqual(self.Model.ActivatedColumns, {4})
        self.force_multiplier("SuperFree", 5)
        Second = self.Model.fg_spin(Board=self.fusion_board(), ReturnDetail=True)
        self.assertTrue(any(Feature["Multiplier"] == 5 for Feature in Second["WildFeatures"]))
        Third = self.Model.fg_spin(Board=[[3] * 5 for _ in range(5)], ReturnDetail=True)
        self.assertTrue(all(Feature["Multiplier"] == 0 for Feature in Third["WildFeatures"]))
        self.assertEqual(self.Model.Mode, "Main")
        self.assertEqual(self.Model.ActivatedColumns, set())

    def test_free_total_continues_across_upgrade_and_new_session_resets_it(self):
        self.Model.start_free(FreeSpins=2)
        First = self.Model.fg_spin(Board=[[3] * 5 for _ in range(5)])
        Upgrade = self.Model.fg_spin(Board=self.scatter_board(4))
        Super = self.Model.fg_spin(Board=[[3] * 5 for _ in range(5)])
        self.assertEqual(self.Model.FreeTotalWin, First["TotalWin"] + Upgrade["TotalWin"] + Super["TotalWin"])
        self.assertEqual(self.Model.FreeSpinsPlayed, 3)
        self.assertEqual(self.Model.FreeSpinsAwarded, 12)
        while self.Model.FreeSpinsRemaining:
            self.Model.fg_spin(Board=self.blank_board())
        self.Model.ng_spin(Board=self.scatter_board(3))
        self.assertEqual((self.Model.FreeTotalWin, self.Model.FreeSpinsPlayed, self.Model.FreeSpinsAwarded), (0, 0, 10))

    def test_evaluate_is_read_only_for_session_and_input_board(self):
        self.Model.start_free(Mode="SuperFree")
        self.Model.ActivatedColumns = {0}
        Board = self.blank_board()
        Before = deepcopy(Board)
        State = (self.Model.Mode, self.Model.FreeSpinsRemaining, self.Model.FreeSpinsPlayed, self.Model.FreeTotalWin, set(self.Model.ActivatedColumns))
        self.Model.evaluate(Board, Mode="SuperFree")
        self.assertEqual(Board, Before)
        self.assertEqual(State, (self.Model.Mode, self.Model.FreeSpinsRemaining, self.Model.FreeSpinsPlayed, self.Model.FreeTotalWin, self.Model.ActivatedColumns))

    def test_session_guards_and_instances_are_independent(self):
        Other = ThemeMath(Seed=373)
        with self.assertRaises(RuntimeError):
            self.Model.fg_spin()
        self.Model.start_free()
        with self.assertRaises(RuntimeError):
            self.Model.ng_spin()
        with self.assertRaises(RuntimeError):
            self.Model.start_free()
        self.assertEqual((Other.Mode, Other.FreeSpinsRemaining), ("Main", 0))

    def test_initial_free_count_cannot_reach_control_limit(self):
        for Count in (0, 99, 100):
            with self.subTest(Count=Count), self.assertRaises(ValueError):
                self.Model.start_free(FreeSpins=Count)
        self.assertEqual((self.Model.Mode, self.Model.FreeSpinsRemaining), ("Main", 0))

    def test_detail_switch_keeps_money_and_state_identical(self):
        Other = ThemeMath(Seed=373)
        Detailed = self.Model.ng_spin(Board=self.fusion_board(), ReturnDetail=True)
        Compact = Other.ng_spin(Board=self.fusion_board(), ReturnDetail=False)
        for Name in ("TotalWin", "UltimateHit", "NextMode", "FreeSpinsRemaining", "FreeTotalWin"):
            self.assertEqual(Detailed[Name], Compact[Name])
        self.assertTrue(Detailed["WinItems"])
        self.assertEqual(Compact["WinItems"], [])
        self.assertEqual(Compact["WildFeatures"], [])

    def test_unconfigured_bet_is_rejected_and_template_reel_fallback_is_reported(self):
        for Bet in (-1, 123456):
            with self.subTest(Bet=Bet), self.assertRaises(ValueError):
                ThemeMath(base_bet=Bet)
        Result = self.Model.ng_spin(index=99, general_index=99, return_detail=True)
        self.assertTrue(Result["spin_info"]["reel_config_index_fallback"])
        self.assertTrue(Result["spin_info"]["general_index_fallback"])
        self.assertEqual(Result["spin_info"]["general_index"], 1)

    def test_same_seed_replays_complete_rounds(self):
        Other = ThemeMath(Seed=373)
        for _ in range(20):
            self.assertEqual(self.Model.play_round(ReturnDetail=True), Other.play_round(ReturnDetail=True))

    def test_all_cyclic_reel_windows_meet_symbol_constraints(self):
        Files = (
            ("Main", "reel_config/cjyx_rand_ex_0.conf"),
            ("Free", "free_reel_config/cjyx_free_rand_ex_0.conf"),
            ("SuperFree", "free_reel_config/cjyx_super_free_rand_ex_0.conf"),
        )
        for Mode, FileName in Files:
            Parser = self.Model._read_config_file(ProjectDir / FileName)
            Section = Parser["GENERAL_1"]
            for Prefix in ("NORMAL_ROLL_", "SP_ROLL_"):
                for Column in range(1, 6):
                    Reel = self.Model._parse_int_list(Section[f"{Prefix}{Column}"])
                    for Start in range(len(Reel)):
                        Window = [Reel[(Start + Offset) % len(Reel)] for Offset in range(5)]
                        with self.subTest(Mode=Mode, Prefix=Prefix, Column=Column, Start=Start):
                            self.assertLessEqual(Window.count(0), 1)
                            self.assertLessEqual(Window.count(1), 1)
                            if 1 in Window:
                                WildRow = Window.index(1)
                                self.assertNotIn(0, Window[WildRow + 1:])
                                self.assertLessEqual(Window[WildRow + 1:].count(2), 1)
                            elif Mode == "SuperFree":
                                ScatterRow = Window.index(0) if 0 in Window else -1
                                Candidates = [4] if ScatterRow == 4 else range(ScatterRow + 1, 5)
                                for Candidate in Candidates:
                                    self.assertLessEqual(Window[Candidate + 1:].count(2), 1)

    def test_malformed_fixed_boards_are_rejected(self):
        InvalidColumns = ([1, 1, 3, 4, 5], [0, 0, 3, 4, 5], [1, 0, 3, 4, 5], [1, 2, 2, 4, 5], [3, 4, 5, 6, 13])
        for Column in InvalidColumns:
            with self.subTest(Column=Column):
                Board = self.blank_board()
                Board[0] = list(Column)
                with self.assertRaises(ValueError):
                    self.Model.evaluate(Board)
        with self.assertRaises(ValueError):
            self.Model.evaluate([3] * 24)

    def test_invalid_configurations_are_rejected_at_load(self):
        Mutations = (
            (ConfigPath, "MAIN", "ROW_COUNT", "4"),
            (ServerPath, "0", "MainFusionWeights", ",".join(["0"] * 15)),
            (ServerPath, "0", "FreeFusionWeights", "-1," + ",".join(["1"] * 14)),
            (ServerPath, "0", "SuperFreeWildFillWeights", ",".join(["1"] * 24)),
            (ConfigPath, "MAIN", "LINE_RULES_0", "0,0,10,15,20"),
            (ConfigPath, "MAIN", "ITEM_PRIZES_1", "0,0,10000,0,250000"),
        )
        for RelativePath, Section, Key, Value in Mutations:
            with self.subTest(Key=Key), tempfile.TemporaryDirectory() as Directory:
                Target = Path(Directory) / "cjyx"
                shutil.copytree(ProjectDir, Target, ignore=shutil.ignore_patterns("__pycache__"))
                Parser = self.Model._read_config_file(Target / RelativePath)
                Parser[Section][Key] = Value
                with (Target / RelativePath).open("w", encoding="utf-8") as Handle:
                    Parser.write(Handle)
                with self.assertRaises(ValueError):
                    ThemeMath(project_dir=Target)

    def test_directory_and_configuration_follow_lines_template(self):
        Template = ProjectDir.parent / "model_linesgame"
        for Source in Template.rglob("*.conf"):
            Relative = Path(str(Source.relative_to(Template)).replace("xxx", "cjyx"))
            self.assertTrue((ProjectDir / Relative).is_file(), Relative)
        self.assertFalse(list(ProjectDir.rglob("*.json")))
        self.assertFalse((ProjectDir / "super_free_reel_config").exists())
        self.assertIsInstance(self.Model, LinesGame)
        self.assertEqual((self.Model.config.col_count, self.Model.config.row_count), (5, 5))
        self.assertEqual(self.Model.config.line_mode, 2)
        self.assertEqual(len(self.Model.config.line_rules), 19)

    def test_only_game_server_or_bonus_can_add_theme_config_fields(self):
        for FileName in sorted(ProjectDir.rglob("*.conf")):
            with self.subTest(FileName=FileName.relative_to(ProjectDir)):
                self.assert_template_config_schema(FileName)
        self.assertFalse((ProjectDir / "special/cjyx_bonus.conf").exists())

    def test_generated_reels_keep_only_model_sections_and_fields(self):
        with tempfile.TemporaryDirectory() as Directory:
            RootDir = Path(Directory)
            Outputs = build_reels(OutputDir=RootDir, Seed=20261026)
            self.assertEqual(len(Outputs), 5)
            for FileName in Outputs:
                with self.subTest(FileName=FileName.relative_to(RootDir)):
                    self.assert_template_config_schema(FileName, RootDir=RootDir)

    def test_all_bet_coefficients_produce_the_confirmed_money_and_integer_awards(self):
        ExpectedBets = [100000, 200000, 500000, 1000000, 2000000, 5000000, 10000000, 20000000]
        Server = self.Model._read_config_file(ProjectDir / ServerPath)["System Base Info"]
        Coefficients = self.Model._parse_int_list(Server["BetScopes"])
        PerReel = self.Model._parse_int_list(Server["BetPerReel"])
        self.assertEqual(Coefficients, [10, 20, 50, 100, 200, 500, 1000, 2000])
        self.assertEqual(len(Coefficients), len(PerReel))
        self.assertEqual(
            [Coefficient * ReelBet * self.Model.BET_UNIT for Coefficient, ReelBet in zip(Coefficients, PerReel)],
            ExpectedBets,
        )
        self.assertEqual(self.Model.GameInfo["BetLevels"], ExpectedBets)
        for Bet in ExpectedBets:
            with self.subTest(Bet=Bet):
                Model = ThemeMath(base_bet=Bet, Seed=373)
                self.assertEqual(Model.base_bet, Bet)
                for Prizes in Model.config.item_prizes:
                    for Prize in Prizes:
                        self.assertEqual((Bet * Prize) % (Model.BET_UNIT * Model.config.prize_rate), 0)
                Result = Model.evaluate(item_list=[[3] * 5 for _ in range(5)], return_detail=True)
                self.assertIsInstance(Result["total_win"], int)
                self.assertEqual(Result["total_win"], 19 * 20 * Bet)

    def test_wilds_do_not_enable_wild_substitution_for_their_own_awards(self):
        self.assertEqual(self.Model.config.use_wilds[:3], [0, 0, 0])
        self.assertEqual(self.Model.config.use_wilds[3:], [1] * 10)
        Result = self.Model.cal_item_list([[2] * 5 for _ in range(5)], return_detail=True)
        self.assertEqual(Result["total_win"], 19 * 25 * self.Model.base_bet)

    def test_initial_boards_are_twenty_five_cells_without_rewards(self):
        Parser = self.Model._read_config_file(ProjectDir / ConfigPath)
        Main = Parser["MAIN"]
        Count = int(Main["INIT_ROLLER_COUNT"])
        self.assertGreaterEqual(Count, 5)
        for Index in range(Count):
            Board = self.Model._parse_int_list(Main[f"INIT_ROLLER_ICON_{Index}"])
            self.assertEqual(len(Board), 25)
            Result = self.Model.evaluate(item_list=Board, return_detail=True)
            self.assertEqual(Result["total_win"], 0)
            self.assertFalse(Result["win_free"])

    def test_template_spin_and_line_evaluation_are_really_used(self):
        Original = LinesGame.cal_item_list
        with patch.object(self.Model, "spin", wraps=self.Model.spin) as SpinCall:
            Result = self.Model.ng_spin(0, 1, return_detail=True)
        self.assertEqual(SpinCall.call_count, 1)
        self.assertEqual(len(Result["item_list"]), 5)
        self.assertTrue(all(len(Column) == 5 for Column in Result["item_list"]))
        self.assertEqual(Result["spin_info"]["reel_config_file"], "cjyx_rand_ex_0.conf")
        with patch.object(LinesGame, "cal_item_list", autospec=True, side_effect=Original) as EvaluateCall:
            Result = self.Model.evaluate(item_list=self.fusion_board(), return_detail=True)
        self.assertGreaterEqual(EvaluateCall.call_count, 1)
        self.assertEqual(Result["total_win"], Result["TotalWin"])
        self.assertEqual(sum(Item["win"] for Item in Result["win_items"]), Result["total_win"])

    def test_all_four_template_spin_sources_are_honored(self):
        Cases = (
            ("normal", 0, [[3] * 5 for _ in range(5)], 19 * 20 * 100000),
            ("special", 1, [[4] * 5 for _ in range(5)], 19 * 175 * 100000 // 10),
            ("fix", 2, [[5] * 5 for _ in range(5)], 19 * 175 * 100000 // 10),
            ("zero", 3, self.blank_board(), 0),
        )
        for SourceType, RateIndex, Board, ExpectedWin in Cases:
            with self.subTest(SourceType=SourceType), tempfile.TemporaryDirectory() as Directory:
                Target = Path(Directory) / "cjyx"
                shutil.copytree(ProjectDir, Target, ignore=shutil.ignore_patterns("__pycache__"))
                ReelPath = Target / "reel_config/cjyx_rand_ex_0.conf"
                Parser = self.Model._read_config_file(ReelPath)
                Section = Parser["GENERAL_1"]
                Section["BASE_RATE"] = ",".join("10000" if Index == RateIndex else "0" for Index in range(4))
                if SourceType in ("normal", "special"):
                    Prefix = "NORMAL_ROLL_" if SourceType == "normal" else "SP_ROLL_"
                    for Column, Symbols in enumerate(Board, 1):
                        Section[f"{Prefix}{Column}"] = ",".join(map(str, Symbols))
                else:
                    Prefix = "FIX" if SourceType == "fix" else "ZERO"
                    Section[f"{Prefix}_NUM"] = "1"
                    Section[f"{Prefix}_DISORDER"] = "0"
                    Section[f"{Prefix}_RESULT_1"] = ",".join(str(Symbol) for Symbols in Board for Symbol in Symbols)
                with ReelPath.open("w", encoding="utf-8") as Handle:
                    Parser.write(Handle)
                Model = ThemeMath(base_bet=100000, project_dir=Target, Seed=373)
                Result = Model.ng_spin(0, 1, return_detail=True)
                self.assertEqual(Result["spin_info"]["spin_type"], SourceType)
                self.assertEqual(Result["total_win"], ExpectedWin)
                self.assertEqual(Result["item_list"], Board)

    def test_each_free_mode_selects_its_own_conf_in_standard_directory(self):
        for Mode, FileName in (
            ("Free", "cjyx_free_rand_ex_0.conf"),
            ("SuperFree", "cjyx_super_free_rand_ex_0.conf"),
        ):
            with self.subTest(Mode=Mode):
                Model = ThemeMath(Seed=373)
                Model.start_free(Mode=Mode, FreeSpins=1)
                Result = Model.fg_spin(0, 1, return_detail=True)
                self.assertEqual(Result["spin_info"]["reel_config_file"], FileName)
                self.assertEqual(Path(Result["spin_info"]["reel_config_dir"]).name, "free_reel_config")


    def test_template_cal_item_list_treats_both_wilds_as_substitutes(self):
        Board = [[3] * 5, [2] * 5, [3] * 5, [4] * 5, [5] * 5]
        Result = self.Model.cal_item_list(Board, return_detail=True)
        self.assertEqual(Result["total_win"], 19 * 2 * self.Model.base_bet)
        self.assertEqual(len(Result["items"]), 19)
        self.assertTrue(all(Item["hit_num"] == 3 for Item in Result["items"]))

    def test_template_free_query_and_fixed_evaluation_report_retriggers(self):
        self.assertTrue(self.Model.check_win_free(self.scatter_board(3)))
        self.assertFalse(self.Model.check_win_free(self.scatter_board(2)))
        Result = self.Model.evaluate(item_list=self.scatter_board(3), free_game=True)
        self.assertTrue(Result["win_free"])
        self.assertEqual(self.Model.FreeSpinsRemaining, 0)
        self.Model.start_free(FreeSpins=11)
        Upgrade = self.Model.fg_spin(Board=self.scatter_board(4))
        self.assertEqual(Upgrade["AwardedFreeSpins"], 0)
        self.assertTrue(Upgrade["Upgraded"])
        self.assertTrue(Upgrade["win_free"])

    @staticmethod
    def add_type_config(Target, TypeIndex, Multiplier):
        ServerFile = Target / ServerPath
        Parser = ThemeMath._read_config_file(ServerFile)
        Parser[str(TypeIndex)] = dict(Parser["0"])
        Values = ThemeMath._parse_int_list(Parser["Game Info"]["FusionMultipliers"])
        for Mode in ("Main", "Free", "SuperFree"):
            Parser[str(TypeIndex)][Mode + "FusionWeights"] = ",".join(str(int(Value == Multiplier)) for Value in Values)
        with ServerFile.open("w", encoding="utf-8") as Handle:
            Parser.write(Handle)
        for Relative in (
            "reel_config/cjyx_rand_ex_0.conf",
            "free_reel_config/cjyx_free_rand_ex_0.conf",
            "free_reel_config/cjyx_super_free_rand_ex_0.conf",
        ):
            shutil.copy2(Target / Relative, Target / Relative.replace("_0.conf", f"_{TypeIndex}.conf"))

    def test_type_parameters_follow_actual_file_and_stay_locked_through_upgrade(self):
        with tempfile.TemporaryDirectory() as Directory:
            Target = Path(Directory) / "cjyx"
            shutil.copytree(ProjectDir, Target, ignore=shutil.ignore_patterns("__pycache__", "*.csv"))
            self.add_type_config(Target, 4, 7)
            Parser = self.Model._read_config_file(Target / ServerPath)
            Values = self.Model._parse_int_list(Parser["Game Info"]["FusionMultipliers"])
            for Mode in ("Main", "Free", "SuperFree"):
                Parser["0"][Mode + "FusionWeights"] = ",".join(str(int(Value == 2)) for Value in Values)
            with (Target / ServerPath).open("w", encoding="utf-8") as Handle:
                Parser.write(Handle)
            Model = ThemeMath(project_dir=Target, Seed=373)
            self.assertIs(Model.TypeConfigs[0], Model.GameInfo)
            Fourth = Model.ng_spin(index=4, Board=self.fusion_board(), return_detail=True)
            self.assertEqual(Fourth["TypeIndex"], 4)
            self.assertEqual(Fourth["WildFeatures"][0]["Multiplier"], 7)
            Fallback = Model.ng_spin(index=99, Board=self.fusion_board(), return_detail=True)
            self.assertEqual(Fallback["TypeIndex"], 0)
            self.assertTrue(Fallback["spin_info"]["reel_config_index_fallback"])
            self.assertEqual(Fallback["WildFeatures"][0]["Multiplier"], 2)
            Model.ng_spin(index=4, Board=self.scatter_board(3))
            self.assertEqual(Model.FreeType, 4)
            Before = (Model.Rng.getstate(), Model.FreeSpinsRemaining, Model.FreeSpinsPlayed, Model.FreeTotalWin)
            with self.assertRaisesRegex(ValueError, "本轮免费须沿用 TYPE 4"):
                Model.fg_spin(index=0, Board=self.fusion_board())
            self.assertEqual(Before, (Model.Rng.getstate(), Model.FreeSpinsRemaining, Model.FreeSpinsPlayed, Model.FreeTotalWin))
            Free = Model.fg_spin(index=4, Board=self.fusion_board(), return_detail=True)
            self.assertEqual(Free["WildFeatures"][0]["Multiplier"], 7)
            Upgrade = Model.fg_spin(index=4, Board=self.scatter_board(4))
            self.assertTrue(Upgrade["Upgraded"])
            self.assertEqual((Model.CurrentType, Model.FreeType), (4, 4))
            Super = Model.fg_spin(index=4, Board=self.fusion_board(), return_detail=True)
            self.assertEqual(Super["WildFeatures"][0]["Multiplier"], 7)
            while Model.FreeSpinsRemaining:
                Model.fg_spin(index=4, Board=self.blank_board())
            self.assertIsNone(Model.FreeType)
            self.assertEqual(Model.Mode, "Main")

    def test_type_requires_parameter_section_and_all_three_reel_sets(self):
        with tempfile.TemporaryDirectory() as Directory:
            Target = Path(Directory) / "cjyx"
            shutil.copytree(ProjectDir, Target, ignore=shutil.ignore_patterns("__pycache__", "*.csv"))
            shutil.copy2(Target / "reel_config/cjyx_rand_ex_0.conf", Target / "reel_config/cjyx_rand_ex_4.conf")
            with self.assertRaisesRegex(ValueError, r"缺少 TYPE 参数段 \[4\]"):
                ThemeMath(project_dir=Target)
            Parser = self.Model._read_config_file(Target / ServerPath)
            Parser["4"] = dict(Parser["0"])
            with (Target / ServerPath).open("w", encoding="utf-8") as Handle:
                Parser.write(Handle)
            with self.assertRaisesRegex(ValueError, "同时配置主游戏、普通免费和超级免费轴带"):
                ThemeMath(project_dir=Target)

    def test_core_protocol_values_cannot_silently_change_scatter_or_bet_meaning(self):
        Mutations = (
            (ConfigPath, "MAIN", "PRIZE_RATE", "0"),
            (ConfigPath, "MAIN", "PRIZE_RATE", "-1"),
            (ConfigPath, "MAIN", "RULE_COUNT", "0"),
            (ConfigPath, "MAIN", "SCATTER_ID", "3"),
            (ConfigPath, "MAIN", "SCATTER_COLS", "0,1,1,1,1"),
            (ConfigPath, "MAIN", "SCATTER_SERIAL", "1"),
            (ConfigPath, "MAIN", "SCATTER_MULTIPLES", "0,0,0,10,10,0"),
            (ServerPath, "System Base Info", "BetPerReel", ",".join(["2"] * 8)),
            (ServerPath, "Game Info", "MainFusionWeights", ",".join(["1"] * 15)),
        )
        for Relative, Section, Key, Value in Mutations:
            with self.subTest(Key=Key, Value=Value), tempfile.TemporaryDirectory() as Directory:
                Target = Path(Directory) / "cjyx"
                shutil.copytree(ProjectDir, Target, ignore=shutil.ignore_patterns("__pycache__", "*.csv"))
                Parser = self.Model._read_config_file(Target / Relative)
                Parser[Section][Key] = Value
                with (Target / Relative).open("w", encoding="utf-8") as Handle:
                    Parser.write(Handle)
                with self.assertRaises(ValueError):
                    ThemeMath(project_dir=Target)

    def test_reel_limits_reject_more_than_two_hundred_symbols_or_five_hundred_bytes(self):
        for Value in (",".join(["3"] * 201), ",".join(["12"] * 200), ",".join(["3  "] * 200)):
            with self.subTest(Length=len(Value)), tempfile.TemporaryDirectory() as Directory:
                Target = Path(Directory) / "cjyx"
                shutil.copytree(ProjectDir, Target, ignore=shutil.ignore_patterns("__pycache__", "*.csv"))
                PathValue = Target / "reel_config/cjyx_rand_ex_0.conf"
                Parser = self.Model._read_config_file(PathValue)
                Parser["GENERAL_1"]["NORMAL_ROLL_1"] = Value
                with PathValue.open("w", encoding="utf-8") as Handle:
                    Parser.write(Handle)
                with self.assertRaises(ValueError):
                    ThemeMath(project_dir=Target)

    def test_seed_constructor_rejects_non_integer_runtime_values(self):
        for Seed in (True, "373", 373.0):
            with self.subTest(Seed=Seed), self.assertRaises(ValueError):
                ThemeMath(Seed=Seed)

    def test_inherited_spin_restores_global_random_sequence_even_on_failure(self):
        Before = random.getstate()
        self.Model.ng_spin(0, 1)
        self.assertEqual(random.getstate(), Before)
        Other = ThemeMath(Seed=373)
        with patch.object(Other, "spin", side_effect=ValueError("抽盘错误")):
            with self.assertRaises(ValueError):
                Other.ng_spin(0, 1)
        self.assertEqual(random.getstate(), Before)


if __name__ == "__main__":
    unittest.main()
