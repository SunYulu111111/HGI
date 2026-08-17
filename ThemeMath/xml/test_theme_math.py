"""水果机数学逻辑的确定性测试。"""

from __future__ import annotations

import csv
import unittest
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from simulation import (
    append_simulation_results,
    build_symbol_bets,
    parse_bet_multis,
    simulation,
    simulation_all,
    simulate,
)
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
        self.assertEqual(self.math.high_symbol_weights, [40, 30, 20])
        self.assertEqual(self.math.mid_symbol_weights, [20, 15, 10])
        self.assertEqual(self.math.symbol_multi_weights, [100, 100, 100])
        self.assertEqual(
            self.math.respin_count_weights,
            [0, 0, 100, 100, 100, 100, 100, 100],
        )
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

    def test_normal_spin_uses_configured_multiplier_as_x(self):
        self.force_trigger_index(14)  # symbol 3, multiplier 3

        result = self.math.spin({3: 100_000})

        self.assertEqual(result["trigger_index"], 14)
        self.assertEqual(result["trigger_symbol_id"], 3)
        self.assertFalse(result["is_bonus"])
        self.assertEqual(result["total_bet"], 100_000)
        self.assertEqual(result["total_win"], 300_000)
        self.assertEqual(result["win_items"][0]["item_prize"], 100_000)
        self.assertEqual(result["win_items"][0]["multi_config"], 3)
        self.assertEqual(result["win_items"][0]["x"], 3)
        self.assertEqual(result["win_items"][0]["multiplier"], 3)

    def test_symbol_two_high_multiplier_formula(self):
        self.force_trigger_index(2)  # symbol 2, multiplier 50

        result = self.math.spin({2: 100_000})

        self.assertEqual(result["total_win"], 5_000_000)

    def test_multi_config_one_uses_symbol_multiplier_rules(self):
        cases = (
            (15, {3: 100_000}, 40, 0, 4_000_000),
            (1, {6: 300_000}, 20, 0, 6_000_000),
            (4, {9: 200_000}, 5, None, 1_000_000),
        )
        for trigger_index, bets, expected_x, expected_index, expected_win in cases:
            with self.subTest(trigger_index=trigger_index):
                self.force_trigger_index(trigger_index)
                result = self.math.spin(bets)
                outcome = result["outcomes"][0]
                self.assertEqual(outcome["multi_config"], 1)
                self.assertEqual(outcome["x"], expected_x)
                self.assertEqual(outcome["symbol_multi_index"], expected_index)
                self.assertEqual(result["total_win"], expected_win)

    def test_high_and_mid_symbols_share_one_multi_index_per_spin(self):
        self.force_trigger_index(9)
        self.math.symbol_multi_weights = [0, 0, 1]
        self.math.respin_count_weights = [0] * 7 + [1]

        result = self.math.spin(
            {symbol_id: 100_000 for symbol_id in range(2, 10)}
        )

        dynamic_outcomes = [
            outcome
            for outcome in result["outcomes"]
            if outcome["multi_config"] == 1
            and outcome["symbol_id"] in (3, 4, 5, 6, 7, 8)
        ]
        self.assertEqual(result["symbol_multi_index"], 2)
        self.assertEqual(
            {outcome["symbol_multi_index"] for outcome in dynamic_outcomes},
            {2},
        )
        self.assertEqual(
            {
                outcome["x"]
                for outcome in dynamic_outcomes
                if outcome["symbol_id"] in (3, 4, 5)
            },
            {20},
        )
        self.assertEqual(
            {
                outcome["x"]
                for outcome in dynamic_outcomes
                if outcome["symbol_id"] in (6, 7, 8)
            },
            {10},
        )

    def test_unselected_winning_symbol_does_not_pay(self):
        self.force_trigger_index(14)  # symbol 3

        result = self.math.spin({2: 100_000})

        self.assertEqual(result["total_win"], 0)
        self.assertEqual(result["win_items"], [])
        self.assertEqual(result["outcomes"][0]["symbol_id"], 3)

    def test_bonus_respin_count_uses_configured_minimum_and_maximum(self):
        self.force_trigger_index(9)  # symbol 0

        minimum_result = self.math.spin(
            {symbol_id: 100_000 for symbol_id in range(2, 10)}
        )
        self.math.respin_count_weights = [0] * 7 + [1]
        maximum_result = self.math.spin(
            {symbol_id: 100_000 for symbol_id in range(2, 10)}
        )

        self.assertTrue(minimum_result["is_bonus"])
        self.assertEqual(minimum_result["respin_count"], 3)
        self.assertEqual(len(minimum_result["winning_indexes"]), 3)
        self.assertEqual(maximum_result["respin_count"], 8)
        self.assertEqual(len(maximum_result["winning_indexes"]), 8)
        self.assertEqual(len(set(maximum_result["winning_indexes"])), 8)
        self.assertNotIn(9, maximum_result["winning_indexes"])
        self.assertNotIn(21, maximum_result["winning_indexes"])

    def test_each_symbol_has_point_seven_rtp_without_bonus(self):
        total_weight = sum(self.math.win_weights)
        self.assertEqual(total_weight, 1_500)
        self.assertEqual(self.math.win_weights[9], 0)
        self.assertEqual(self.math.win_weights[21], 0)
        high_expected_x = Fraction(
            sum(
                weight * value
                for weight, value in zip(
                    self.math.symbol_multi_weights,
                    self.math.high_symbol_weights,
                )
            ),
            sum(self.math.symbol_multi_weights),
        )
        mid_expected_x = Fraction(
            sum(
                weight * value
                for weight, value in zip(
                    self.math.symbol_multi_weights,
                    self.math.mid_symbol_weights,
                )
            ),
            sum(self.math.symbol_multi_weights),
        )

        for symbol_id in range(2, 10):
            weighted_win = Fraction(0)
            for index, reel_symbol_id in enumerate(self.math.reel_config):
                if reel_symbol_id != symbol_id:
                    continue
                configured_x = self.math.multi_config[index]
                if configured_x != 1:
                    expected_x = Fraction(configured_x)
                elif symbol_id in (3, 4, 5):
                    expected_x = high_expected_x
                elif symbol_id in (6, 7, 8):
                    expected_x = mid_expected_x
                else:
                    expected_x = Fraction(5)
                weighted_win += (
                    self.math.win_weights[index]
                    * self.math.item_prizes[symbol_id]
                    * expected_x
                )
            with self.subTest(symbol_id=symbol_id):
                self.assertEqual(
                    weighted_win
                    / (total_weight * self.math.base_bet),
                    Fraction(7, 10),
                )

    def test_bonus_repeated_symbol_indexes_pay_independently(self):
        self.force_trigger_index(9)
        self.math.respin_count_weights = [0] * 7 + [1]
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
        self.assertEqual(symbol_two_wins, [5_000_000, 10_000_000])
        self.assertEqual(result["total_win"], 15_000_000)

    def test_multiple_symbol_bets_have_independent_amounts(self):
        self.force_trigger_index(1)  # symbol 6, multiplier 1

        result = self.math.spin({2: 100_000, 6: 300_000, 9: 200_000})

        self.assertEqual(result["total_bet"], 600_000)
        self.assertEqual(result["total_win"], 6_000_000)

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

        self.assertEqual(result["base_win"], 300_000)
        self.assertEqual(result["double_result"]["attempted_times"], 2)
        self.assertEqual(
            result["double_result"]["double_weight_key"],
            "DoubleWeight_5",
        )
        self.assertEqual(result["total_win"], 1_200_000)

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

    def test_simulation_returns_rzcs_style_checkpoint_rows(self):
        bet_multi = [0, 0, 1, 2, 0, 0, 0, 0, 0, 0]

        rows = simulation(
            spin_times=5,
            bet_multi=bet_multi,
            double_times=0,
            seed=7,
            report_interval=2,
        )

        self.assertEqual([row["SPIN"] for row in rows], [2, 4, 5])
        self.assertEqual(rows[-1]["BET_MULTI"], bet_multi)
        self.assertEqual(rows[-1]["DOUBLE_TIMES"], 0)
        self.assertEqual(rows[-1]["总押注"], 1_500_000)
        self.assertEqual(rows[-1]["rtp"], rows[-1]["rtp_check"])
        self.assertIn("status", rows[-1])
        self.assertEqual(rows[-1]["symbol_2_bet"], 500_000)
        self.assertEqual(rows[-1]["symbol_3_bet"], 1_000_000)

    def test_simulation_all_runs_parameter_combinations(self):
        bet_multi = [0, 0, 1, 1, 0, 0, 0, 0, 0, 0]

        rows = simulation_all(
            spin_times=2,
            bet_multis=[bet_multi],
            double_times_values=[0, 1],
            seeds=[7, 8],
            report_interval=0,
            print_updates=False,
        )

        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["ok"] for row in rows))
        self.assertEqual({row["DOUBLE_TIMES"] for row in rows}, {0, 1})
        self.assertEqual({row["SEED"] for row in rows}, {7, 8})

    def test_simulation_results_append_to_csv(self):
        row = simulate(
            3,
            bet_multi=[0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
            seed=7,
        )
        row["ok"] = True

        with TemporaryDirectory() as directory:
            path = Path(directory) / "simulate_result.csv"
            append_simulation_results([row], path=path)
            with path.open("r", newline="", encoding="utf-8-sig") as file_obj:
                rows = list(csv.DictReader(file_obj))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["SPIN"], "3")
        self.assertEqual(rows[0]["BET_MULTI"], "[0, 0, 1, 1, 0, 0, 0, 0, 0, 0]")

    def test_parse_multiple_bet_multi_groups(self):
        self.assertEqual(
            parse_bet_multis("0,0,1,0,0,0,0,0,0,0;0,0,0,2,0,0,0,0,0,0"),
            [
                [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 2, 0, 0, 0, 0, 0, 0],
            ],
        )


if __name__ == "__main__":
    unittest.main()
