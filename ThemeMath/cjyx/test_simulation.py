"""验证超级英雄沿用 Lines 模板的统计、配置选择和报表输出。"""

from configparser import ConfigParser
from contextlib import redirect_stderr, redirect_stdout
import csv
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from . import simulation
    from .theme_math import ThemeMath
except ImportError:
    import simulation
    from theme_math import ThemeMath

from slots_math import LinesGame
from slots_simulation import simulation as SlotsSimulation


ProjectDir = Path(__file__).resolve().parent


def spin_result(Mode="Main", Win=0, Awarded=0, Remaining=0, NextMode="Main", **Overrides):
    Result = {
        "total_win": Win, "line_win": Win, "win_items": [], "win_positions": [],
        "win_free": Awarded > 0, "item_list": [], "free_game": Mode != "Main",
        "Mode": Mode, "NextMode": NextMode, "AwardedFreeSpins": Awarded,
        "FreeSpinsRemaining": Remaining, "Upgraded": False, "UltimateHit": False,
        "ScatterCount": 0, "spin_info": {
            "index": 0, "general_index": 1, "requested_general_index": 1,
            "general_index_fallback": False, "reel_config_index_fallback": False,
            "reel_config_file": "cjyx_rand_ex_0.conf" if Mode == "Main" else "cjyx_free_rand_ex_0.conf",
        },
    }
    Result.update(Overrides)
    return Result


class ScriptedGame:
    """按固定旋转序列模拟主题会话，记录模板入参。"""

    def __init__(self, Spins, BaseBet=100000):
        self.Spins = iter(Spins)
        self.base_bet = BaseBet
        self.FreeSpinsRemaining = 0
        self.Calls = []

    def _next(self, ModeKey, index, general_index, return_detail):
        self.Calls.append((ModeKey, index, general_index, return_detail))
        Result = next(self.Spins)
        self.FreeSpinsRemaining = Result["FreeSpinsRemaining"]
        return Result

    def ng_spin(self, index, general_index, return_detail):
        return self._next("Main", index, general_index, return_detail)

    def fg_spin(self, index, general_index, return_detail):
        return self._next("Free", index, general_index, return_detail)


class SimulationTests(unittest.TestCase):
    def test_template_inheritance_status_and_three_mode_general_discovery(self):
        self.assertTrue(issubclass(ThemeMath, LinesGame))
        self.assertIsInstance(simulation.status_handler, SlotsSimulation)
        for Mode in ("base", "free"):
            self.assertEqual(simulation.status_model[Mode], {"spin": 0, "lines": [0, 0], "free": 0})
        self.assertEqual(simulation.discover_general_indexes(), [1])
        self.assertEqual(simulation.discover_general_indexes(free_game=True), [1])
        self.assertEqual(simulation.discover_general_indexes(SuperFree=True), [1])

    def test_per_spin_shared_statistics_include_upgrade_retrigger_and_ultimate(self):
        Spins = [
            spin_result(Win=100000, Awarded=2, Remaining=2, NextMode="Free"),
            spin_result("Free", Win=200000, Awarded=2, Remaining=3, NextMode="SuperFree", Upgraded=True, ScatterCount=4),
            spin_result("SuperFree", Win=300000, Awarded=4, Remaining=6, NextMode="SuperFree", ScatterCount=3, UltimateHit=True),
            *(spin_result("SuperFree", Remaining=Remaining, NextMode="SuperFree" if Remaining else "Main") for Remaining in range(5, -1, -1)),
            spin_result(Win=1000000),
        ]
        Game = ScriptedGame(Spins)
        SharedUpdate = simulation.status_handler.update_feature_win
        with patch.object(simulation, "ThemeMath", return_value=Game) as Factory, patch.object(simulation.status_handler, "update_feature_win", wraps=SharedUpdate) as Update:
            Rows = simulation.simulation(2, index=4, general_index=7, free_general_index=8, report_interval=1, Seed=37)
        Factory.assert_called_once_with(base_bet=100000, Seed=37)
        self.assertEqual(Update.call_count, 10)
        self.assertEqual(Game.Calls[0], ("Main", 4, 7, True))
        self.assertTrue(all(Call == ("Free", 4, 8, True) for Call in Game.Calls[1:9]))
        self.assertEqual(Game.Calls[-1], ("Main", 4, 7, True))
        self.assertEqual([Row["SPIN"] for Row in Rows], [1, 2])
        Summary = Rows[-1]
        self.assertEqual((Summary["PaidSpins"], Summary["TotalSpins"], Summary["Bet"]), (2, 10, 200000))
        self.assertEqual((Summary["MainWin"], Summary["FreeWin"], Summary["SuperFreeWin"]), (1100000, 200000, 300000))
        self.assertEqual((Summary["BaseLine"], Summary["FreeLine"], Summary["总赢钱"], Summary["Line赢钱"]), (1100000, 500000, 1600000, 1600000))
        self.assertEqual((Summary["Free次数"], Summary["FreeSpin"], Summary["FreeSpinsAwarded"]), (8, 8, 8))
        self.assertEqual((Summary["NormalFreeSpins"], Summary["SuperFreeSpins"]), (1, 7))
        self.assertEqual((Summary["触发Free"], Summary["Free重触发"], Summary["Upgrades"]), (1, 1, 1))
        self.assertEqual((Summary["FreeTriggers"], Summary["SuperFreeTriggers"], Summary["Retriggers"]), (1, 0, 1))
        self.assertEqual(Summary["UltimateHits"], 1)
        self.assertEqual(Summary["UltimateWin"], 300000)
        self.assertEqual(Summary["UltimateRtp"], 1.5)
        self.assertEqual(Summary["UltimateFrequency"], 10)
        self.assertEqual(Summary["Rtp"], 8)
        self.assertEqual(Summary["rtp_check"], 8)
        self.assertAlmostEqual(Summary["Rtp"], Summary["MainRtp"] + Summary["FreeRtp"] + Summary["SuperFreeRtp"])
        self.assertEqual(Summary[">5x"], 2)
        self.assertEqual(Summary[">10x"], 0)
        self.assertEqual(Summary["WinAbove10Count"], 0)

    def test_super_free_direct_entry_counts_once_in_common_trigger(self):
        Game = ScriptedGame([
            spin_result(Awarded=1, Remaining=1, NextMode="SuperFree"),
            spin_result("SuperFree", Win=100000),
        ])
        with patch.object(simulation, "ThemeMath", return_value=Game):
            Row = simulation.simulation(1)[-1]
        self.assertEqual((Row["触发Free"], Row["FreeTriggers"], Row["SuperFreeTriggers"]), (1, 0, 1))
        self.assertEqual((Row["FreeSpins"], Row["SuperFreeSpins"], Row["FreeWin"], Row["SuperFreeWin"]), (1, 1, 0, 100000))

    def test_thresholds_use_strictly_greater_than_round_bet(self):
        Game = ScriptedGame([spin_result(Win=500000), spin_result(Win=500001), spin_result(Win=1000000)])
        with patch.object(simulation, "ThemeMath", return_value=Game):
            Row = simulation.simulation(3)[-1]
        self.assertEqual(Row[">5x"], 2)
        self.assertEqual(Row[">10x"], 0)
        self.assertEqual(Row["WinAbove5Count"], Row[">5x"])
        self.assertNotIn("WinAtLeast5Count", Row)

    def test_integer_money_keeps_large_amounts(self):
        LargeWin = 2 ** 60 + 1
        Game = ScriptedGame([spin_result(Win=LargeWin) for _ in range(3)])
        with patch.object(simulation, "ThemeMath", return_value=Game):
            Row = simulation.simulation(3)[-1]
        self.assertEqual(Row["总赢钱"], LargeWin * 3)
        self.assertIsInstance(Row["总赢钱"], int)
        self.assertEqual(Row["BaseLine"], LargeWin * 3)

    def test_mismatched_line_amount_and_incomplete_free_session_are_rejected(self):
        for Spins in (
            [spin_result(Win=100000, line_win=1)],
            [spin_result(Awarded=2, Remaining=2, NextMode="Free"), spin_result("Free")],
        ):
            with self.subTest(Spins=Spins), patch.object(simulation, "ThemeMath", return_value=ScriptedGame(Spins)), self.assertRaises(ValueError):
                simulation.simulation(1)

    def test_get_line_win_supports_template_detail_fallback(self):
        self.assertEqual(simulation.get_line_win({"win_items": [{"win": 10}, {"win": 20}]}), 30)
        with self.assertRaises(ValueError):
            simulation.get_line_win({"line_win": 1.5})

    def test_zero_spins_and_argument_validation(self):
        Row = simulation.simulation(0, Seed=7)[-1]
        for Field in ("SPIN", "总押注", "总赢钱", "FreeSpin", "Rtp", "HitRate", "UltimateRtp"):
            self.assertEqual(Row[Field], 0)
        self.assertIsNone(Row["UltimateFrequency"])
        for Options in (
            {"spin_times": -1}, {"spin_times": 1.5}, {"spin_times": True},
            {"index": -1}, {"general_index": -1}, {"free_general_index": -1},
            {"BaseBet": 0}, {"report_interval": -1}, {"Seed": "7"}, {"PrintUpdates": 1},
        ):
            with self.subTest(Options=Options), self.assertRaises(ValueError):
                simulation.simulation(**Options)

    @staticmethod
    def write_fixed_section(PathValue, General, Board):
        Parser = ConfigParser()
        Parser.optionxform = str
        Parser.read(PathValue, encoding="utf-8-sig")
        SectionName = f"GENERAL_{General}"
        if not Parser.has_section(SectionName):
            Parser[SectionName] = dict(Parser["GENERAL_1"])
        Section = Parser[SectionName]
        Section["BASE_RATE"] = "0,0,10000,0"
        Section["FIX_DISORDER"] = "0"
        Section["FIX_NUM"] = "1"
        Section["FIX_RESULT_1"] = ",".join(str(Symbol) for Column in Board for Symbol in Column)
        with PathValue.open("w", encoding="utf-8") as Handle:
            Parser.write(Handle)

    def test_actual_index_general_and_free_general_select_their_conf_sections(self):
        with tempfile.TemporaryDirectory() as Directory:
            Target = Path(Directory) / "cjyx"
            shutil.copytree(ProjectDir, Target, ignore=shutil.ignore_patterns("__pycache__", "*.csv"))
            Main0 = Target / "reel_config/cjyx_rand_ex_0.conf"
            Main4 = Target / "reel_config/cjyx_rand_ex_4.conf"
            Free0 = Target / "free_reel_config/cjyx_free_rand_ex_0.conf"
            Free4 = Target / "free_reel_config/cjyx_free_rand_ex_4.conf"
            Super0 = Target / "free_reel_config/cjyx_super_free_rand_ex_0.conf"
            Super4 = Target / "free_reel_config/cjyx_super_free_rand_ex_4.conf"
            Blank = [[Symbol] * 5 for Symbol in (8, 9, 10, 11, 12)]
            Winning = [[3] * 5 for _ in range(5)]
            Trigger = [list(Column) for Column in Blank]
            for Column in range(3):
                Trigger[Column][0] = 0
            self.write_fixed_section(Main0, 7, Trigger)
            shutil.copy2(Main0, Main4)
            self.write_fixed_section(Main4, 7, Blank)
            self.write_fixed_section(Free0, 7, Winning)
            self.write_fixed_section(Free0, 8, Blank)
            self.write_fixed_section(Super0, 7, Blank)
            self.write_fixed_section(Super0, 8, Blank)
            shutil.copy2(Free0, Free4)
            shutil.copy2(Super0, Super4)
            ServerPath = Target / "special/cjyx_game_server.conf"
            Parser = ThemeMath._read_config_file(ServerPath)
            Parser["4"] = dict(Parser["0"])
            with ServerPath.open("w", encoding="utf-8") as Handle:
                Parser.write(Handle)
            for RelativePath, GeneralCount in (
                ("reel_config/cjyx_rand_main.conf", 2),
                ("free_reel_config/cjyx_free_rand_main.conf", 3),
            ):
                SpecPath = Target / RelativePath
                Parser = ThemeMath._read_config_file(SpecPath)
                Parser["MAIN"]["ITEM_COM_COUNT"] = str(GeneralCount)
                with SpecPath.open("w", encoding="utf-8") as Handle:
                    Parser.write(Handle)
            def Factory(**Options):
                return ThemeMath(project_dir=Target, **Options)
            with patch.object(simulation, "ThemeMath", side_effect=Factory):
                self.assertEqual(simulation.discover_general_indexes(), [1, 7])
                self.assertEqual(simulation.discover_general_indexes(free_game=True), [1, 7, 8])
                WinningFree = simulation.simulation(1, 0, 7, 7, Seed=3)[-1]
                LosingFree = simulation.simulation(1, 0, 7, 8, Seed=3)[-1]
                OtherIndex = simulation.simulation(1, 4, 7, 7, Seed=3)[-1]
            self.assertEqual(WinningFree["FreeWin"], 19 * 20 * 100000 * 10)
            self.assertEqual(LosingFree["FreeWin"], 0)
            self.assertEqual(OtherIndex["FreeSpin"], 0)
            self.assertEqual((WinningFree["ActualGeneral"], WinningFree["ActualFreeGeneral"]), (7, 7))
            self.assertEqual((OtherIndex["INDEX"], OtherIndex["ActualIndex"]), (4, 4))
            self.assertEqual(OtherIndex["ReelConfigFile"], "cjyx_rand_ex_4.conf")
            self.assertEqual(WinningFree["Free次数"], WinningFree["FreeSpin"])

    def test_fallback_is_reported_with_requested_and_actual_values(self):
        Row = simulation.simulation(2, index=99, general_index=99, Seed=7)[-1]
        self.assertEqual((Row["INDEX"], Row["GENERAL"]), (99, 99))
        self.assertEqual((Row["ActualIndex"], Row["ActualGeneral"]), (0, 1))
        self.assertTrue(Row["IndexFallback"])
        self.assertTrue(Row["GeneralFallback"])
        self.assertEqual(Row["ReelConfigFile"], "cjyx_rand_ex_0.conf")

    def test_seeded_real_engine_and_compatibility_summary_are_identical(self):
        First = simulation.simulation(200, Seed=2, report_interval=50)
        Second = simulation.simulation(200, Seed=2, report_interval=50)
        self.assertEqual(First, Second)
        Final = First[-1]
        self.assertEqual(Final, simulation.simulate(Spins=200, Seed=2))
        self.assertEqual([Row["SPIN"] for Row in First], [50, 100, 150, 200])
        self.assertEqual(Final["FreeSpinsAwarded"], Final["FreeSpin"])
        self.assertEqual(Final["TotalSpins"], Final["SPIN"] + Final["FreeSpin"])
        self.assertEqual(Final["TotalWin"], Final["MainWin"] + Final["FreeWin"] + Final["SuperFreeWin"])
        self.assertEqual(Final["rtp"], Final["rtp_check"])

    def test_progress_uses_shared_table_and_does_not_change_totals(self):
        with patch.object(simulation.status_handler, "print_table") as PrintTable:
            WithProgress = simulation.simulation(5, Seed=7, report_interval=2, PrintUpdates=True)
        Without = simulation.simulation(5, Seed=7, report_interval=2)
        self.assertEqual(WithProgress, Without)
        self.assertEqual(PrintTable.call_count, 2)
        self.assertEqual([Call.args[0][0]["SPIN"] for Call in PrintTable.call_args_list], [2, 4])

    def test_csv_keeps_template_headers_and_exact_amounts(self):
        with tempfile.TemporaryDirectory() as Directory:
            Output = Path(Directory) / "nested/result.csv"
            Row = simulation.simulate(Spins=4, Seed=7)
            simulation.append_summary(Row, Output)
            simulation.append_summary(Row, Output)
            with Output.open(newline="", encoding="utf-8") as Handle:
                Reader = csv.DictReader(Handle)
                self.assertEqual(Reader.fieldnames, list(simulation.CsvFields))
                Rows = list(Reader)
            self.assertEqual(len(Rows), 2)
            self.assertTrue(set(SlotsSimulation.DEFAULT_HEADERS).issubset(Rows[0]))
            self.assertEqual(int(Rows[0]["总赢钱"]), int(Rows[0]["BaseLine"]) + int(Rows[0]["FreeLine"]))
            self.assertEqual(float(Rows[0]["rtp_check"]), int(Rows[0]["总赢钱"]) / int(Rows[0]["总押注"]))
            self.assertEqual(Rows[0]["Seed"], "7")

    def test_incompatible_csv_header_preserves_file(self):
        with tempfile.TemporaryDirectory() as Directory:
            Output = Path(Directory) / "old.csv"
            Original = "DifferentHeader\nunchanged\n"
            Output.write_text(Original, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "表头不兼容"):
                simulation.append_summary(simulation.simulate(Spins=0), Output)
            self.assertEqual(Output.read_text(encoding="utf-8"), Original)

    def test_cli_prints_shared_groups_and_appends_only_final_per_combination(self):
        with tempfile.TemporaryDirectory() as Directory:
            Output = Path(Directory) / "cli.csv"
            Printed = io.StringIO()
            SharedPrint = simulation.status_handler.print_table
            with redirect_stdout(Printed), patch.object(simulation.status_handler, "print_table", wraps=SharedPrint) as PrintTable:
                ExitCode = simulation.main([
                    "--spins", "3", "--index", "0", "--generals", "1,2",
                    "--free-general-index", "1", "--seed", "8", "--report-interval", "1",
                    "--no-print-updates", "--output", str(Output),
                ])
            self.assertEqual(ExitCode, 0)
            self.assertEqual(PrintTable.call_count, 1)
            self.assertIn("普通免费", Printed.getvalue())
            self.assertIn("超级免费", Printed.getvalue())
            self.assertIn("终极大奖", Printed.getvalue())
            with Output.open(newline="", encoding="utf-8") as Handle:
                Rows = list(csv.DictReader(Handle))
            self.assertEqual(len(Rows), 2)
            self.assertEqual([Row["GENERAL"] for Row in Rows], ["1", "2"])
            self.assertTrue(all(Row["SPIN"] == "3" for Row in Rows))
            self.assertEqual(Rows[1]["ActualGeneral"], "1")
            self.assertEqual(Rows[1]["GeneralFallback"], "True")

    def test_cli_defaults_and_scalar_arguments_match_lines_model(self):
        Options = simulation.parse_args([])
        self.assertEqual(Options.spins, 1000000)
        self.assertEqual((Options.index, Options.general, Options.free_general), (0, 1, None))
        self.assertEqual(Options.report_interval, 5000)
        Options = simulation.parse_args(["--index", "4", "--general-index", "7", "--free-general-index", "8"])
        self.assertEqual((Options.index, Options.general, Options.free_general), (4, 7, 8))

    def test_plural_cli_options_are_separate_and_mutually_exclusive(self):
        Options = simulation.parse_args(["--indexes", "0,4", "--generals", "1,7", "--free-generals", "7,8"])
        self.assertEqual((Options.Indexes, Options.Generals, Options.FreeGenerals), ([0, 4], [1, 7], [7, 8]))
        for Args in (
            ["--index", "0", "--indexes", "0,4"],
            ["--general", "1", "--generals", "1,7"],
            ["--free-general", "1", "--free-generals", "1,8"],
            ["--indexes", ""], ["--generals", "1,,2"],
        ):
            with self.subTest(Args=Args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                simulation.parse_args(Args)

    def test_cli_final_checkpoint_is_printed_once(self):
        with tempfile.TemporaryDirectory() as Directory, redirect_stdout(io.StringIO()):
            Output = Path(Directory) / "checkpoints.csv"
            with patch.object(simulation.status_handler, "print_table") as PrintTable:
                simulation.main(["--spins", "4", "--report-interval", "2", "--seed", "7", "--output", str(Output)])
            Batches = [[Row["SPIN"] for Row in Call.args[0]] for Call in PrintTable.call_args_list]
            self.assertEqual(Batches, [[2], [4]])
            with Output.open(newline="", encoding="utf-8") as Handle:
                self.assertEqual(len(list(csv.DictReader(Handle))), 1)

    def test_cli_saves_completed_combination_before_later_failure(self):
        Complete = simulation.simulation(1, Seed=7)
        with tempfile.TemporaryDirectory() as Directory:
            Output = Path(Directory) / "completed.csv"
            with patch.object(simulation, "simulation", side_effect=[Complete, ValueError("后续组合无法执行")]), patch.object(simulation.status_handler, "print_table") as PrintTable:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    simulation.main(["--spins", "1", "--generals", "1,2", "--output", str(Output)])
            with Output.open(newline="", encoding="utf-8") as Handle:
                Rows = list(csv.DictReader(Handle))
            self.assertEqual(len(Rows), 1)
            self.assertEqual(Rows[0]["GENERAL"], "1")
            self.assertEqual(Rows[0]["SPIN"], "1")
            self.assertEqual(PrintTable.call_count, 1)

    def test_cli_validates_csv_and_all_batch_values_before_running(self):
        with tempfile.TemporaryDirectory() as Directory:
            Output = Path(Directory) / "old.csv"
            Original = "DifferentHeader\nunchanged\n"
            Output.write_text(Original, encoding="utf-8")
            with patch.object(simulation, "ThemeMath") as Factory, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                simulation.main(["--spins", "1", "--output", str(Output)])
            Factory.assert_not_called()
            self.assertEqual(Output.read_text(encoding="utf-8"), Original)
            Output = Path(Directory) / "invalid.csv"
            with patch.object(simulation, "ThemeMath") as Factory, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                simulation.main(["--spins", "1", "--indexes", "0,-1", "--output", str(Output)])
            Factory.assert_not_called()
            self.assertFalse(Output.exists())

    def test_cli_invalid_arguments_do_not_write_csv(self):
        with tempfile.TemporaryDirectory() as Directory:
            Output = Path(Directory) / "bad.csv"
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                simulation.main(["--spins", "-1", "--output", str(Output)])
            self.assertFalse(Output.exists())


if __name__ == "__main__":
    unittest.main()
