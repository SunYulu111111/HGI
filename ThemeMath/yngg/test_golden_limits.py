"""Golden Feature caps, reveal guarantees, and scripted-result compatibility."""

from __future__ import annotations

import random
import unittest
from unittest.mock import patch

from theme_math import ThemeMath


class GoldenLimitsTest(unittest.TestCase):
    def setUp(self):
        self.Math = ThemeMath()

    @staticmethod
    def _coin(Position, Value=1):
        return {"position": list(Position), "type": "coin", "value": Value}

    @staticmethod
    def _pot(Position):
        return {"position": list(Position), "type": "pot"}

    @staticmethod
    def _clover(Position):
        return {"position": list(Position), "type": "clover", "multiplier": 2}

    @staticmethod
    def _jackpot(Position):
        return {"position": list(Position), "type": "jackpot", "tier": "mini"}

    def _type_options(self):
        self.Math.BONUS_SYMBOL_TYPE_WEIGHTS = (11, 7, 5, 3)
        Options = {}
        for ExcludePot in (False, True):
            for ExcludeClover in (False, True):
                Pairs = [
                    (Kind, Weight)
                    for Kind, Weight in zip(
                        self.Math.BONUS_SYMBOL_TYPES, self.Math.BONUS_SYMBOL_TYPE_WEIGHTS
                    )
                    if not (ExcludePot and Kind == "pot")
                    and not (ExcludeClover and Kind == "clover")
                ]
                Options[tuple(Weight for _, Weight in Pairs)] = [Kind for Kind, _ in Pairs]
        return Options

    def test_published_limits_and_legacy_pot_alias(self):
        self.assertEqual(self.Math.BonusMaxPotCount, 5)
        self.assertEqual(self.Math.BonusMaxCloverCount, 3)
        self.assertEqual(self.Math.BonusRevealMinCoinCount, 1)
        self.assertEqual(self.Math.BONUS_MAX_ROUND, self.Math.BonusMaxPotCount)

    def test_missing_new_fields_use_legacy_pot_limit_and_default_guarantees(self):
        Section = self.Math.game_server_config["Game Info"]
        for Field in ("BonusMaxPotCount", "BonusMaxCloverCount", "BonusRevealMinCoinCount"):
            Section.pop(Field, None)
        Section["bonus_max_round"] = "2"
        self.Math._load_super_scatter_config()
        self.assertEqual(self.Math.BonusMaxPotCount, 2)
        self.assertEqual(self.Math.BONUS_MAX_ROUND, 2)
        self.assertEqual(self.Math.BonusMaxCloverCount, 3)
        self.assertEqual(self.Math.BonusRevealMinCoinCount, 1)

    def test_explicit_limits_override_legacy_values_and_allow_zero(self):
        Section = self.Math.game_server_config["Game Info"]
        Section["bonus_max_round"] = "9"
        for Field in ("BonusMaxPotCount", "BonusMaxCloverCount", "BonusRevealMinCoinCount"):
            Section[Field] = "0"
        self.Math._load_super_scatter_config()
        self.assertEqual(self.Math.BonusMaxPotCount, 0)
        self.assertEqual(self.Math.BONUS_MAX_ROUND, 0)
        self.assertEqual(self.Math.BonusMaxCloverCount, 0)
        self.assertEqual(self.Math.BonusRevealMinCoinCount, 0)

    def test_invalid_limits_fail_when_loaded(self):
        Section = self.Math.game_server_config["Game Info"]
        for Field, Value in (
            ("BonusMaxPotCount", "-1"),
            ("BonusMaxCloverCount", "-1"),
            ("BonusRevealMinCoinCount", "-1"),
            ("BonusRevealMinCoinCount", "31"),
        ):
            Original = Section[Field]
            with self.subTest(Field=Field, Value=Value):
                Section[Field] = Value
                with self.assertRaisesRegex(ValueError, Field):
                    self.Math._load_super_scatter_config()
                Section[Field] = Original

    def test_single_new_cell_forces_coin_and_only_draws_coin_tier(self):
        self.Math.BONUS_SYMBOL_TYPE_WEIGHTS = (0, 0, 0, 1)
        with patch.object(self.Math, "weighted_random_index", return_value=0) as Draw:
            Reveals = self.Math.generate_golden_round({(0, 0)})
        self.assertEqual(Reveals[0]["type"], "coin")
        self.assertEqual(Reveals[0]["value"], self.Math.COIN_VALUES[0])
        Draw.assert_called_once_with(self.Math.COIN_VALUE_WEIGHTS)

    def test_bronze_silver_and_gold_coins_all_satisfy_the_minimum(self):
        for Tier in ("bronze", "silver", "gold"):
            Index = next(
                Index for Index, Value in enumerate(self.Math.COIN_VALUES)
                if self.Math.get_coin_tier(Value) == Tier
            )
            with self.subTest(Tier=Tier), \
                    patch.object(self.Math, "weighted_random_index", return_value=Index) as Draw:
                Reveals = self.Math.generate_golden_round({(0, 0)})
                Result = self.Math.resolve_golden_feature([Reveals], {(0, 0)})
                self.assertEqual(Reveals[0]["coin_tier"], Tier)
                self.assertEqual(Result["total_win"], round(self.Math.COIN_VALUES[Index] * self.Math.base_bet))
                Draw.assert_called_once_with(self.Math.COIN_VALUE_WEIGHTS)

    def test_larger_minimum_forces_the_last_required_coins_without_type_draws(self):
        self.Math.BonusRevealMinCoinCount = 2
        with patch.object(self.Math, "weighted_random_index", side_effect=[3, 0, 0, 0]) as Draw:
            Reveals = self.Math.generate_golden_round({(0, 0), (1, 0), (2, 0)})
        self.assertEqual([Cell["type"] for Cell in Reveals], ["jackpot", "coin", "coin"])
        self.assertEqual(
            [Call.args[0] for Call in Draw.call_args_list],
            [self.Math.BONUS_SYMBOL_TYPE_WEIGHTS, self.Math.JACKPOT_TYPE_WEIGHTS,
             self.Math.COIN_VALUE_WEIGHTS, self.Math.COIN_VALUE_WEIGHTS],
        )

    def test_batch_smaller_than_minimum_fails_before_drawing(self):
        self.Math.BonusRevealMinCoinCount = 2
        with patch.object(self.Math, "weighted_random_index") as Draw:
            for Generate in (self.Math.generate_golden_round, self.Math.generate_golden_rounds):
                with self.subTest(Method=Generate.__name__), \
                        self.assertRaisesRegex(ValueError, "BonusRevealMinCoinCount"):
                    Generate({(0, 0)})
            Draw.assert_not_called()

    def test_type_weights_exclude_capped_types_and_preserve_remaining_ratios(self):
        self.Math.BonusMaxPotCount = 1
        self.Math.BonusMaxCloverCount = 1
        Options = self._type_options()
        Seen = []

        def Draw(Weights):
            Weights = tuple(Weights)
            if Weights in Options:
                Seen.append(Weights)
                Kinds = Options[Weights]
                Kind = next(Kind for Kind in ("pot", "clover", "jackpot") if Kind in Kinds)
                return Kinds.index(Kind)
            return 0

        with patch.object(self.Math, "weighted_random_index", side_effect=Draw):
            Reveals = self.Math.generate_golden_round({(Index, 0) for Index in range(5)})
        self.assertEqual([Cell["type"] for Cell in Reveals], ["pot", "clover", "jackpot", "jackpot", "coin"])
        self.assertEqual(Seen, [(11, 7, 5, 3), (11, 7, 3), (11, 3), (11, 3)])

    def test_feature_wide_caps_apply_to_every_reroll(self):
        Options = self._type_options()

        def Draw(Weights):
            Kinds = Options.get(tuple(Weights))
            if Kinds is None:
                return 0
            Kind = next(Kind for Kind in ("pot", "clover", "jackpot") if Kind in Kinds)
            return Kinds.index(Kind)

        Positions = {(Column, Row) for Row in range(2) for Column in range(5)}
        with patch.object(self.Math, "weighted_random_index", side_effect=Draw):
            Rounds = self.Math.generate_golden_rounds(Positions)
        self.assertEqual(len(Rounds), 2)
        self.assertEqual(sum(Cell["type"] == "pot" for Batch in Rounds for Cell in Batch), 5)
        self.assertEqual(sum(Cell["type"] == "clover" for Batch in Rounds for Cell in Batch), 3)
        self.assertTrue(all(any(Cell["type"] == "coin" for Cell in Batch) for Batch in Rounds))
        Result = self.Math.resolve_golden_feature(Rounds, Positions)
        self.assertEqual(Result["pot_count"], 5)

    def test_clover_count_survives_replacement_and_multiple_pot_rerolls(self):
        Options = self._type_options()
        Script = iter(("clover", "pot", "jackpot", "jackpot", "clover", "pot", "jackpot", "clover", "pot", "pot"))
        Seen = []

        def Draw(Weights):
            Weights = tuple(Weights)
            Kinds = Options.get(Weights)
            if Kinds is None:
                return 0
            Seen.append(Weights)
            return Kinds.index(next(Script))

        Positions = {(Index, 0) for Index in range(5)}
        with patch.object(self.Math, "weighted_random_index", side_effect=Draw):
            Rounds = self.Math.generate_golden_rounds(Positions)
        self.assertEqual(len(Rounds), 5)
        self.assertEqual(sum(Cell["type"] == "clover" for Batch in Rounds for Cell in Batch), 3)
        self.assertEqual(Seen[-2:], [(11, 5, 3), (11, 5, 3)])
        Result = self.Math.resolve_golden_feature(Rounds, Positions)
        self.assertEqual(Result["pot_count"], 4)
        self.assertEqual(sum(Event["type"] == "Clover" for Event in Result["events"]), 3)

    def test_existing_counts_exclude_types_before_the_next_batch(self):
        self._type_options()
        with patch.object(self.Math, "weighted_random_index", side_effect=[1, 0, 1, 0, 0]) as Draw:
            Reveals = self.Math.generate_golden_round(
                {(0, 0), (1, 0), (2, 0)}, existing_pot_count=5, ExistingCloverCount=3,
            )
        self.assertEqual([Cell["type"] for Cell in Reveals], ["jackpot", "jackpot", "coin"])
        self.assertEqual([Call.args[0] for Call in Draw.call_args_list][::2], [(11, 3), (11, 3), self.Math.COIN_VALUE_WEIGHTS])

    def test_zero_eligible_type_weights_force_coin_when_guarantee_is_enabled(self):
        self.Math.BonusMaxPotCount = 0
        self.Math.BonusMaxCloverCount = 0
        self.Math.BONUS_SYMBOL_TYPE_WEIGHTS = (0, 1, 1, 0)
        with patch.object(self.Math, "weighted_random_index", return_value=0) as Draw:
            Reveals = self.Math.generate_golden_round({(0, 0), (1, 0), (2, 0)})
        self.assertEqual([Cell["type"] for Cell in Reveals], ["coin"] * 3)
        self.assertEqual([Call.args[0] for Call in Draw.call_args_list], [self.Math.COIN_VALUE_WEIGHTS] * 3)
        self.Math.BonusRevealMinCoinCount = 0
        with self.assertRaisesRegex(ValueError, "weights total"):
            self.Math.generate_golden_round({(0, 0)})

    def test_injected_caps_accept_boundary_counts_across_batches(self):
        Rounds = [
            [self._pot((0, 0)), self._pot((1, 0)), self._clover((0, 1)), self._coin((5, 1))],
            [self._pot((2, 0)), self._pot((3, 0)), self._clover((0, 1)), self._coin((5, 1))],
            [self._pot((4, 0)), self._clover((0, 1)), self._coin((5, 1))],
            [self._coin((5, 1))],
        ]
        Result = self.Math.resolve_golden_feature(Rounds)
        self.assertEqual(Result["pot_count"], 5)
        self.assertEqual(sum(Event["type"] == "Clover" for Event in Result["events"]), 3)
        self.assertEqual(sum(Event["type"] == "Collect" for Event in Result["events"]), 5)

    def test_injected_pot_limit_accumulates_across_batches(self):
        Rounds = [
            [self._pot((Index, 0)) for Index in range(3)] + [self._coin((5, 1))],
            [self._pot((Index, 0)) for Index in range(3, 6)] + [self._coin((5, 1))],
        ]
        with self.assertRaisesRegex(ValueError, "pot limit=5"):
            self.Math.resolve_golden_feature(Rounds)

    def test_injected_clover_limit_counts_repeated_replacements_across_batches(self):
        Rounds = [
            [self._clover((0, 0)), self._pot((Index, 1)), self._coin((1, 0))]
            for Index in range(3)
        ] + [[self._clover((0, 0)), self._coin((1, 0))]]
        with self.assertRaisesRegex(ValueError, "clover limit=3"):
            self.Math.resolve_golden_feature(Rounds)

    def test_old_coin_or_retained_pot_does_not_satisfy_a_new_batch(self):
        First = [self._coin((0, 0)), self._pot((1, 0))]
        for Second in ([self._clover((0, 0))], [self._jackpot((2, 0))]):
            with self.subTest(Second=Second), self.assertRaisesRegex(ValueError, "coin"):
                self.Math.resolve_golden_feature([First, Second])
        with self.assertRaisesRegex(ValueError, "coin"):
            self.Math.resolve_golden_feature([[self._jackpot((0, 0))]])

    def test_injected_guarantee_counts_unique_new_coin_positions(self):
        self.Math.BonusRevealMinCoinCount = 2
        with self.assertRaisesRegex(ValueError, "duplicate golden reveal position"):
            self.Math.resolve_golden_feature([[self._coin((0, 0)), self._coin((0, 0))]])
        with self.assertRaisesRegex(ValueError, "coin"):
            self.Math.resolve_golden_feature([[self._coin((0, 0)), self._jackpot((1, 0))]])
        Result = self.Math.resolve_golden_feature([[self._coin((0, 0)), self._coin((1, 0))]])
        self.assertEqual(Result["total_win"], 2 * self.Math.base_bet)

    def test_partial_script_with_coin_remains_valid_without_full_grid_coverage(self):
        Result = self.Math.resolve_golden_feature(
            [[self._pot((0, 0)), self._coin((1, 0))], [self._coin((1, 0), 5)]],
            golden_squares={(0, 0), (1, 0), (2, 0)},
        )
        self.assertEqual(Result["pot_count"], 1)
        self.assertEqual(Result["total_multiple"], 6)
        self.assertEqual(len(Result["cells"]), 2)

    def test_known_golden_area_requires_a_batch_unless_guarantee_is_disabled(self):
        with self.assertRaisesRegex(ValueError, "coin"):
            self.Math.resolve_golden_feature([], {(0, 0)})
        self.Math.BonusRevealMinCoinCount = 0
        self.assertEqual(self.Math.resolve_golden_feature([], {(0, 0)})["total_win"], 0)
        self.assertEqual(self.Math.resolve_golden_feature([[self._jackpot((0, 0))]])["total_win"], 10 * self.Math.base_bet)
        self.assertEqual(self.Math.generate_golden_rounds(set()), [])

    def test_seeded_generated_features_obey_limits_for_every_type(self):
        Positions = {(Column, Row) for Row in range(5) for Column in range(6)}
        for TypeIndex in self.Math.ConfiguredTypes:
            self.Math._activate_type(TypeIndex)
            for Seed in (20261023, 20261024, 20261025):
                Generator = random.Random(Seed)
                with self.subTest(TypeIndex=TypeIndex, Seed=Seed), \
                        patch("theme_math.random.randrange", side_effect=Generator.randrange):
                    Rounds = self.Math.generate_golden_rounds(Positions)
                self.assertLessEqual(sum(Cell["type"] == "pot" for Batch in Rounds for Cell in Batch), 5)
                self.assertLessEqual(sum(Cell["type"] == "clover" for Batch in Rounds for Cell in Batch), 3)
                self.assertTrue(all(any(Cell["type"] == "coin" for Cell in Batch) for Batch in Rounds))
                self.Math.resolve_golden_feature(Rounds, Positions)


if __name__ == "__main__":
    unittest.main()
