"""水果机数学逻辑的确定性测试。"""

from __future__ import annotations

import unittest
from fractions import Fraction

from simulation import build_symbol_bets, simulate
from theme_math import ThemeMath


class FirstChoiceRandom:
    """总是命中当前正权重候选中的第一个。"""

    @staticmethod
    def randrange(stop: int) -> int:
        if stop <= 0:
            raise ValueError("stop must be positive")
        return 0


class LastChoiceRandom:
    """命中最后一个权重区间，用于强制翻倍成功。"""

    @staticmethod
    def randrange(stop: int) -> int:
        if stop <= 0:
            raise ValueError("stop must be positive")
        return stop - 1


class CountingLastChoiceRandom:
    def __init__(self):
        self.calls = 0

    def randrange(self, stop: int) -> int:
        self.calls += 1
        return stop - 1


class ThemeMathTest(unittest.TestCase):
    def setUp(self):
        self.math = ThemeMath(rng=FirstChoiceRandom())

    def force_trigger_index(self, index: int) -> None:
        self.math.win_weights = [0] * len(self.math.win_weights)
        self.math.win_weights[index] = 1

    def test_configuration_matches_fruit_machine_symbols(self):
        self.assertEqual(self.math.base_bet, 100_000)
        self.assertEqual(self.math.item_count, 10)
        self.assertEqual(set(self.math.item_prizes), set(range(2, 10)))
        self.assertEqual(
            len(self.math.reel_config),
            len(self.math.multi_config),
        )
        self.assertTrue(self.math.double_enabled)
        self.assertEqual(self.math.double_max_times, 10)
        self.assertEqual(self.math.double_multiple, 2)
        self.assertEqual(
            self.math.double_weights,
            [1000, 512, 256, 128, 64, 32, 16, 8, 4, 2, 1],
        )
        self.assertEqual(
            list(self.math.double_weight_tiers),
            [1, 5, 10, 25, 50, 100],
        )
        for section in ("0", "4", "8", "12", "17"):
            self.assertTrue(self.math.game_server_config.has_section(section))
            self.assertEqual(
                self.math.game_server_config[section]["DoubleWeight"],
                "1000,512,256,128,64,32,16,8,4,2,1",
            )
            for threshold in (1, 5, 10, 25, 50, 100):
                self.assertEqual(
                    self.math.game_server_config[section][
                        f"DoubleWeight_{threshold}"
                    ],
                    "1000,512,256,128,64,32,16,8,4,2,1",
                )

    def test_normal_spin_uses_index_symbol_prize_and_multiplier(self):
        self.force_trigger_index(14)  # symbol 3, multiplier 3

        result = self.math.spin({3: 100_000})

        self.assertEqual(result["trigger_index"], 14)
        self.assertEqual(result["trigger_symbol_id"], 3)
        self.assertFalse(result["is_bonus"])
        self.assertEqual(result["total_bet"], 100_000)
        self.assertEqual(result["total_win"], 2_400_000)
        self.assertEqual(result["win_items"][0]["item_prize"], 800_000)
        self.assertEqual(result["win_items"][0]["multiplier"], 3)

    def test_symbol_two_high_multiplier_formula(self):
        self.force_trigger_index(2)  # symbol 2, multiplier 50

        result = self.math.spin({2: 100_000})

        self.assertEqual(result["total_win"], 100_000_000)

    def test_unselected_winning_symbol_does_not_pay(self):
        self.force_trigger_index(14)  # symbol 3

        result = self.math.spin({2: 100_000})

        self.assertEqual(result["total_win"], 0)
        self.assertEqual(result["win_items"], [])
        self.assertEqual(result["outcomes"][0]["symbol_id"], 3)

    def test_bonus_selects_eight_distinct_indexes(self):
        self.force_trigger_index(9)  # symbol 0

        result = self.math.spin({symbol_id: 100_000 for symbol_id in range(2, 10)})

        self.assertTrue(result["is_bonus"])
        self.assertEqual(len(result["winning_indexes"]), 8)
        self.assertEqual(len(set(result["winning_indexes"])), 8)
        self.assertNotIn(9, result["winning_indexes"])
        self.assertNotIn(21, result["winning_indexes"])

    def test_each_symbol_and_all_symbols_have_exact_point_seven_rtp(self):
        total_weight = sum(self.math.win_weights)
        self.assertEqual(total_weight, 30_000)
        self.assertEqual(self.math.win_weights[9], 0)
        self.assertEqual(self.math.win_weights[21], 0)

        for symbol_id in range(2, 10):
            bets = {symbol_id: self.math.base_bet}
            weighted_win = sum(
                weight * self.math._settle_index(index, bets)["win"]
                for index, weight in enumerate(self.math.win_weights)
            )
            with self.subTest(symbol_id=symbol_id):
                self.assertEqual(
                    Fraction(weighted_win, total_weight * self.math.base_bet),
                    Fraction(7, 10),
                )

        bets = {symbol_id: self.math.base_bet for symbol_id in range(2, 10)}
        weighted_win = sum(
            weight * self.math._settle_index(index, bets)["win"]
            for index, weight in enumerate(self.math.win_weights)
        )
        self.assertEqual(
            Fraction(weighted_win, total_weight * sum(bets.values())),
            Fraction(7, 10),
        )

    def test_bonus_repeated_symbol_indexes_pay_independently(self):
        self.force_trigger_index(9)
        self.math.bonus_win_weights = [0] * len(self.math.bonus_win_weights)
        for index in range(8):
            self.math.bonus_win_weights[index] = 1

        result = self.math.spin({2: 100_000})

        self.assertEqual(result["winning_indexes"], list(range(8)))
        symbol_two_wins = [
            outcome["win"]
            for outcome in result["outcomes"]
            if outcome["symbol_id"] == 2
        ]
        self.assertEqual(symbol_two_wins, [100_000_000, 200_000_000])
        self.assertEqual(result["total_win"], 300_000_000)

    def test_multiple_symbol_bets_have_independent_amounts(self):
        self.force_trigger_index(1)  # symbol 6, multiplier 1

        result = self.math.spin({2: 100_000, 6: 300_000, 9: 200_000})

        self.assertEqual(result["total_bet"], 600_000)
        self.assertEqual(result["total_win"], 1_200_000)

    def test_invalid_bets_are_rejected(self):
        invalid_bets = (
            {},
            {1: 100_000},
            {10: 100_000},
            {2: 0},
            {2: -100_000},
            {2: 10_000},
            {2: 150_000},
        )
        for bets in invalid_bets:
            with self.subTest(bets=bets), self.assertRaises(ValueError):
                self.math.spin(bets)

        with self.assertRaises(TypeError):
            self.math.spin({"2": 100_000})
        with self.assertRaises(TypeError):
            self.math.spin({2: 100_000.0})
        with self.assertRaises(TypeError):
            self.math.spin([(2, 100_000)])

    def test_bonus_requires_eight_positive_weight_indexes(self):
        with self.assertRaises(ValueError):
            self.math._weighted_sample_without_replacement([1, 1, 1], 8)

    def test_double_success_doubles_win_and_can_continue(self):
        math = ThemeMath(rng=LastChoiceRandom())

        result = math.double_win(2_400_000)

        self.assertTrue(result["success"])
        self.assertEqual(result["total_win"], 4_800_000)
        self.assertTrue(result["can_double"])

    def test_double_failure_resets_win_to_zero(self):
        result = self.math.double_win(2_400_000)

        self.assertFalse(result["success"])
        self.assertEqual(result["selected_times"], 0)
        self.assertEqual(result["total_win"], 0)
        self.assertFalse(result["can_double"])

    def test_double_can_succeed_at_most_ten_times(self):
        math = ThemeMath(rng=LastChoiceRandom())

        result = math.apply_double_up(100_000, double_times=10)

        self.assertEqual(result["attempted_times"], 10)
        self.assertEqual(result["selected_times"], 10)
        self.assertEqual(result["success_times"], 10)
        self.assertEqual(result["total_win"], 102_400_000)
        self.assertFalse(result["can_double"])
        with self.assertRaises(ValueError):
            math.double_win(result["total_win"], completed_times=10)

    def test_double_weight_is_selected_once_per_win(self):
        rng = CountingLastChoiceRandom()
        math = ThemeMath(rng=rng)

        result = math.apply_double_up(100_000, double_times=10)

        self.assertEqual(rng.calls, 1)
        self.assertEqual(result["selected_times"], 10)
        self.assertEqual(result["success_times"], 10)

    def test_double_weight_tier_follows_initial_win_multiple(self):
        total_bet = 100_000
        cases = (
            (50_000, "DoubleWeight_1"),
            (100_000, "DoubleWeight_1"),
            (100_001, "DoubleWeight_5"),
            (500_000, "DoubleWeight_5"),
            (500_001, "DoubleWeight_10"),
            (1_000_001, "DoubleWeight_25"),
            (2_500_001, "DoubleWeight_50"),
            (5_000_001, "DoubleWeight_100"),
            (10_000_000, "DoubleWeight_100"),
            (10_000_001, "DoubleWeight"),
        )
        for win_amount, expected_key in cases:
            with self.subTest(win_amount=win_amount):
                key, _ = self.math.get_double_weight_config(win_amount, total_bet)
                self.assertEqual(key, expected_key)

    def test_attempt_beyond_selected_double_times_fails(self):
        self.math.double_weight_tiers[1] = [0] * 11
        self.math.double_weight_tiers[1][2] = 1

        result = self.math.apply_double_up(100_000, double_times=3)

        self.assertEqual(result["selected_times"], 2)
        self.assertEqual(result["success_times"], 2)
        self.assertEqual(result["attempted_times"], 3)
        self.assertTrue(result["failed"])
        self.assertEqual(result["total_win"], 0)

    def test_spin_applies_requested_double_choices(self):
        math = ThemeMath(rng=LastChoiceRandom())
        math.win_weights = [0] * len(math.win_weights)
        math.win_weights[14] = 1  # symbol 3, multiplier 3

        result = math.spin({3: 100_000}, double_times=2)

        self.assertEqual(result["base_win"], 2_400_000)
        self.assertEqual(result["double_result"]["attempted_times"], 2)
        self.assertEqual(
            result["double_result"]["double_weight_key"],
            "DoubleWeight_25",
        )
        self.assertEqual(result["total_win"], 9_600_000)

    def test_double_is_not_attempted_without_a_win(self):
        self.force_trigger_index(14)  # symbol 3，玩家只押symbol 2

        result = self.math.spin({2: 100_000}, double_times=10)

        self.assertEqual(result["base_win"], 0)
        self.assertEqual(result["double_result"]["attempted_times"], 0)
        self.assertEqual(result["total_win"], 0)

    def test_invalid_double_requests_are_rejected(self):
        with self.assertRaises(ValueError):
            self.math.apply_double_up(100_000, double_times=11)
        with self.assertRaises(ValueError):
            self.math.double_win(0)
        with self.assertRaises(TypeError):
            self.math.apply_double_up(100_000, double_times=True)


class SimulationBetMultiTest(unittest.TestCase):
    def setUp(self):
        self.math = ThemeMath(rng=FirstChoiceRandom())

    def test_bet_multi_maps_symbol_ids_to_base_bet_multiples(self):
        bet_multi = [0, 0, 1, 2, 0, 3, 0, 0, 4, 0]

        bets = build_symbol_bets(self.math, bet_multi)

        self.assertEqual(
            bets,
            {
                2: 100_000,
                3: 200_000,
                5: 300_000,
                8: 400_000,
            },
        )

    def test_simulation_uses_bet_multi_for_total_bet(self):
        bet_multi = [0, 0, 1, 2, 0, 0, 0, 0, 0, 0]

        result = simulate(3, bet_multi=bet_multi, seed=7)

        self.assertEqual(result["bet_multi"], bet_multi)
        self.assertEqual(result["bets"], {2: 100_000, 3: 200_000})
        self.assertEqual(result["total_bet"], 900_000)

    def test_invalid_bet_multi_is_rejected(self):
        invalid_values = (
            [0] * 9,
            [1, 0, 1, 1, 1, 1, 1, 1, 1, 1],
            [0, 0, 1, -1, 1, 1, 1, 1, 1, 1],
            [0] * 10,
        )
        for bet_multi in invalid_values:
            with self.subTest(bet_multi=bet_multi), self.assertRaises(ValueError):
                build_symbol_bets(self.math, bet_multi)


if __name__ == "__main__":
    unittest.main()
