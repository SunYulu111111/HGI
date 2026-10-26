"""Verify paid-bet RTP attribution for ordinary and super-free sessions."""

from __future__ import annotations

import csv
import io
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import simulation as Simulation


class SimulationReportingTest(unittest.TestCase):
    @staticmethod
    def base_result(TotalWin, BonusWin, Mode):
        return {
            "total_win": TotalWin,
            "feature_win": BonusWin,
            "cascade_count": 1,
            "is_trigger_feature": BonusWin > 0,
            "is_trigger_free": True,
            "free_times": 1,
            "free_mode": Mode,
        }

    @staticmethod
    def free_result(TotalWin, BonusWin, Retrigger=0):
        return {
            "total_win": TotalWin,
            "feature_win": BonusWin,
            "is_trigger_feature": BonusWin > 0,
            "free_bonus_seen": True,
            "golden_squares": [(0, 0)],
            "retrigger_spins": Retrigger,
        }

    def mixed_mode_result(self):
        Game = Mock()
        Game.base_bet = 100
        Game.ng_spin.side_effect = [
            self.base_result(50, 20, "free"),
            self.base_result(40, 10, "super_free"),
        ]
        Game.fg_spin.side_effect = [
            self.free_result(30, 20, Retrigger=1),
            self.free_result(50, 10),
            self.free_result(100, 80),
        ]
        with patch.object(Simulation, "m", Game):
            Row = Simulation.simulation(spin_times=2, index=0, general_index=1)[-1]
        return Row, Game

    def test_retrigger_stays_in_its_mode_and_rtp_sums_to_legacy_total(self):
        Row, Game = self.mixed_mode_result()
        Normal = Row["status"]["ModeStats"]["Free"]
        Super = Row["status"]["ModeStats"]["SuperFree"]
        self.assertEqual(
            Normal,
            {"SessionCount": 1, "SpinCount": 2, "ClusterWin": 50,
             "BonusWin": 30, "RetriggerCount": 1},
        )
        self.assertEqual(
            Super,
            {"SessionCount": 1, "SpinCount": 1, "ClusterWin": 20,
             "BonusWin": 80, "RetriggerCount": 0},
        )
        self.assertEqual(Row["总押注"], 200)
        self.assertAlmostEqual(Row["NormalFreeClusterRtp"], 0.25)
        self.assertAlmostEqual(Row["NormalFreeBonusRtp"], 0.15)
        self.assertAlmostEqual(Row["SuperFreeClusterRtp"], 0.10)
        self.assertAlmostEqual(Row["SuperFreeBonusRtp"], 0.40)
        self.assertEqual(Row["NormalFreeFrequency"], 0.5)
        self.assertEqual(Row["SuperFreeFrequency"], 0.5)
        self.assertAlmostEqual(Row["NormalFreeRtp"] + Row["SuperFreeRtp"], Row["free_rtp"])
        self.assertAlmostEqual(
            Row["NormalFreeClusterRtp"] + Row["SuperFreeClusterRtp"],
            Row["free_cluster_rtp"],
        )
        self.assertAlmostEqual(
            Row["NormalFreeBonusRtp"] + Row["SuperFreeBonusRtp"],
            Row["free_bonus_rtp"],
        )
        self.assertAlmostEqual(Row["base_rtp"] + Row["free_rtp"], Row["rtp"])
        self.assertAlmostEqual(Row["rtp"], Row["rtp_check"])
        self.assertAlmostEqual(Row["rtp"], 1.35)
        self.assertEqual(Row["FreeSpin"], 3)
        self.assertEqual(Row["Free重触发"], 1)
        self.assertFalse(any(Key.startswith("ModeStats_") for Key in Row))
        self.assertEqual(
            [Call.kwargs["free_mode"] for Call in Game.fg_spin.call_args_list],
            ["free", "free", "super_free"],
        )
        self.assertEqual(Game.fg_spin.call_args_list[2].kwargs["golden_squares"], set())

    def test_no_paid_spins_produces_zero_mode_rates_and_fresh_counters(self):
        Row = Simulation.simulation(spin_times=0, index=0, general_index=1)[-1]
        for Prefix in ("NormalFree", "SuperFree"):
            for Suffix in ("Rtp", "ClusterRtp", "BonusRtp", "Frequency"):
                self.assertEqual(Row[Prefix + Suffix], 0)
        self.assertEqual(Row["rtp"], 0)
        Row["status"]["ModeStats"]["Free"]["SpinCount"] = 99
        self.assertEqual(Simulation.status_handler.new_status()["ModeStats"]["Free"]["SpinCount"], 0)

    def test_csv_extends_old_header_and_summary_exposes_both_modes(self):
        Row, _ = self.mixed_mode_result()
        with TemporaryDirectory() as Directory:
            CsvPath = Path(Directory) / "result.csv"
            CsvPath.write_text("SPIN,rtp,free_rtp\n1,0.1,0.02\n", encoding="utf-8")
            Simulation.append_simulation_results([Row], path=CsvPath)
            with CsvPath.open(encoding="utf-8-sig", newline="") as File:
                Reader = csv.DictReader(File)
                Rows = list(Reader)
            self.assertEqual(Rows[0]["free_rtp"], "0.02")
            self.assertEqual(Rows[0]["NormalFreeRtp"], "")
            self.assertAlmostEqual(float(Rows[1]["NormalFreeRtp"]), 0.4)
            self.assertAlmostEqual(float(Rows[1]["SuperFreeRtp"]), 0.5)
            self.assertIn("free_rtp", Reader.fieldnames)
            self.assertIn("SuperFreeBonusRtp", Reader.fieldnames)
        Output = io.StringIO()
        with redirect_stdout(Output):
            Simulation.print_summary(Row)
        self.assertIn("免费游戏合计 RTP: 0.900", Output.getvalue())
        self.assertIn("普通 Free RTP: 0.400000", Output.getvalue())
        self.assertIn("Super Free RTP: 0.500000", Output.getvalue())


if __name__ == "__main__":
    unittest.main()
