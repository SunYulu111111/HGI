"""核对 cjyx 配置的服务器格式、档位关联和生成版本。"""

from pathlib import Path
import sys
import tempfile
import unittest

try:
    from .build_demo_reels import build_reels
except ImportError:
    from build_demo_reels import build_reels


ProjectDir = Path(__file__).resolve().parent
RootDir = ProjectDir.parent
if str(RootDir) not in sys.path:
    sys.path.insert(0, str(RootDir))

from slots_math import LinesGame


class ConfigContractTests(unittest.TestCase):
    def setUp(self):
        self.Model = LinesGame(base_bet=100000, project_dir=ProjectDir, game_config_file="special/cjyx_game_config.conf")

    def read_config(self, Relative):
        return self.Model._read_config_file(ProjectDir / Relative)

    def test_reel_specs_match_generals_and_server_limits(self):
        Modes = (
            ("reel_config/cjyx_rand_main.conf", "reel_config/cjyx_rand_ex_0.conf"),
            ("free_reel_config/cjyx_free_rand_main.conf", "free_reel_config/cjyx_free_rand_ex_0.conf"),
            ("free_reel_config/cjyx_free_rand_main.conf", "free_reel_config/cjyx_super_free_rand_ex_0.conf"),
        )
        for MainFile, ReelFile in Modes:
            Spec = self.read_config(MainFile)["MAIN"]
            Parser = self.read_config(ReelFile)
            Generals = [Section for Section in Parser if Section.startswith("GENERAL_")]
            self.assertEqual(int(Spec["ITEM_COM_COUNT"]), len(Generals))
            self.assertEqual((int(Spec["COL_COUNT"]), int(Spec["ROW_COUNT"]), int(Spec["ITEM_COUNT"])), (5, 5, 13))
            for General in Generals:
                Section = Parser[General]
                for Prefix in ("NORMAL_ROLL_", "SP_ROLL_"):
                    for Column in range(1, 6):
                        Value = Section[f"{Prefix}{Column}"]
                        self.assertLessEqual(len(Value), 500)
                        self.assertLessEqual(len(Value.split(",")), 200)
                for Prefix in ("FIX", "ZERO"):
                    Count = int(Section[f"{Prefix}_NUM"])
                    self.assertTrue(0 <= Count <= 200)
                    for Index in range(1, Count + 1):
                        Board = self.Model._parse_int_list(Section[f"{Prefix}_RESULT_{Index}"])
                        self.assertEqual(len(Board), 25)
                        self.assertEqual(self.Model.cal_item_list(Board), 0)

    def test_scatter_arrays_and_all_eight_bet_arrays_are_consistent(self):
        Main = self.read_config("special/cjyx_game_config.conf")["MAIN"]
        self.assertEqual(self.Model._parse_int_list(Main["SCATTER_MULTIPLES"]), [0] * 25)
        self.assertEqual(self.Model._parse_int_list(Main["SCATTER_PRIZES"]), [0] * 25)
        Server = self.read_config("special/cjyx_game_server.conf")
        Base = Server["System Base Info"]
        for Key in ("BetScopes", "BetPerReel", "BetUnLockLevel", "BetUnLockVip"):
            self.assertEqual(len(self.Model._parse_int_list(Base[Key])), 8, Key)
        self.assertEqual(len(self.Model._parse_int_list(Server["Game Info"]["BetGeneralCtrl"])), 8)
        self.assertNotIn("MainFusionWeights", Server["Game Info"])
        for Key in ("MainFusionWeights", "FreeFusionWeights", "SuperFreeFusionWeights"):
            self.assertEqual(len(self.Model._parse_int_list(Server["0"][Key])), 15)
        self.assertEqual(len(self.Model._parse_int_list(Server["0"]["SuperFreeWildFillWeights"])), 25)

    def test_control_arrays_match_legal_bets_and_existing_groups(self):
        Server = self.read_config("special/cjyx_game_server.conf")
        Base = Server["System Base Info"]
        Bets = {10000 * Scope * PerReel for Scope, PerReel in zip(self.Model._parse_int_list(Base["BetScopes"]), self.Model._parse_int_list(Base["BetPerReel"]))}
        Groups = self.read_config("special_config/slot_control_group.conf")
        GroupIds = {int(Section.removeprefix("CONTROL_GROUP_")) for Section in Groups if Section.startswith("CONTROL_GROUP_")}
        self.assertEqual(GroupIds, set(range(18)))
        ExpectedCuts = [5000, 0, 0, 0, 12000, 0, 0, 0, 1000, 0, 0, 0, 20, 0, 0, 0, 0, 1000]
        for Key in ("control_group_cut_multiple", "control_group_free_cut_multiple"):
            self.assertEqual(self.Model._parse_int_list(Groups["MAIN"][Key]), ExpectedCuts)
        for Group in GroupIds:
            Section = Groups[f"CONTROL_GROUP_{Group}"]
            Rates = self.Model._parse_int_list(Section["lable_user_control_group_rate"])
            Values = self.Model._parse_int_list(Section["lable_user_control_group_value"])
            self.assertEqual(len(Rates), len(Values))
            self.assertLessEqual(len(Rates), 20)
            self.assertTrue(all(Rate >= 0 for Rate in Rates))
            self.assertGreater(sum(Rates), 0)
            for Value in Values:
                TypeIndex = Value // 100
                self.assertIn(str(TypeIndex), Server)
                self.assertTrue((ProjectDir / f"reel_config/cjyx_rand_ex_{TypeIndex}.conf").is_file())
                self.assertTrue((ProjectDir / f"free_reel_config/cjyx_free_rand_ex_{TypeIndex}.conf").is_file())
        Controls = self.read_config("special/cjyx_control.conf")
        PipeFields = {"lable_user_day_balance", "lable_user_user_control_buff", "lable_user_day_avg_bet_coefficient", "lable_user_day_rtp", "lable_user_user_money", "lable_user_total_infull_exp"}
        ScalarFields = {"lable_user_user_control_buff_deduct", "lable_user_day_control_count", "lable_user_day_control_index", "lable_user_control_rate", "lable_user_control_group"}
        for Name in Controls:
            if not Name.startswith("CONTROL_"):
                continue
            Section = Controls[Name]
            ConfiguredBets = self.Model._parse_int_list(Section["lable_user_bet_money"])
            self.assertTrue(set(ConfiguredBets).issubset(Bets))
            for Key in PipeFields.intersection(Section):
                self.assertEqual(len(Section[Key].split("|")), len(ConfiguredBets), (Name, Key))
            for Key in ScalarFields.intersection(Section):
                self.assertEqual(len(self.Model._parse_int_list(Section[Key])), len(ConfiguredBets), (Name, Key))
            for Group in self.Model._parse_int_list(Section["lable_user_control_group"]):
                self.assertIn(Group, GroupIds)
            self.assertTrue(0 <= int(Section["lable_user_percent"]) <= 10000)
            self.assertTrue(all(0 <= Rate <= 10000 for Rate in self.Model._parse_int_list(Section["lable_user_control_rate"])))
            Counts = self.Model._parse_int_list(Section["lable_user_day_control_count"])
            Indexes = self.Model._parse_int_list(Section["lable_user_day_control_index"])
            for Count, Index in zip(Counts, Indexes):
                self.assertTrue(0 <= Count <= 99)
                self.assertTrue(1 <= Index <= 5 or (Index == 0 and Count == 0))

    def test_unconfigured_prop_features_and_bonus_have_no_placeholder_entries(self):
        Props = self.read_config("special/slot_prop_config.conf")
        self.assertFalse(any(Section.startswith("SLOT_PROP_INFO_") for Section in Props))
        self.assertGreater(int(Props["System Base Info"]["OPEN_GAME_VER"]), 0)
        Controls = self.read_config("special/cjyx_control.conf")
        self.assertNotIn("FREE_PROP_CONTROL", Controls)
        self.assertNotIn("SPIN_PROP_CONTROL", Controls)
        self.assertNotIn("free_prop_lable_user_percent", Controls["MAIN"])
        self.assertFalse((ProjectDir / "special/cjyx_bonus.conf").exists())

    def test_generator_reloads_main_only_after_real_reel_changes(self):
        with tempfile.TemporaryDirectory() as Directory:
            Outputs = build_reels(OutputDir=Directory, Seed=20261026)
            First = {PathValue: PathValue.read_bytes() for PathValue in Outputs}
            Versions = {PathValue: int(self.Model._read_config_file(PathValue)["MAIN"]["VERSION"]) for PathValue in Outputs}
            build_reels(OutputDir=Directory, Seed=20261026)
            self.assertEqual(First, {PathValue: PathValue.read_bytes() for PathValue in Outputs})
            build_reels(OutputDir=Directory, Seed=20261027)
            for PathValue in Outputs:
                self.assertEqual(int(self.Model._read_config_file(PathValue)["MAIN"]["VERSION"]), Versions[PathValue] + 1)
            Second = {PathValue: PathValue.read_bytes() for PathValue in Outputs}
            build_reels(OutputDir=Directory, Seed=20261027)
            self.assertEqual(Second, {PathValue: PathValue.read_bytes() for PathValue in Outputs})


if __name__ == "__main__":
    unittest.main()
