"""MaxWinCoin 配置路由、金额边界与砍分结算测试。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from simulation import record_spin, status_model
from theme_math import ThemeMath


class FixedRandom:
    def __init__(self, Last=False):
        self.Last = Last
        self.Calls = 0

    def randrange(self, stop):
        self.Calls += 1
        return stop - 1 if self.Last else 0


class MaxWinCoinTest(unittest.TestCase):
    def setUp(self):
        self.Math = ThemeMath(rng=FixedRandom())
        self.Math.MaxWinCoin = 0
        self.Math.GroupMaxWinCoin = {}

    def load_limits(self, Default=None, Groups=None):
        Config = self.Math.game_server_config
        for Section in Config.sections():
            Config.remove_option(Section, "MaxWinCoin")
        if Default is not None:
            Config["Game Info"]["MaxWinCoin"] = str(Default)
        for Group, Limit in (Groups or {}).items():
            Config[str(Group)]["MaxWinCoin"] = str(Limit)
        with TemporaryDirectory() as Directory:
            File = Path(Directory) / "server.conf"
            with File.open("w", encoding="utf-8") as Stream:
                Config.write(Stream)
            return ThemeMath(game_server_config_file=File)

    def force_index(self, Index):
        self.Math.win_weights = [0] * len(self.Math.win_weights)
        self.Math.win_weights[Index] = 1
        for Group in self.Math.group_win_weights:
            self.Math.group_win_weights[Group] = list(self.Math.win_weights)

    def force_bonus(self):
        self.force_index(9)
        self.Math.respin_count_weights = [0, 0, 1, 0, 0, 0, 0, 0]
        self.Math.bonus_win_weights = [0] * len(self.Math.bonus_win_weights)
        for Index in (2, 3, 4):
            self.Math.bonus_win_weights[Index] = 1

    def test_group_override_fallback_and_explicit_zero(self):
        Math = self.load_limits(200, {8: 100, 4: 0})
        for Group, Expected in ((0, 200), (1, 200), (8, 100), (4, 0)):
            self.assertEqual(Math.get_max_win_coin(Group), Expected)
        Math = self.load_limits()
        self.assertEqual(Math.get_max_win_coin(0), 0)
        self.assertEqual(Math.get_max_win_coin(8), 0)

    def test_invalid_amounts_are_rejected(self):
        for Value in (-1, "1.5", "", "abc"):
            for InGroup in (False, True):
                with self.subTest(Value=Value, InGroup=InGroup):
                    with self.assertRaises(ValueError):
                        self.load_limits(Groups={8: Value}) if InGroup else self.load_limits(Value)

    def test_normal_win_without_double_ignores_amount_limit(self):
        self.force_index(3)  # Symbol 2，100 倍，派彩 10,000,000。
        for Limit in (10_000_001, 10_000_000, 9_999_999, 1, 0):
            with self.subTest(Limit=Limit):
                self.Math.GroupMaxWinCoin[1] = Limit
                Result = self.Math.spin({2: 100_000}, group_index=1)
                Control = Result["control_result"]
                self.assertEqual(Control["MaxWinCoin"], Limit)
                self.assertFalse(Control["is_cut"])
                self.assertEqual(Control["cut_triggers"], [])
                self.assertEqual(Result["total_win"], 10_000_000)

    def test_bonus_without_double_ignores_amount_limit(self):
        self.force_bonus()
        self.Math.MaxWinCoin = 14_999_999
        Result = self.Math.spin({2: 100_000}, group_index=1)
        self.assertEqual(Result["control_result"]["cut_triggers"], [])
        self.assertEqual(Result["control_result"]["original_bonus_result"]["total_win"], 15_000_000)
        self.assertTrue(Result["is_bonus"])
        self.assertEqual(Result["winning_indexes"], [2, 3, 4])
        self.assertEqual(Result["total_win"], 15_000_000)

    def test_bonus_double_checks_successful_win(self):
        self.force_bonus()
        self.Math.rng = FixedRandom(Last=True)
        self.Math.MaxWinCoin = 20_000_000
        Result = self.Math.spin({2: 100_000}, group_index=1, double_times=1)
        self.assertEqual(Result["control_result"]["cut_triggers"], ["MaxWinCoin"])
        self.assertEqual(Result["control_result"]["original_bonus_result"]["total_win"], 15_000_000)
        self.assertEqual(Result["control_result"]["original_base_win"], 30_000_000)
        self.assertFalse(Result["is_bonus"])
        self.assertEqual(Result["total_win"], 0)

    def test_post_double_cut_uses_amount_and_updates_statistics(self):
        self.force_index(3)
        self.Math.rng = FixedRandom(Last=True)
        self.Math.MaxWinCoin = 15_000_000
        Bets = {2: 100_000}
        Result = self.Math.spin(Bets, group_index=1, double_times=1)
        self.assertEqual(Result["control_result"]["original_base_win"], 20_000_000)
        self.assertEqual(Result["control_result"]["cut_triggers"], ["MaxWinCoin"])
        self.assertEqual(Result["total_win"], 0)
        self.assertEqual(Result["double_result"]["total_win"], 0)
        self.assertEqual(Result["double_result"]["attempted_times"], 0)
        Status = deepcopy(status_model)
        record_spin(Status, Result, Bets)
        self.assertEqual(Status["wins"], 0)
        self.assertEqual(Status["control_cut_count"], 1)
        self.assertEqual(Status["control_original_win"], 20_000_000)

    def test_post_double_equal_amount_is_not_cut(self):
        self.force_index(3)
        self.Math.rng = FixedRandom(Last=True)
        self.Math.MaxWinCoin = 20_000_000
        Result = self.Math.spin({2: 100_000}, group_index=1, double_times=1)
        self.assertFalse(Result["control_result"]["is_cut"])
        self.assertEqual(Result["total_win"], 20_000_000)

    def test_all_bets_use_existing_replacement_not_amount_cap(self):
        self.force_index(3)
        self.Math.rng = FixedRandom(Last=True)
        Bets = {SymbolId: 100_000 for SymbolId in range(2, 10)}
        for Limit, DoubleTimes in ((5_000_000, 1), (15_000_000, 1), (300_000, 1), (1, 1)):
            with self.subTest(Limit=Limit, DoubleTimes=DoubleTimes):
                self.Math.MaxWinCoin = Limit
                Result = self.Math.spin(Bets, group_index=1, double_times=DoubleTimes)
                self.assertEqual(Result["total_win"], 300_000)
                self.assertEqual(Result["control_result"]["cut_reason"], "minimum_bet_symbol_x3")
                self.assertEqual(Result["double_result"]["total_win"], 300_000)
                self.assertEqual(Result["double_result"]["attempted_times"], 0)

    def test_amount_and_multiple_limits_are_independent(self):
        self.force_bonus()
        self.Math.control_group_cut_multiples[1] = 100
        self.Math.respin_max_multiples[1] = 100
        self.Math.MaxWinCoin = 1_000_000
        for Limit, Expected in ((1_000_000, ["control_group_cut_multiple", "RespinMaxMulti"]),
                                (0, ["control_group_cut_multiple", "RespinMaxMulti"])):
            self.Math.MaxWinCoin = Limit
            Result = self.Math.spin({2: 100_000}, group_index=1)
            self.assertEqual(Result["control_result"]["cut_triggers"], Expected)

    def test_small_amount_limit_does_not_reject_all_bets(self):
        self.force_index(3)
        self.Math.MaxWinCoin = 1
        Bets = {SymbolId: 100_000 for SymbolId in range(2, 10)}
        Result = self.Math.spin(Bets, group_index=1)
        self.assertEqual(Result["total_win"], 10_000_000)
        self.assertFalse(Result["control_result"]["is_cut"])

    def test_failed_double_does_not_cut_initial_win_above_limit(self):
        self.force_index(3)
        self.Math.MaxWinCoin = 1
        Result = self.Math.spin({2: 100_000}, group_index=1, double_times=1)
        self.assertTrue(Result["double_result"]["failed"])
        self.assertFalse(Result["control_result"]["is_cut"])
        self.assertEqual(Result["total_win"], 0)

    def test_no_win_means_no_double_or_amount_cut(self):
        self.force_index(14)
        self.Math.MaxWinCoin = 1
        Result = self.Math.spin({2: 100_000}, group_index=1, double_times=10)
        self.assertEqual(Result["double_result"]["attempted_times"], 0)
        self.assertFalse(Result["control_result"]["is_cut"])

    def test_limit_stops_double_before_a_later_failure(self):
        self.Math._weighted_index = lambda Weights: 1
        Result = self.Math.apply_double_up(100_000, 2, 100_000, MaxWinCoin=150_000)
        self.assertEqual(Result["attempted_times"], 1)
        self.assertEqual(Result["total_win"], 200_000)
        self.assertFalse(Result["can_double"])
        self.assertFalse(Result["failed"])
        # 未启用金额限制时，同一预选成功次数在第二次失败归零。
        Result = self.Math.apply_double_up(100_000, 2, 100_000, MaxWinCoin=0)
        self.assertEqual(Result["attempted_times"], 2)
        self.assertTrue(Result["failed"])
        self.assertEqual(Result["total_win"], 0)


if __name__ == "__main__":
    unittest.main()
