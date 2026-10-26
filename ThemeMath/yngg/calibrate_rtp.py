"""Run reproducible native sampling of the local yngg rules.

Example:
    python calibrate_rtp.py --spins 25000000 --runs 8 --workers 4 \
        --seed 20261022 --output /tmp/yngg-calibration.json

The sampler is compiled into a temporary directory and reads a frozen copy of
the project's configuration. It does not execute a server binary. Quantiles
remain attached to individual runs; combining run quantiles is not a pooled
quantile estimate.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
import time


RtpFields = (
    "BaseClusterRtp",
    "BaseBonusRtp",
    "FreeClusterRtp",
    "FreeBonusRtp",
    "SuperFreeClusterRtp",
    "SuperFreeBonusRtp",
    "Rtp",
)
TriggerFields = (
    ("BaseBonusTriggerCount", "BaseBonusFrequency"),
    ("FreeTriggerCount", "FreeFrequency"),
    ("SuperFreeTriggerCount", "SuperFreeFrequency"),
)


def PositiveInteger(Value: str) -> int:
    Number = int(Value)
    if Number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return Number


def BuildParser() -> argparse.ArgumentParser:
    Parser = argparse.ArgumentParser(description=__doc__)
    Parser.add_argument("--spins", dest="Spins", type=PositiveInteger, default=25_000_000,
                        help="paid Base spins per run (default: 25000000)")
    Parser.add_argument("--runs", dest="Runs", type=PositiveInteger, default=4)
    Parser.add_argument("--workers", dest="Workers", type=PositiveInteger, default=4)
    Parser.add_argument("--seed", dest="Seed", type=int, default=20261022,
                        help="first seed; subsequent runs use Seed + RunIndex")
    Parser.add_argument("--project", dest="Project", type=Path,
                        default=Path(__file__).resolve().parent)
    Parser.add_argument("--output", dest="Output", type=Path,
                        default=Path("rtp_calibration_batch.json"))
    Parser.add_argument("--expected-rewards", dest="ExpectedRewards", action="store_true",
                        help="integrate independent reward tiers; does not measure reward volatility")
    return Parser


def HashFile(FilePath: Path) -> str:
    return hashlib.sha256(FilePath.read_bytes()).hexdigest()


def SnapshotInputs(Project: Path, Snapshot: Path, Source: Path) -> tuple[list[dict], list[dict]]:
    ConfigFiles = []
    for Original in sorted(Project.rglob("*.conf")):
        Relative = Original.relative_to(Project)
        Destination = Snapshot / Relative
        Destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Original, Destination)
        ConfigFiles.append({"Path": str(Relative), "Sha256": HashFile(Destination)})
    SourceFiles = []
    for Original in (
        Source,
        Path(__file__).resolve(),
        Project / "theme_math.py",
        Project / "simulation.py",
        Project.parent / "slots_math.py",
    ):
        if Original.is_file():
            SourceFiles.append({"Path": str(Original), "Sha256": HashFile(Original)})
    return ConfigFiles, SourceFiles


def ReadTriggerCount(Run: dict, CountField: str, FrequencyField: str) -> int:
    Count = int(Run.get(CountField, round(Run[FrequencyField] * Run["BaseSpinCount"])))
    if not 0 <= Count <= Run["BaseSpinCount"]:
        raise ValueError(f"invalid {CountField}: {Count}")
    if not math.isclose(Count / Run["BaseSpinCount"], Run[FrequencyField], abs_tol=1e-10):
        raise ValueError(f"{FrequencyField} disagrees with its trigger count")
    return Count


def CheckRun(Run: dict, Spins: int, RewardSampling: str) -> None:
    if Run["BaseSpinCount"] != Spins:
        raise ValueError("sampler returned a different paid-spin count")
    if Run.get("RewardSampling") != RewardSampling:
        raise ValueError("sampler returned a different reward-sampling mode")
    for Field in RtpFields:
        if not math.isfinite(Run[Field]) or Run[Field] < 0:
            raise ValueError(f"invalid {Field}")
        StandardError = Run[f"{Field}StandardError"]
        if not math.isfinite(StandardError) or StandardError < 0:
            raise ValueError(f"invalid {Field}StandardError")
    if not math.isclose(sum(Run[Field] for Field in RtpFields[:-1]), Run["Rtp"], abs_tol=1e-8):
        raise ValueError("run RTP is not the sum of its six components")
    for CountField, FrequencyField in TriggerFields:
        Run[CountField] = ReadTriggerCount(Run, CountField, FrequencyField)
    if Run["FreeTriggerCount"] + Run["SuperFreeTriggerCount"] > Spins:
        raise ValueError("ordinary and Super Free trigger counts overlap")


def RunSampler(Executable: Path, Snapshot: Path, Spins: int, Seed: int,
               RunIndex: int, ExpectedRewards: bool) -> dict:
    Command = [str(Executable), str(Snapshot), str(Spins), str(Seed), "0", "0",
               str(int(ExpectedRewards))]
    Completed = subprocess.run(Command, check=False, capture_output=True, text=True)
    if Completed.returncode:
        Detail = Completed.stderr.strip() or Completed.stdout.strip()
        raise RuntimeError(f"run {RunIndex + 1}, seed {Seed} failed: {Detail}")
    Run = json.loads(Completed.stdout)
    CheckRun(Run, Spins, "ConditionalExpectation" if ExpectedRewards else "FullRandom")
    Run["RunIndex"] = RunIndex
    Run["Seed"] = Seed
    return Run


def PoolMetric(Runs: list[dict], Field: str) -> tuple[float, float]:
    """Pool sample means and their SEs, including between-run mean differences."""

    Count = sum(Run["BaseSpinCount"] for Run in Runs)
    Mean = math.fsum(Run["BaseSpinCount"] * Run[Field] for Run in Runs) / Count
    M2 = math.fsum(
        Run[f"{Field}StandardError"] ** 2
        * Run["BaseSpinCount"] * (Run["BaseSpinCount"] - 1)
        + Run["BaseSpinCount"] * (Run[Field] - Mean) ** 2
        for Run in Runs
    )
    StandardError = math.sqrt(max(0.0, M2) / (Count * (Count - 1))) if Count > 1 else 0.0
    return Mean, StandardError


def AggregateRuns(Runs: list[dict], ExpectedRewards: bool) -> dict:
    if not Runs:
        raise ValueError("cannot aggregate an empty batch")
    Total = sum(Run["BaseSpinCount"] for Run in Runs)
    Result = {"BaseSpinCount": Total}
    for Field in RtpFields:
        Result[Field], Result[f"{Field}StandardError"] = PoolMetric(Runs, Field)
    for CountField, FrequencyField in TriggerFields:
        Result[CountField] = sum(ReadTriggerCount(Run, CountField, FrequencyField) for Run in Runs)
        Result[FrequencyField] = Result[CountField] / Total
    for Field in ("FreeSpinCount", "SuperFreeSpinCount"):
        Result[Field] = sum(Run[Field] for Run in Runs)

    BonusCount = Result["BaseBonusTriggerCount"]
    Result["BaseBonusVolatilityStatisticsAvailable"] = bool(BonusCount and not ExpectedRewards)
    if BonusCount:
        BonusRuns = [Run for Run in Runs if Run["BaseBonusTriggerCount"]]
        BonusMean = math.fsum(
            Run["BaseBonusTriggerCount"] * Run["BaseBonusConditionalMean"] for Run in BonusRuns
        ) / BonusCount
        Result["BaseBonusConditionalMean"] = BonusMean
        if not ExpectedRewards:
            # The native conditional SD uses population variance (divisor K).
            BonusM2 = math.fsum(
                Run["BaseBonusTriggerCount"]
                * (Run["BaseBonusConditionalStdDev"] ** 2
                   + (Run["BaseBonusConditionalMean"] - BonusMean) ** 2)
                for Run in BonusRuns
            )
            Result["BaseBonusConditionalStdDev"] = math.sqrt(max(0.0, BonusM2) / BonusCount)
            Result["BaseBonusConditionalMeanStandardError"] = (
                math.sqrt(max(0.0, BonusM2) / (BonusCount * (BonusCount - 1)))
                if BonusCount > 1 else 0.0
            )
            Result["BaseBonusMax"] = max(Run["BaseBonusMax"] for Run in BonusRuns)

    ComponentsMatch = math.isclose(
        math.fsum(Result[Field] for Field in RtpFields[:-1]), Result["Rtp"], abs_tol=1e-8
    )
    BonusMeanMatches = not BonusCount or math.isclose(
        Result["BaseBonusConditionalMean"] * Result["BaseBonusFrequency"],
        Result["BaseBonusRtp"], abs_tol=1e-8,
    )
    if not ComponentsMatch or not BonusMeanMatches:
        raise ValueError("aggregated RTP conservation check failed")
    Result["Verification"] = {
        "RtpComponentsMatch": ComponentsMatch,
        "BaseBonusConditionalMeanMatchesRtp": BonusMeanMatches,
        "RunQuantilesPooled": False,
    }
    return Result


def WriteJson(Output: Path, Result: dict) -> None:
    Output.parent.mkdir(parents=True, exist_ok=True)
    TemporaryPath = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=Output.parent,
                                prefix=Output.name + ".", suffix=".tmp", delete=False) as Target:
            TemporaryPath = Path(Target.name)
            json.dump(Result, Target, ensure_ascii=False, indent=2, allow_nan=False)
            Target.write("\n")
        os.replace(TemporaryPath, Output)
    finally:
        if TemporaryPath is not None:
            TemporaryPath.unlink(missing_ok=True)


def Main(Arguments: list[str] | None = None) -> int:
    Parser = BuildParser()
    Args = Parser.parse_args(Arguments)
    Project = Args.Project.expanduser().resolve()
    Output = Args.Output.expanduser().resolve()
    Source = Project / "calibration_sampler.cpp"
    if not Source.is_file():
        Parser.error(f"native sampler source not found: {Source}")
    if Args.Seed < 0 or Args.Seed + Args.Runs - 1 > 2 ** 64 - 1:
        Parser.error("seeds must fit unsigned 64-bit integers")
    if Args.Spins > 2 ** 63 - 1:
        Parser.error("spin count must fit a signed 64-bit integer")
    Protected = {File.resolve() for File in Project.rglob("*.conf")}
    Protected.update({Source.resolve(), Project / "rtp_calibration.json"})
    if Output in Protected:
        Parser.error("output must not replace an input configuration, sampler source, or rtp_calibration.json")
    Compiler = shutil.which("clang++") or shutil.which("c++") or shutil.which("g++")
    if Compiler is None:
        Parser.error("a C++17 compiler is required")

    Start = time.perf_counter()
    Workers = min(Args.Workers, Args.Runs)
    with TemporaryDirectory(prefix="yngg-calibration-") as Directory:
        TemporaryRoot = Path(Directory)
        Snapshot = TemporaryRoot / "Project"
        ConfigFiles, SourceFiles = SnapshotInputs(Project, Snapshot, Source)
        FrozenSource = TemporaryRoot / "calibration_sampler.cpp"
        shutil.copyfile(Source, FrozenSource)
        SourceFiles[0]["Sha256"] = HashFile(FrozenSource)
        Executable = TemporaryRoot / "calibration_sampler"
        CompileCommand = [Compiler, "-std=c++17", "-O3", str(FrozenSource), "-o", str(Executable)]
        Compiled = subprocess.run(CompileCommand, check=False, capture_output=True, text=True)
        if Compiled.returncode:
            raise RuntimeError("native sampler compilation failed:\n" + Compiled.stderr.strip())

        Runs = []
        with ThreadPoolExecutor(max_workers=Workers) as Executor:
            Futures = [
                Executor.submit(RunSampler, Executable, Snapshot, Args.Spins,
                                Args.Seed + RunIndex, RunIndex, Args.ExpectedRewards)
                for RunIndex in range(Args.Runs)
            ]
            for Future in as_completed(Futures):
                Run = Future.result()
                Runs.append(Run)
                print(f"Completed {len(Runs)}/{Args.Runs}: seed {Run['Seed']}, "
                      f"RTP {Run['Rtp']:.6f}, {Run['Seconds']:.2f}s", flush=True)
        Runs.sort(key=lambda Run: Run["RunIndex"])

    Result = AggregateRuns(Runs, Args.ExpectedRewards)
    Result.update({
        "CreatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "SamplerKind": "LocalRulesNativeSampler",
        "BinaryServerExecuted": False,
        "RewardSampling": "ConditionalExpectation" if Args.ExpectedRewards else "FullRandom",
        "StandardErrorInterpretation": (
            "Monte Carlo SE after integrating independent reward tiers; it does not describe player payout volatility."
            if Args.ExpectedRewards else "Monte Carlo SE of fully sampled paid-Base-spin returns."
        ),
        "Project": str(Project),
        "TypeIndex": 0,
        "GeneralIndex": 1,
        "BaseBet": 100000,
        "Denominator": "Total paid Base bets, including triggered Free and Super Free sessions and retriggers.",
        "SpinsPerRun": Args.Spins,
        "RunCount": Args.Runs,
        "Workers": Workers,
        "Seeds": [Run["Seed"] for Run in Runs],
        "InputSnapshotUsed": True,
        "Compiler": Compiler,
        "CompilerOptions": ["-std=c++17", "-O3"],
        "ConfigFiles": ConfigFiles,
        "SourceFiles": SourceFiles,
        "Runs": Runs,
        "Seconds": time.perf_counter() - Start,
    })
    WriteJson(Output, Result)
    print(f"Saved {Result['BaseSpinCount']} paid Base spins to {Output}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(Main())
    except (OSError, ValueError, RuntimeError) as Error:
        print(f"Calibration failed: {Error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
