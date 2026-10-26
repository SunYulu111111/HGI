"""Benchmark local Python spins and compare an optional reference implementation.

Examples:
    python -B benchmark_spin.py --spins 5000 --runs 3
    python -B benchmark_spin.py --reference /path/to/original/theme_math.py
    python -B benchmark_spin.py --reference /path/to/original/theme_math.py --verify-only

Timing uses Base spins plus every triggered Free session. Differential validation
checks each Base/Free result, observable last-result state, RNG requests and RNG
state. --verify-spins is the paid-spin count for each TYPE/detail combination.
Timing is evidence, never a pass/fail performance threshold.
"""

from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
from statistics import mean
import sys
from time import perf_counter

from theme_math import ThemeMath


class ComparisonFailure(RuntimeError):
    def __init__(self, Details):
        super().__init__(str(Details))
        self.Details = Details


def freeze(Value):
    """Detach mutable RNG arguments before a shuffle or subsequent game mutation."""

    if isinstance(Value, dict):
        return ("Dict", tuple((Key, freeze(Item)) for Key, Item in sorted(Value.items())))
    if isinstance(Value, (list, tuple)):
        return (type(Value).__name__, tuple(freeze(Item) for Item in Value))
    if isinstance(Value, (set, frozenset)):
        return (type(Value).__name__, tuple(sorted((freeze(Item) for Item in Value), key=repr)))
    return Value


class RandomTrace(AbstractContextManager):
    """Observe module-level RNG APIs without changing their implementation."""

    Names = ("randrange", "randint", "choice", "choices", "shuffle", "sample",
             "random", "getrandbits", "uniform")

    def __enter__(self):
        self.Requests = []
        self.Originals = {Name: getattr(random, Name) for Name in self.Names}
        for Name, Original in self.Originals.items():
            setattr(random, Name, self.wrap(Name, Original))
        return self

    def wrap(self, Name, Original):
        def Recorded(*Args, **Kwargs):
            Request = (Name, freeze(Args), freeze(Kwargs))
            Result = Original(*Args, **Kwargs)
            self.Requests.append((Request, freeze(Result)))
            return Result
        return Recorded

    def __exit__(self, *ExceptionInfo):
        for Name, Original in self.Originals.items():
            setattr(random, Name, Original)
        return False


def first_difference(Reference, Current, Location="$"):
    if type(Reference) is not type(Current):
        return {"Path": Location, "Reference": repr(Reference)[:500], "Current": repr(Current)[:500]}
    if isinstance(Reference, dict):
        if Reference.keys() != Current.keys():
            return {"Path": Location, "ReferenceKeys": sorted(Reference), "CurrentKeys": sorted(Current)}
        for Key in Reference:
            Difference = first_difference(Reference[Key], Current[Key], f"{Location}.{Key}")
            if Difference:
                return Difference
    elif isinstance(Reference, (list, tuple)):
        if len(Reference) != len(Current):
            return {"Path": Location, "ReferenceLength": len(Reference), "CurrentLength": len(Current)}
        for Index, (Before, After) in enumerate(zip(Reference, Current)):
            Difference = first_difference(Before, After, f"{Location}[{Index}]")
            if Difference:
                return Difference
    elif Reference != Current:
        return {"Path": Location, "Reference": repr(Reference)[:500], "Current": repr(Current)[:500]}
    return None


def require_equal(Reference, Current, Context, Check):
    Difference = first_difference(Reference, Current)
    if Difference:
        raise ComparisonFailure({**Context, "Check": Check, "Difference": Difference})


def load_reference(PathValue):
    Name = "_yngg_benchmark_reference"
    Spec = importlib.util.spec_from_file_location(Name, PathValue)
    if Spec is None or Spec.loader is None:
        raise ValueError(f"Cannot import reference: {PathValue}")
    Module = importlib.util.module_from_spec(Spec)
    sys.modules[Name] = Module
    Spec.loader.exec_module(Module)
    # theme_math was imported first, so both classes use the current CountGame.
    return Module.ThemeMath


def new_totals():
    return {
        "PaidSpinCount": 0, "PaidBet": 0,
        "BaseClusterWin": 0, "BaseBonusWin": 0,
        "NormalFreeClusterWin": 0, "NormalFreeBonusWin": 0,
        "SuperFreeClusterWin": 0, "SuperFreeBonusWin": 0,
        "BaseBonusTriggerCount": 0,
        "NormalFreeTriggerCount": 0, "SuperFreeTriggerCount": 0,
        "NormalFreeSpinCount": 0, "SuperFreeSpinCount": 0,
        "NormalFreeRetriggerCount": 0, "SuperFreeRetriggerCount": 0,
    }


def record_win(Totals, Result, Prefix):
    BonusWin = int(Result.get("feature_win", 0))
    Totals[Prefix + "ClusterWin"] += int(Result.get("total_win", 0)) - BonusWin
    Totals[Prefix + "BonusWin"] += BonusWin


def run_sample(Game, SpinCount, Seed, TypeIndex):
    random.seed(Seed)
    Totals = new_totals()
    for _ in range(SpinCount):
        Base = Game.ng_spin(index=TypeIndex, general_index=1, return_detail=False)
        Totals["PaidSpinCount"] += 1
        Totals["PaidBet"] += Game.base_bet
        record_win(Totals, Base, "Base")
        Totals["BaseBonusTriggerCount"] += int(bool(Base.get("is_trigger_feature")))
        if not Base.get("is_trigger_free"):
            continue
        Mode = Base.get("free_mode") or "free"
        Prefix = "SuperFree" if Mode == "super_free" else "NormalFree"
        Remaining = int(Base.get("free_times", 0))
        Totals[Prefix + "TriggerCount"] += 1
        Golden, Seen = set(), False
        while Remaining > 0:
            Free = Game.fg_spin(
                index=TypeIndex, general_index=1, return_detail=False,
                free_mode=Mode, golden_squares=Golden,
                remaining_spins=Remaining, bonus_seen=Seen,
            )
            Totals[Prefix + "SpinCount"] += 1
            record_win(Totals, Free, Prefix)
            Added = int(Free.get("retrigger_spins", 0))
            Totals[Prefix + "RetriggerCount"] += int(Added > 0)
            Remaining += Added - 1
            Golden = set(map(tuple, Free.get("golden_squares") or []))
            Seen = bool(Free.get("free_bonus_seen"))
    Totals["TotalWin"] = sum(Totals[Prefix + Kind] for Prefix in ("Base", "NormalFree", "SuperFree")
                             for Kind in ("ClusterWin", "BonusWin"))
    return Totals, random.getstate()


def observable_state(Game):
    Names = (Name for Name in vars(Game)
             if Name.startswith("last_win") or Name in
             ("last_spin_info", "last_spin_state", "last_ng_result", "last_fg_result"))
    return {Name: getattr(Game, Name) for Name in Names}


def verify_case(CurrentClass, ReferenceClass, ProjectDir, BaseBet, SpinCount, Seed, TypeIndex, Detail):
    Games = {
        "Reference": ReferenceClass(base_bet=BaseBet, project_dir=ProjectDir),
        "Current": CurrentClass(base_bet=BaseBet, project_dir=ProjectDir),
    }
    random.seed(Seed)
    States = {Name: random.getstate() for Name in Games}
    Totals = new_totals()
    RequestCount = 0

    def Pair(Method, Arguments, Context):
        nonlocal RequestCount
        Snapshots, Requests = {}, {}
        for Name, Game in Games.items():
            random.setstate(States[Name])
            with RandomTrace() as Trace:
                Result = getattr(Game, Method)(**deepcopy(Arguments))
            States[Name] = random.getstate()
            Requests[Name] = Trace.Requests
            Snapshots[Name] = deepcopy({"Result": Result, "LastState": observable_state(Game)})
        require_equal(Snapshots["Reference"], Snapshots["Current"], Context, "FullResultAndLastState")
        require_equal(Requests["Reference"], Requests["Current"], Context, "RandomRequests")
        require_equal(States["Reference"], States["Current"], Context, "RandomAfterState")
        RequestCount += len(Requests["Current"])
        return Snapshots["Current"]["Result"]

    for PaidIndex in range(SpinCount):
        Context = {"TypeIndex": TypeIndex, "ReturnDetail": Detail, "PaidSpinIndex": PaidIndex + 1}
        Base = Pair("ng_spin", {"index": TypeIndex, "general_index": 1, "return_detail": Detail}, Context)
        Totals["PaidSpinCount"] += 1
        Totals["PaidBet"] += BaseBet
        record_win(Totals, Base, "Base")
        Totals["BaseBonusTriggerCount"] += int(bool(Base.get("is_trigger_feature")))
        if not Base.get("is_trigger_free"):
            continue
        Mode = Base.get("free_mode") or "free"
        Prefix = "SuperFree" if Mode == "super_free" else "NormalFree"
        Remaining = int(Base.get("free_times", 0))
        Totals[Prefix + "TriggerCount"] += 1
        Golden, Seen, FreeIndex = set(), False, 0
        while Remaining > 0:
            FreeIndex += 1
            Arguments = {
                "index": TypeIndex, "general_index": 1, "return_detail": Detail,
                "free_mode": Mode, "golden_squares": Golden,
                "remaining_spins": Remaining, "bonus_seen": Seen,
            }
            Free = Pair("fg_spin", Arguments, {**Context, "FreeMode": Mode, "FreeSpinIndex": FreeIndex})
            Totals[Prefix + "SpinCount"] += 1
            record_win(Totals, Free, Prefix)
            Added = int(Free.get("retrigger_spins", 0))
            Totals[Prefix + "RetriggerCount"] += int(Added > 0)
            Remaining += Added - 1
            Golden = set(map(tuple, Free.get("golden_squares") or []))
            Seen = bool(Free.get("free_bonus_seen"))
    Totals["TotalWin"] = sum(Totals[Prefix + Kind] for Prefix in ("Base", "NormalFree", "SuperFree")
                             for Kind in ("ClusterWin", "BonusWin"))
    return {
        "TypeIndex": TypeIndex, "ReturnDetail": Detail, "Seed": Seed,
        "PaidSpinCount": SpinCount,
        "FreeSpinCount": Totals["NormalFreeSpinCount"] + Totals["SuperFreeSpinCount"],
        "RandomRequestCount": RequestCount, "ResultsAndLastStateEqual": True,
        "RandomRequestsEqual": True, "RandomAfterStateEqual": True, "Totals": Totals,
    }


def benchmark(Args, ReferenceClass):
    Classes = {"Current": ThemeMath}
    if ReferenceClass is not None:
        Classes["Reference"] = ReferenceClass
    Games = {Name: Class(base_bet=Args.BaseBet, project_dir=Args.ProjectDir)
             for Name, Class in Classes.items()}
    Runs = []
    for RunIndex in range(Args.Runs):
        Seed = Args.Seed + RunIndex
        Order = ["Reference", "Current"] if RunIndex % 2 == 0 else ["Current", "Reference"]
        Order = [Name for Name in Order if Name in Games]
        Entry, States = {"RunIndex": RunIndex + 1, "Seed": Seed, "ExecutionOrder": Order}, {}
        for Name in Order:
            Start = perf_counter()
            Totals, States[Name] = run_sample(Games[Name], Args.Spins, Seed, Args.TypeIndex)
            Seconds = perf_counter() - Start
            Entry[Name] = {
                "Seconds": Seconds, "PaidSpinsPerSecond": Args.Spins / Seconds,
                "Totals": Totals,
                "RandomAfterStateSha256": hashlib.sha256(repr(States[Name]).encode()).hexdigest(),
            }
        if ReferenceClass is not None:
            require_equal(Entry["Reference"]["Totals"], Entry["Current"]["Totals"],
                          {"RunIndex": RunIndex + 1, "Seed": Seed}, "TimingTotals")
            require_equal(States["Reference"], States["Current"],
                          {"RunIndex": RunIndex + 1, "Seed": Seed}, "TimingRandomAfterState")
            Entry["TotalsEqual"] = Entry["RandomAfterStateEqual"] = True
        Runs.append(Entry)
    Summary = {Name + "MeanSeconds": mean(Run[Name]["Seconds"] for Run in Runs) for Name in Games}
    Summary["CurrentPaidSpinsPerSecond"] = Args.Spins / Summary["CurrentMeanSeconds"]
    if ReferenceClass is not None:
        Summary["Speedup"] = Summary["ReferenceMeanSeconds"] / Summary["CurrentMeanSeconds"]
    return {"TypeIndex": Args.TypeIndex, "PaidSpinsPerRun": Args.Spins, "RunCount": Args.Runs,
            "IncludesCompleteFreeSessions": True, "Runs": Runs, "Summary": Summary}


def main(argv=None):
    Parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    Parser.add_argument("--spins", dest="Spins", type=int, default=5000)
    Parser.add_argument("--runs", dest="Runs", type=int, default=3)
    Parser.add_argument("--seed", dest="Seed", type=int, default=20261022)
    Parser.add_argument("--reference", dest="Reference", type=Path, help="Original theme_math.py; both classes use current configs.")
    Parser.add_argument("--project-dir", dest="ProjectDir", type=Path, default=Path(__file__).resolve().parent)
    Parser.add_argument("--base-bet", dest="BaseBet", type=int, default=100000)
    Parser.add_argument("--type", dest="TypeIndex", type=int, default=0, help="TYPE used for timing.")
    Parser.add_argument("--verify-spins", dest="VerifySpins", type=int, default=2000,
                        help="Paid spins per TYPE/detail case (default: 20000 paid spins across 10 cases).")
    Parser.add_argument("--verify-types", dest="VerifyTypes", type=int, nargs="+", default=[0, 4, 8, 12, 17])
    Mode = Parser.add_mutually_exclusive_group()
    Mode.add_argument("--verify-only", dest="VerifyOnly", action="store_true")
    Mode.add_argument("--skip-verify", dest="SkipVerify", action="store_true")
    Parser.add_argument("--output", dest="Output", type=Path, help="Optional JSON report; no simulation CSV is written.")
    Args = Parser.parse_args(argv)
    if min(Args.Spins, Args.Runs, Args.VerifySpins, Args.BaseBet) <= 0:
        Parser.error("spins, runs, verify-spins and base-bet must be positive")
    if Args.VerifyOnly and Args.Reference is None:
        Parser.error("--verify-only requires --reference")
    Args.ProjectDir = Args.ProjectDir.resolve()
    ReferenceClass = load_reference(Args.Reference.resolve()) if Args.Reference else None
    Report = {"Status": "Passed", "Engine": "LocalPython", "ProjectDir": str(Args.ProjectDir),
              "ReferencePath": str(Args.Reference.resolve()) if Args.Reference else None,
              "BaseBet": Args.BaseBet, "Seed": Args.Seed}
    try:
        if not Args.VerifyOnly:
            Report["Benchmark"] = benchmark(Args, ReferenceClass)
        if ReferenceClass is not None and not Args.SkipVerify:
            Cases = []
            for TypeIndex in Args.VerifyTypes:
                for Detail in (False, True):
                    Cases.append(verify_case(ThemeMath, ReferenceClass, Args.ProjectDir, Args.BaseBet,
                                             Args.VerifySpins, Args.Seed, TypeIndex, Detail))
            Report["Verification"] = {
                "PaidSpinsPerCase": Args.VerifySpins, "CaseCount": len(Cases),
                "TotalPaidSpinCount": sum(Case["PaidSpinCount"] for Case in Cases), "Cases": Cases,
            }
        else:
            Report["Verification"] = {"Skipped": True,
                                      "Reason": "Requested" if Args.SkipVerify else "ReferenceNotProvided"}
    except ComparisonFailure as Failure:
        Report["Status"] = "Mismatch"
        Report["Mismatch"] = Failure.Details
    Text = json.dumps(Report, ensure_ascii=False, indent=2)
    if Args.Output is not None:
        Args.Output.parent.mkdir(parents=True, exist_ok=True)
        Args.Output.write_text(Text + "\n", encoding="utf-8")
    print(Text)
    return 0 if Report["Status"] == "Passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
