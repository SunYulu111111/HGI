"""恐龙世界仿真：累计统计、分组报表与 CSV 输出。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import re
import sys


RootDir = Path(__file__).resolve().parent.parent
if str(RootDir) not in sys.path:
    sys.path.insert(0, str(RootDir))

from slots_simulation import simulation as SlotsSimulation

try:
    from .theme_math import ThemeMath
except ImportError:
    from theme_math import ThemeMath


SPIN_TIMES = 10000000
INDEX = [0]
GENERAL_INDEX = [1]
REPORT_INTERVAL = 5000
THRESHOLDS = (5, 10, 20, 50, 100, 1000)
RESULT_CSV = Path(__file__).resolve().with_name("simulate_result.csv")
MAIN_CASCADE_BUCKETS = tuple(range(10))
MAIN_CASCADE_OVERFLOW_LABEL = "10+"
MAIN_CASCADE_BUCKET_COUNT = len(MAIN_CASCADE_BUCKETS) + 1
GENERAL_SECTION_RE = re.compile(r"^\s*\[GENERAL_(\d+)\]\s*$", re.MULTILINE)
RESULT_CSV_FIELDS = [
    "INDEX", "GENERAL", "FREE_GENERAL", "SPIN", "总押注",
    "rtp", "rtp_check", "base_rtp", "base_ways_rtp", "free_rtp", "free_ways_rtp",
    "总赢钱", "Ways赢钱", "BaseWays", "FreeWays", "Hit", "Hit率",
    ">5x", ">10x", ">20x", ">50x", ">100x", ">1000x",
    "触发Free", "Free频率", "Free次数", "FreeSpin", "Free重触发",
    "Free平均次数", "Free平均倍", "main_win_times", "main_win_rate",
    *(f"连消{Number}次" for Number in MAIN_CASCADE_BUCKETS), "连消10+次",
    "free_win_times", "free_win_rate", "ok", "错误", "status",
    "ProvisionalConfig", "Seed", "RequestedSpins", "ActualGeneral", "ActualFreeGeneral",
    "ReelConfigFile", "FreeReelConfigFile",
]

status_model = {
    "base": {"spin": 0, "ways": [0, 0], "free": 0},
    "free": {"spin": 0, "ways": [0, 0], "free": 0},
    "bet": 0,
    "wins": 0,
    "hit": 0,
    "free_times": 0,
    **{f"gt_{Threshold}x": 0 for Threshold in THRESHOLDS},
    "MainCascadeCounts": [0] * MAIN_CASCADE_BUCKET_COUNT,
    "ActualGeneral": "",
    "ActualFreeGeneral": "",
    "ReelConfigFile": "",
    "FreeReelConfigFile": "",
}

statics_columns = [
    {"title": "基础信息", "fields": [
        "INDEX", "GENERAL", "FREE_GENERAL", "SPIN", "总押注", "rtp", "rtp_check",
        "总赢钱", "Ways赢钱", "Hit", "Hit率",
        ">5x", ">10x", ">20x", ">50x", ">100x", ">1000x", "错误",
    ]},
    {"title": "Base", "fields": [
        "base_rtp", "base_ways_rtp", "BaseWays", "main_win_times", "main_win_rate",
        *(f"连消{Number}次" for Number in MAIN_CASCADE_BUCKETS), "连消10+次",
    ]},
    {"title": "Free", "fields": [
        "free_rtp", "free_ways_rtp", "FreeWays", "free_win_times", "free_win_rate",
        "触发Free", "Free频率", "Free次数", "FreeSpin", "Free重触发",
        "Free平均次数", "Free平均倍",
    ]},
]

status_handler = SlotsSimulation(
    status_model=status_model,
    thresholds=THRESHOLDS,
    feature_key="ways",
    feature_label="Ways",
    print_mode="statics",
    statics_columns=statics_columns,
)


def first_config_value(value):
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError("default config list cannot be empty")
        return value[0]
    return value


def list_config_values(value) -> list:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def discover_general_indexes(index: int) -> list[int]:
    Game = ThemeMath()
    Source = Game._find_reel_config_path(index).read_text(encoding="utf-8-sig")
    return sorted({int(Match.group(1)) for Match in GENERAL_SECTION_RE.finditer(Source)})


def record_win_info(status: dict, win_info: dict, mode_key: str) -> int:
    Win = int(win_info["TotalWin"])
    status_handler.update_feature_win(status, mode_key, "ways", Win)
    return Win


def main_cascade_bucket(cascade_count: int) -> int:
    if cascade_count < 0:
        raise ValueError("CascadeCount must be nonnegative")
    return min(cascade_count, len(MAIN_CASCADE_BUCKETS))


def record_main_cascade_count(status: dict, ng_result: dict) -> None:
    Bucket = main_cascade_bucket(int(ng_result.get("CascadeCount", 0)))
    status["MainCascadeCounts"][Bucket] += 1


def record_reel_source(status: dict, Game, FreeGame: bool) -> None:
    Info = getattr(Game, "last_spin_info", {})
    if Info:
        status["ActualFreeGeneral" if FreeGame else "ActualGeneral"] = Info.get("general_index", "")
        status["FreeReelConfigFile" if FreeGame else "ReelConfigFile"] = Info.get("reel_config_file", "")


def run_free_spins(
    Game, status: dict, index: int, free_general_index: int, free_times: int,
) -> int:
    """所有已发次数正常玩完；待玩次数传回生成逻辑，倍数继承上一手终倍加 1。"""
    if not 0 <= free_times <= Game.FreeMaxTimes:
        raise RuntimeError("initial free award exceeds the generated Scatter budget")
    Remaining = free_times
    FreeWin = 0
    FreeSpinNumber = 0
    FreeStartMultiplier = 1
    while Remaining:
        Remaining -= 1
        FreeSpinNumber += 1
        Result = Game.fg_spin(
            index=index,
            general_index=free_general_index,
            FreeSpinNumber=FreeSpinNumber,
            FreeStartMultiplier=FreeStartMultiplier,
            FreeSpinsRemaining=Remaining,
        )
        Extra = int(Result["ExtraFreeSpins"])
        if not 0 <= Extra <= Game.FreeMaxTimes - FreeSpinNumber - Remaining:
            raise RuntimeError("extra free award exceeds the generated Scatter budget")
        status_handler.add_status_value(status, 1, "free", "spin")
        FreeWin += record_win_info(status, Result, "free")
        status_handler.update_free_trigger(status, "free", Extra)
        record_reel_source(status, Game, True)
        Remaining += Extra
        FreeStartMultiplier = Result["FreeEndMultiplier"] + 1
    return FreeWin


def build_simulation_row(
    status: dict, index: int, general_index: int, free_general_index: int,
    seed: int | None = None, RequestedSpins: int | None = None,
) -> dict:
    # 连消计数不参与通用金额列表的 RTP 递归计算。
    MoneyStatus = {Key: Value for Key, Value in status.items() if Key != "MainCascadeCounts"}
    Row = status_handler.build_report_row(MoneyStatus)
    BaseSpins = status["base"]["spin"]
    FreeSpins = status["free"]["spin"]
    Triggers = status["base"]["free"]
    BaseBet = status["bet"] / BaseSpins if BaseSpins else 0
    Row.update({
        "INDEX": index,
        "GENERAL": general_index,
        "FREE_GENERAL": free_general_index,
        "总押注": status["bet"],
        "Free平均次数": status["free_times"] / Triggers if Triggers else 0,
        "Free平均倍": status["free"]["ways"][1] / Triggers / BaseBet if Triggers and BaseBet else 0,
        "main_win_times": status["base"]["ways"][0],
        "main_win_rate": status["base"]["ways"][0] / BaseSpins if BaseSpins else 0,
        "free_win_times": status["free"]["ways"][0],
        "free_win_rate": status["free"]["ways"][0] / FreeSpins if FreeSpins else 0,
        "ok": True,
        "错误": "",
        "ProvisionalConfig": True,
        "Seed": seed,
        "RequestedSpins": RequestedSpins if RequestedSpins is not None else BaseSpins,
    })
    for Number, Count in enumerate(status["MainCascadeCounts"]):
        Label = str(Number) if Number < len(MAIN_CASCADE_BUCKETS) else MAIN_CASCADE_OVERFLOW_LABEL
        Row[f"连消{Label}次"] = Count
    for Key in ("ActualGeneral", "ActualFreeGeneral", "ReelConfigFile", "FreeReelConfigFile"):
        Row[Key] = status[Key]
    return Row


def simulation(
    spin_times: int = SPIN_TIMES,
    index: int | None = None,
    general_index: int | None = None,
    free_general_index: int | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = False,
    base_bet: int = 10000,
    seed: int | None = None,
) -> list[dict]:
    """按付费手累计统计，检查点在该手的整轮免费游戏结束后输出。"""
    if spin_times <= 0:
        raise ValueError("spin_times must be positive")
    if base_bet <= 0:
        raise ValueError("base_bet must be positive")
    if report_interval < 0:
        raise ValueError("report_interval must be nonnegative")
    if seed is not None:
        random.seed(seed)
    index = first_config_value(INDEX) if index is None else index
    general_index = first_config_value(GENERAL_INDEX) if general_index is None else general_index
    FreeGeneral = general_index if free_general_index is None else free_general_index
    Game = ThemeMath(base_bet=base_bet)
    Status = status_handler.new_status()
    Rows = []
    for _ in range(spin_times):
        status_handler.update_spin_start(Status, base_bet)
        Main = Game.ng_spin(index=index, general_index=general_index)
        record_main_cascade_count(Status, Main)
        record_reel_source(Status, Game, False)
        Win = record_win_info(Status, Main, "base")
        FreeTimes = int(Main["FreeSpinsAwarded"])
        if not 0 <= FreeTimes <= Game.FreeMaxTimes:
            raise RuntimeError("initial free award exceeds the generated Scatter budget")
        status_handler.update_free_trigger(Status, "base", FreeTimes)
        if FreeTimes:
            Win += run_free_spins(Game, Status, index, FreeGeneral, FreeTimes)
        status_handler.update_spin_result(Status, Win, base_bet)
        if report_interval and Status["base"]["spin"] % report_interval == 0:
            Row = build_simulation_row(Status, index, general_index, FreeGeneral, seed, spin_times)
            Rows.append(Row)
            if print_updates:
                print_table([Row])
    if not Rows or Rows[-1]["SPIN"] != spin_times:
        Rows.append(build_simulation_row(Status, index, general_index, FreeGeneral, seed, spin_times))
    Rows[-1]["status"] = Status
    return Rows


def simulation_all(
    spin_times: int = SPIN_TIMES,
    indexes: list[int] | None = None,
    general_indexes: list[int] | None = None,
    free_general_indexes: list[int] | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = True,
    base_bet: int = 10000,
    seed: int | None = None,
) -> list[dict]:
    Results = []
    Indexes = list_config_values(INDEX) if indexes is None else list_config_values(indexes)
    Generals = list_config_values(GENERAL_INDEX) if general_indexes is None else list_config_values(general_indexes)
    FreeGenerals = [None] if free_general_indexes is None else list_config_values(free_general_indexes)
    if not Indexes or not Generals or not FreeGenerals:
        raise ValueError("index and GENERAL lists cannot be empty")
    for Index in Indexes:
        for General in Generals:
            for FreeGeneral in FreeGenerals:
                try:
                    Rows = simulation(
                        spin_times=spin_times, index=Index, general_index=General,
                        free_general_index=FreeGeneral, report_interval=report_interval,
                        print_updates=print_updates, base_bet=base_bet, seed=seed,
                    )
                    Results.append(Rows[-1])
                except Exception as Exc:
                    Results.append({
                        "INDEX": Index, "GENERAL": General,
                        "FREE_GENERAL": General if FreeGeneral is None else FreeGeneral,
                        "SPIN": 0, "RequestedSpins": spin_times,
                        "ok": False, "错误": str(Exc), "Seed": seed, "ProvisionalConfig": True,
                    })
    return Results


def simulate(
    spins: int, base_bet: int = 10000, index: int = 0,
    general_index: int = 1, seed: int | None = None,
) -> dict:
    """保留原汇总接口，数据由同一仿真流程生成。"""
    Row = simulation(spins, index, general_index, report_interval=0, base_bet=base_bet, seed=seed)[-1]
    return {
        "ProvisionalConfig": True, "PaidSpins": Row["SPIN"], "FreeSpins": Row["FreeSpin"],
        "MainHits": Row["main_win_times"], "FreeTriggers": Row["触发Free"],
        "TotalBet": Row["总押注"], "MainWin": Row["BaseWays"], "FreeWin": Row["FreeWays"],
        "TotalWin": Row["总赢钱"], "Rtp": Row["rtp"], "MainHitRate": Row["main_win_rate"],
        "FreeTriggerRate": Row["Free频率"], "AverageFreeSpinsPerTrigger": Row["Free平均次数"],
        "Seed": seed,
    }


def print_table(results: list[dict]) -> None:
    status_handler.print_table(results)


def print_summary(result: dict | list[dict]) -> None:
    if isinstance(result, list):
        result = result[-1] if result else {}
    if result:
        print_table([result])


def format_csv_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value


def get_result_csv_fields(rows: list[dict], path: Path) -> list[str]:
    Extra = sorted({Key for Row in rows for Key in Row if Key not in RESULT_CSV_FIELDS})
    Fields = RESULT_CSV_FIELDS + Extra
    if path.exists() and path.stat().st_size:
        with path.open("r", newline="", encoding="utf-8-sig") as File:
            Header = next((Row for Row in csv.reader(File) if Row), [])
        if Header:
            return Header + [Key for Key in Fields if Key not in Header]
    return Fields


def update_result_csv_header(path: Path, fieldnames: list[str]) -> None:
    if not path.exists() or not path.stat().st_size:
        return
    with path.open("r", newline="", encoding="utf-8-sig") as File:
        Reader = csv.DictReader(File)
        if Reader.fieldnames == fieldnames:
            return
        Rows = list(Reader)
    with path.open("w", newline="", encoding="utf-8-sig") as File:
        Writer = csv.DictWriter(File, fieldnames=fieldnames)
        Writer.writeheader()
        for Row in Rows:
            Writer.writerow({Key: Row.get(Key, "") for Key in fieldnames})


def append_simulation_results(rows: list[dict], path: Path = RESULT_CSV) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Fields = get_result_csv_fields(rows, path)
    WriteHeader = not path.exists() or not path.stat().st_size
    if not WriteHeader:
        update_result_csv_header(path, Fields)
    with path.open("a", newline="", encoding="utf-8-sig" if WriteHeader else "utf-8") as File:
        Writer = csv.DictWriter(File, fieldnames=Fields)
        if WriteHeader:
            Writer.writeheader()
        for Row in rows:
            Writer.writerow({Key: format_csv_value(Row.get(Key, "")) for Key in Fields})


def parse_int_list(value: str | None) -> list[int] | None:
    if value is None:
        return None
    return [int(Item.strip()) for Item in value.split(",") if Item.strip()]


def parse_args(argv=None) -> argparse.Namespace:
    Parser = argparse.ArgumentParser(description="恐龙世界 Ways 仿真")
    Parser.add_argument("--spins", type=int, default=SPIN_TIMES)
    Parser.add_argument("--base-bet", type=int, default=10000)
    IndexGroup = Parser.add_mutually_exclusive_group()
    IndexGroup.add_argument("--index", type=int)
    IndexGroup.add_argument("--indexes", type=parse_int_list)
    GeneralGroup = Parser.add_mutually_exclusive_group()
    GeneralGroup.add_argument("--general-index", "--general", type=int)
    GeneralGroup.add_argument("--generals", type=parse_int_list)
    Parser.add_argument("--free-generals", type=parse_int_list)
    Parser.add_argument("--seed", type=int)
    Parser.add_argument("--report-interval", type=int, default=REPORT_INTERVAL)
    Parser.add_argument("--no-print-updates", action="store_false", dest="print_updates")
    Parser.set_defaults(print_updates=True)
    Parser.add_argument("--output", type=Path, default=RESULT_CSV)
    Args = Parser.parse_args(argv)
    if Args.spins <= 0 or Args.base_bet <= 0:
        Parser.error("--spins and --base-bet must be positive")
    if Args.report_interval < 0:
        Parser.error("--report-interval must be nonnegative")
    if any(Value == [] for Value in (Args.indexes, Args.generals, Args.free_generals)):
        Parser.error("INDEX and GENERAL lists cannot be empty")
    return Args


def main(argv=None) -> None:
    Args = parse_args(argv)
    Results = simulation_all(
        spin_times=Args.spins,
        indexes=[Args.index] if Args.index is not None else Args.indexes,
        general_indexes=[Args.general_index] if Args.general_index is not None else Args.generals,
        free_general_indexes=Args.free_generals,
        report_interval=Args.report_interval,
        print_updates=Args.print_updates,
        base_bet=Args.base_bet,
        seed=Args.seed,
    )
    print_table(Results)
    append_simulation_results(Results, Args.output)
    if any(not Row["ok"] for Row in Results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
