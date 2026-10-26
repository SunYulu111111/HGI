"""Replay the local native calibration sampler against the actual ThemeMath.

This compiles calibration_sampler.cpp in a temporary directory. It does not run
the supplied Linux server binary or write simulation results into the project.
Every uniform draw and every paid spin's six monetary components must match.
Replay always uses the default FullRandom reward mode. The sampler's optional
ExpectedRewards=1 mode estimates conditional means and is not a payout replay.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


BaseBet = 100_000


def LoadThemeMath(ScriptDirectory: Path):
    """Load this project's real implementation, with candidate config support."""

    Source = ScriptDirectory / "theme_math.py"
    Spec = importlib.util.spec_from_file_location("YnggCalibrationThemeMath", Source)
    if Spec is None or Spec.loader is None:
        raise RuntimeError(f"Cannot load ThemeMath from {Source}")
    Module = importlib.util.module_from_spec(Spec)
    sys.dont_write_bytecode = True
    Spec.loader.exec_module(Module)
    return Module.ThemeMath


def ValidateScope(Math, Project: Path) -> None:
    """Refuse configurations outside the sampler's exact replay scope."""

    if Math.base_bet != BaseBet:
        raise ValueError("Calibration replay requires BaseBet=100000")
    if (Math.config.col_count, Math.config.row_count, Math.config.item_count) != (6, 5, 13):
        raise ValueError("Calibration replay requires the current 6x5, 13-symbol layout")
    if any(Math.config.grid_disables) or any(Math.config.grid_disables_free):
        raise ValueError("Calibration replay requires every grid position to be enabled")
    if (
        Math.FREE_SPIN_ID != 0
        or Math.WILD_ID != 1
        or Math.FEATURE_ID != 2
        or Math.SUPER_SCATTER_SOURCE_ID != 0
        or Math.BET_UNIT != 10_000
    ):
        raise ValueError("Calibration replay requires the current symbol IDs and BetUnit")
    for Relative in (
        "reel_config/yngg_rand_ex_0.conf",
        "free_reel_config/yngg_free_rand_ex_0.conf",
    ):
        Config = Math._read_config_file(Project / Relative)
        Section = Config["GENERAL_1"]
        for Key in ("FIX_DISORDER", "ZERO_DISORDER"):
            if int(Section.get(Key, "0")) != 0:
                raise ValueError(f"Calibration replay does not support {Key}=1 in {Relative}")


class ReplayDraws:
    """Consume the native sampler's requested ranges and selected values."""

    def __init__(self, Stream):
        self.Stream = Stream
        self.Calls = 0
        self.SpinIndex = -1

    def Draw(self, Stop: int) -> int:
        Line = self.Stream.readline()
        if not Line:
            raise AssertionError(
                f"Random stream exhausted at spin {self.SpinIndex}, call {self.Calls}"
            )
        ExpectedStop, Hit = map(int, Line.split())
        if Stop != ExpectedStop or not 0 <= Hit < Stop:
            raise AssertionError(
                f"Random mismatch at spin {self.SpinIndex}, call {self.Calls}: "
                f"PythonStop={Stop}, NativeStop={ExpectedStop}, Hit={Hit}"
            )
        self.Calls += 1
        return Hit

    def Choose(self, Values):
        return Values[self.Draw(len(Values))]

    @staticmethod
    def RejectShuffle(*Arguments, **Keywords):
        raise ValueError("Calibration replay does not support shuffled fixed results")


def Replay(Math, Draws: ReplayDraws, Outcomes, SpinCount: int) -> dict:
    """Compare monetary integers, modes, and Bonus flags for every paid spin."""

    Counts = {
        "BaseBonusCount": 0,
        "FreeSessionCount": 0,
        "SuperFreeSessionCount": 0,
        "FreeSpinCount": 0,
        "SuperFreeSpinCount": 0,
    }
    with (
        patch.object(random, "randrange", Draws.Draw),
        patch.object(random, "choice", Draws.Choose),
        patch.object(random, "shuffle", Draws.RejectShuffle),
    ):
        for SpinIndex in range(SpinCount):
            Draws.SpinIndex = SpinIndex
            Line = Outcomes.readline()
            if not Line:
                raise AssertionError(f"Native outcome stream ended before spin {SpinIndex}")
            Expected = list(map(int, Line.split()))
            if len(Expected) != 9:
                raise AssertionError(f"Invalid native outcome at spin {SpinIndex}: {Line!r}")
            Values = [0] * 7
            Base = Math.ng_spin(index=0, general_index=1)
            Values[0] = Base["total_win"] - Base["feature_win"]
            Values[1] = Base["feature_win"]
            Mode = 0
            if Base["is_trigger_feature"]:
                Counts["BaseBonusCount"] += 1
            if Base["is_trigger_free"]:
                Mode = 1 if Base["free_mode"] == "free" else 2
                Prefix = "Free" if Mode == 1 else "SuperFree"
                Counts[Prefix + "SessionCount"] += 1
                Remaining = Base["free_times"]
                Golden = set()
                Seen = False
                while Remaining > 0:
                    Free = Math.fg_spin(
                        index=0,
                        general_index=1,
                        free_mode=Base["free_mode"],
                        golden_squares=Golden,
                        remaining_spins=Remaining,
                        bonus_seen=Seen,
                    )
                    Counts[Prefix + "SpinCount"] += 1
                    Offset = 2 if Mode == 1 else 4
                    Values[Offset] += Free["total_win"] - Free["feature_win"]
                    Values[Offset + 1] += Free["feature_win"]
                    Remaining -= 1
                    Remaining += Free["retrigger_spins"]
                    Golden = set(map(tuple, Free["golden_squares"]))
                    Seen = Free["free_bonus_seen"]
            Values[6] = sum(Values[:6])
            Values.extend((Mode, int(Base["is_trigger_feature"])))
            if Values != Expected:
                raise AssertionError(
                    f"Outcome mismatch at spin {SpinIndex}: Python={Values}, Native={Expected}"
                )
    if Outcomes.readline():
        raise AssertionError("Native outcome stream contains extra spins")
    if Draws.Stream.readline():
        raise AssertionError("Native random stream contains unconsumed draws")
    return Counts


def Main() -> int:
    ScriptDirectory = Path(__file__).resolve().parent
    Parser = argparse.ArgumentParser(description=__doc__)
    Parser.add_argument(
        "--project", dest="Project", type=Path, default=ScriptDirectory,
        help="yngg configuration directory; defaults to this script's directory",
    )
    Parser.add_argument("--spins", dest="Spins", type=int, default=2_000)
    Parser.add_argument("--seed", dest="Seed", type=int, default=20261022)
    Arguments = Parser.parse_args()
    if Arguments.Spins <= 0:
        Parser.error("--spins must be positive")
    if Arguments.Seed < 0:
        Parser.error("--seed must be nonnegative")
    Project = Arguments.Project.resolve()
    Compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
    if Compiler is None:
        raise RuntimeError("A C++17 compiler (c++, clang++, or g++) is required")
    ThemeMath = LoadThemeMath(ScriptDirectory)
    Math = ThemeMath(base_bet=BaseBet, project_dir=Project)
    ValidateScope(Math, Project)
    Start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="yngg-calibration-replay-") as Temporary:
        TemporaryDirectory = Path(Temporary)
        Executable = TemporaryDirectory / "calibration_sampler"
        RandomPath = TemporaryDirectory / "random.log"
        OutcomePath = TemporaryDirectory / "outcomes.log"
        subprocess.run(
            [
                Compiler, "-std=c++17", "-O3", "-DNDEBUG",
                str(ScriptDirectory / "calibration_sampler.cpp"), "-o", str(Executable),
            ],
            check=True, capture_output=True, text=True,
        )
        Environment = os.environ.copy()
        Environment["YNGG_RANDOM_LOG"] = str(RandomPath)
        Environment["YNGG_OUTCOME_LOG"] = str(OutcomePath)
        Native = subprocess.run(
            [str(Executable), str(Project), str(Arguments.Spins), str(Arguments.Seed), "0", "0"],
            check=True, capture_output=True, text=True, env=Environment,
        )
        NativeSummary = json.loads(Native.stdout)
        if NativeSummary["BaseBet"] != BaseBet:
            raise AssertionError("Native sampler used a different BaseBet")
        if NativeSummary["RewardSampling"] != "FullRandom" or NativeSummary["ExpectedRewardsIntegrated"]:
            raise AssertionError("Exact replay requires FullRandom reward sampling")
        with RandomPath.open() as RandomStream, OutcomePath.open() as OutcomeStream:
            Draws = ReplayDraws(RandomStream)
            Counts = Replay(Math, Draws, OutcomeStream, Arguments.Spins)
    Result = {
        "SamplerKind": "LocalRulesNativeSampler",
        "BinaryServerExecuted": False,
        "Project": str(Project),
        "BaseBet": BaseBet,
        "Seed": Arguments.Seed,
        "SpinsMatched": Arguments.Spins,
        "RandomCallsMatched": Draws.Calls,
        "AllMetricsExactlyMatched": True,
        **Counts,
        "NativeSummary": NativeSummary,
        "Seconds": time.perf_counter() - Start,
    }
    print(json.dumps(Result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(Main())
    except subprocess.CalledProcessError as Error:
        print(Error.stderr or str(Error), file=sys.stderr)
        raise SystemExit(1) from Error
