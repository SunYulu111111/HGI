"""超级英雄的模板仿真入口：逐手统计，付费检查点包含完整免费游戏。"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re
import sys
from typing import Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from slots_simulation import simulation as SlotsSimulation

try:
    from .theme_math import ThemeMath
except ImportError:
    from theme_math import ThemeMath


SPIN_TIMES = 1000000
INDEX = 0
GENERAL_INDEX = 1
REPORT_INTERVAL = 5000
THRESHOLDS = (5, 10, 20, 50, 100, 1000)
GENERAL_SECTION_RE = re.compile(r"^\s*\[GENERAL_(\d+)\]\s*$", re.MULTILINE)
DefaultResultCsv = Path(__file__).with_name("simulate_result.csv")
WinThresholds = THRESHOLDS

# base/free 与 gt_* 沿用 Lines 模板，免费包含普通免费和超级免费。
status_model = {
    "base": {"spin": 0, "lines": [0, 0], "free": 0},
    "free": {"spin": 0, "lines": [0, 0], "free": 0},
    "bet": 0, "wins": 0, "hit": 0, "free_times": 0,
    **{f"gt_{Threshold}x": 0 for Threshold in THRESHOLDS},
    "MainWin": 0, "FreeWin": 0, "SuperFreeWin": 0,
    "NormalFreeSpins": 0, "SuperFreeSpins": 0,
    "FreeTriggers": 0, "SuperFreeTriggers": 0, "Retriggers": 0, "Upgrades": 0,
    "UltimateHits": 0, "UltimateWin": 0, "TotalSpins": 0, "FreeSpinsAwarded": 0,
    "ActualIndex": None, "ActualGeneral": None, "ReelConfigFile": "",
    "ActualFreeIndex": None, "ActualFreeGeneral": None, "FreeReelConfigFile": "",
    "ActualSuperFreeIndex": None, "ActualSuperFreeGeneral": None, "SuperFreeReelConfigFile": "",
    "IndexFallback": False, "GeneralFallback": False,
    "FreeIndexFallback": False, "FreeGeneralFallback": False,
    "SuperFreeIndexFallback": False, "SuperFreeGeneralFallback": False,
}
MetadataFields = (
    "ActualIndex", "ActualGeneral", "ReelConfigFile", "ActualFreeIndex", "ActualFreeGeneral",
    "FreeReelConfigFile", "ActualSuperFreeIndex", "ActualSuperFreeGeneral", "SuperFreeReelConfigFile",
    "IndexFallback", "GeneralFallback", "FreeIndexFallback", "FreeGeneralFallback",
    "SuperFreeIndexFallback", "SuperFreeGeneralFallback",
)
SummaryFields = (
    "Seed", "ConfigPurpose", "ControlMode", "BaseBet", "PaidSpins", "TotalSpins", "Bet",
    "MainWin", "FreeWin", "SuperFreeWin", "TotalWin", "Rtp", "MainRtp", "FreeRtp",
    "SuperFreeRtp", "Hits", "HitRate", "FreeTriggers", "SuperFreeTriggers", "Retriggers", "Upgrades",
    "FreeSpins", "NormalFreeSpins", "SuperFreeSpins", "FreeSpinsAwarded", "UltimateHits",
    "UltimateWin", "UltimateRtp", "UltimateFrequency",
    *(f"WinAbove{Threshold}Count" for Threshold in THRESHOLDS),
)
CsvFields = ("INDEX", "GENERAL", "FREE_GENERAL", *SlotsSimulation.DEFAULT_HEADERS, "总押注", *SummaryFields, *MetadataFields)

status_handler = SlotsSimulation(
    status_model=status_model,
    thresholds=THRESHOLDS,
    print_mode="statics",
    statics_columns=[
        {"title": "基础信息", "fields": [
            "INDEX", "GENERAL", "FREE_GENERAL", "SPIN", "总押注", "rtp", "rtp_check",
            "总赢钱", "Line赢钱", "Hit", "Hit率", *(f">{Threshold}x" for Threshold in THRESHOLDS),
        ]},
        {"title": "主游戏", "fields": ["base_rtp", "BaseLine", "触发Free", "Free频率", "ActualIndex", "ActualGeneral", "ReelConfigFile"]},
        {"title": "普通免费", "fields": [
            ("普通免费赢分", "FreeWin"), ("普通免费RTP", "FreeRtp"), ("普通免费手数", "NormalFreeSpins"),
            ("普通免费直入", "FreeTriggers"), ("升级次数", "Upgrades"), "ActualFreeGeneral", "FreeReelConfigFile",
        ]},
        {"title": "超级免费", "fields": [
            ("超级免费赢分", "SuperFreeWin"), ("超级免费RTP", "SuperFreeRtp"), ("超级免费手数", "SuperFreeSpins"),
            ("超级免费直入", "SuperFreeTriggers"), "ActualSuperFreeGeneral", "SuperFreeReelConfigFile",
        ]},
        {"title": "免费与终极大奖", "fields": [
            "free_rtp", "FreeLine", "Free次数", "FreeSpin", "Free重触发",
            ("终极大奖命中", "UltimateHits"), ("终极大奖赢分", "UltimateWin"),
            ("终极大奖RTP", "UltimateRtp"), ("终极大奖平均间隔", "UltimateFrequency"),
        ]},
    ],
)


def _nonnegative_integer(Value, Name, AllowZero=True):
    if type(Value) is not int or Value < (0 if AllowZero else 1):
        raise ValueError(f"{Name} 必须为{'非负' if AllowZero else '正'}整数")
    return Value


def discover_general_indexes(index: int = INDEX, free_game: bool = False, SuperFree: bool = False) -> list[int]:
    """读取相应主／免费轴带中的 GENERAL 段，不混用两种免费轴。"""
    m = ThemeMath()
    if SuperFree:
        ReelDir, Template = m.SuperFreeReelConfigDir, m.SuperFreeReelFileTemplate
    elif free_game:
        ReelDir, Template = m.FREE_REEL_CONFIG_DIR, m.FreeReelFileTemplate
    else:
        ReelDir, Template = None, m.MainReelFileTemplate
    path = m._find_reel_config_path(index, reel_config_dir=ReelDir, reel_file_template=Template)
    text = path.read_text(encoding="utf-8-sig")
    return sorted({int(Match.group(1)) for Match in GENERAL_SECTION_RE.finditer(text)})


def get_line_win(win_info: dict) -> int:
    """读取模板金额；cjyx 的中奖均来自连线。"""
    if "line_win" in win_info:
        return _nonnegative_integer(win_info["line_win"], "line_win")
    return sum(_nonnegative_integer(Item.get("win", 0), "win") for Item in win_info.get("win_items", []))


def get_free_times(m: ThemeMath, win_info: dict) -> int:
    """本手完整授予次数由主题决定，升级只读取实际补发量。"""
    return _nonnegative_integer(win_info.get("AwardedFreeSpins", 0), "AwardedFreeSpins")


def _record_reel_source(status: dict, win_info: dict) -> None:
    Info = win_info.get("spin_info", {})
    Prefix = {"Main": "", "Free": "Free", "SuperFree": "SuperFree"}[win_info["Mode"]]
    FileName = Info.get("reel_config_file", "")
    Match = re.search(r"_ex_(\d+)\.conf$", FileName)
    ActualIndex = int(Match.group(1)) if Match else Info.get("index")
    for Field, Value in (
        ("Actual" + Prefix + "Index", ActualIndex),
        ("Actual" + Prefix + "General", Info.get("general_index")),
        (Prefix + "ReelConfigFile", FileName),
    ):
        if Value is not None and Value != "":
            status[Field] = Value
    for Field, Source in (("IndexFallback", "reel_config_index_fallback"), ("GeneralFallback", "general_index_fallback")):
        status[Prefix + Field] |= bool(Info.get(Source, False))


def record_win_info(status: dict, win_info: dict, mode_key: str) -> int:
    """每手实际进入通用连线统计，再补充普通／超级免费及终极大奖统计。"""
    total_win = _nonnegative_integer(win_info.get("total_win", 0), "total_win")
    line_win = get_line_win(win_info)
    if line_win != total_win:
        raise ValueError("cjyx 连线金额与本手总赢分不一致")
    Mode = win_info["Mode"]
    if Mode not in ("Main", "Free", "SuperFree") or (Mode == "Main") != (mode_key == "base"):
        raise ValueError("旋转模式与统计分组不一致")
    status_handler.update_feature_win(status, mode_key, "lines", line_win)
    status["TotalSpins"] += 1
    status[{"Main": "MainWin", "Free": "FreeWin", "SuperFree": "SuperFreeWin"}[Mode]] += total_win
    if Mode != "Main":
        status["SuperFreeSpins" if Mode == "SuperFree" else "NormalFreeSpins"] += 1
        status["Upgrades"] += int(bool(win_info.get("Upgraded", False)))
    else:
        status["FreeTriggers"] += int(win_info.get("NextMode") == "Free")
        status["SuperFreeTriggers"] += int(win_info.get("NextMode") == "SuperFree")
    if win_info.get("UltimateHit", False):
        status["UltimateHits"] += 1
        status["UltimateWin"] += total_win
    _record_reel_source(status, win_info)
    return total_win


def run_free_spins(m: ThemeMath, status: dict, index: int, free_general_index: int, free_times: int) -> int:
    """由主题会话控制全部免费手数，追加和升级不自行截短。"""
    if m.FreeSpinsRemaining != free_times:
        raise ValueError("初始免费授予次数与主题会话不一致")
    free_total_win = 0
    Executed = 0
    Awarded = free_times
    while m.FreeSpinsRemaining > 0:
        status_handler.add_status_value(status, 1, "free", "spin")
        fg_info = m.fg_spin(index, free_general_index, return_detail=True)
        free_total_win += record_win_info(status, fg_info, "free")
        Extra = get_free_times(m, fg_info)
        Awarded += Extra
        status["FreeSpinsAwarded"] += Extra
        if fg_info.get("ScatterCount") == 3:
            status_handler.update_free_trigger(status, "free", Extra)
            status["Retriggers"] += 1
        elif Extra:
            status_handler.add_status_value(status, Extra, "free_times")
        Executed += 1
    if Executed != Awarded:
        raise ValueError("免费授予次数与本轮实际执行次数不一致")
    return free_total_win


def build_simulation_row(status: dict, index: int, general_index: int, free_general_index: int, BaseBet: int, Seed: int | None) -> dict:
    Row = status_handler.build_report_row(status)
    Bet = status["bet"]
    Row.update({
        "INDEX": index, "GENERAL": general_index, "FREE_GENERAL": free_general_index,
        "总押注": Bet, "Seed": Seed, "ConfigPurpose": "FlowValidation", "ControlMode": "Uncontrolled",
        "BaseBet": BaseBet, "PaidSpins": Row["SPIN"], "TotalSpins": status["TotalSpins"], "Bet": Bet,
        "MainWin": status["MainWin"], "FreeWin": status["FreeWin"], "SuperFreeWin": status["SuperFreeWin"],
        "TotalWin": status["wins"], "Rtp": Row["rtp"], "MainRtp": status["MainWin"] / Bet if Bet else 0,
        "FreeRtp": status["FreeWin"] / Bet if Bet else 0, "SuperFreeRtp": status["SuperFreeWin"] / Bet if Bet else 0,
        "Hits": status["hit"], "HitRate": Row["Hit率"], "FreeSpins": Row["FreeSpin"],
        "UltimateRtp": status["UltimateWin"] / Bet if Bet else 0,
        "UltimateFrequency": status["TotalSpins"] / status["UltimateHits"] if status["UltimateHits"] else None,
    })
    for Field in ("NormalFreeSpins", "SuperFreeSpins", "FreeTriggers", "SuperFreeTriggers", "Retriggers", "Upgrades", "FreeSpinsAwarded", "UltimateHits", "UltimateWin", *MetadataFields):
        Row[Field] = status[Field]
    for Threshold in THRESHOLDS:
        Row[f"WinAbove{Threshold}Count"] = status[f"gt_{Threshold}x"]
    return Row


def simulation(
    spin_times: int = SPIN_TIMES,
    index: int = INDEX,
    general_index: int = GENERAL_INDEX,
    free_general_index: int | None = None,
    report_interval: int = REPORT_INTERVAL,
    BaseBet: int = 100000,
    Seed: int | None = None,
    PrintUpdates: bool = False,
) -> list[dict]:
    """返回累计检查点；每个检查点均已完成该付费手触发的整轮免费游戏。"""
    for Value, Name in ((spin_times, "spin_times"), (index, "index"), (general_index, "general_index"), (report_interval, "report_interval")):
        _nonnegative_integer(Value, Name)
    _nonnegative_integer(BaseBet, "BaseBet", AllowZero=False)
    if Seed is not None and type(Seed) is not int:
        raise ValueError("Seed 必须为整数或 None")
    if type(PrintUpdates) is not bool:
        raise ValueError("PrintUpdates 必须为布尔值")
    free_general_index = general_index if free_general_index is None else free_general_index
    _nonnegative_integer(free_general_index, "free_general_index")
    m = ThemeMath(base_bet=BaseBet, Seed=Seed)
    status = status_handler.new_status()
    rows = []
    for _ in range(spin_times):
        status_handler.update_spin_start(status, m.base_bet)
        win_info = m.ng_spin(index, general_index, return_detail=True)
        spin_total_win = record_win_info(status, win_info, "base")
        free_times = get_free_times(m, win_info)
        status_handler.update_free_trigger(status, "base", free_times)
        status["FreeSpinsAwarded"] += free_times
        if free_times:
            spin_total_win += run_free_spins(m, status, index, free_general_index, free_times)
        status_handler.update_spin_result(status, spin_total_win, m.base_bet)
        if report_interval and status["base"]["spin"] % report_interval == 0:
            Row = build_simulation_row(status, index, general_index, free_general_index, BaseBet, Seed)
            rows.append(Row)
            if PrintUpdates and status["base"]["spin"] < spin_times:
                status_handler.print_table([Row])
    if not rows or rows[-1]["SPIN"] != status["base"]["spin"]:
        rows.append(build_simulation_row(status, index, general_index, free_general_index, BaseBet, Seed))
    return rows


def simulate(
    Spins: int = SPIN_TIMES, BaseBet: int = 100000, Seed: int | None = None,
    ReportInterval: int = 0, PrintUpdates: bool = False,
    Index: int = INDEX, GeneralIndex: int = GENERAL_INDEX, FreeGeneralIndex: int | None = None,
) -> dict:
    """兼容汇总入口，直接使用模板仿真的最后一个检查点。"""
    return simulation(Spins, Index, GeneralIndex, FreeGeneralIndex, ReportInterval, BaseBet, Seed, PrintUpdates)[-1]


def format_summary(Summary: dict) -> str:
    """保留简短文本接口；命令行表格通过共享 status_handler 输出。"""
    Frequency = Summary["UltimateFrequency"]
    FrequencyText = "尚未命中" if Frequency is None else f"每 {Frequency:,.2f} 次实际旋转一次"
    return (
        f"主游戏赢分 {Summary['MainWin']:,}；普通免费赢分 {Summary['FreeWin']:,}；超级免费赢分 {Summary['SuperFreeWin']:,}\n"
        f"总赢分 {Summary['TotalWin']:,}；RTP {Summary['Rtp']:.6f}；终极大奖频率 {FrequencyText}。\n"
        "当前轴带用于流程验证，不表示 RTP 目标已达标。"
    )


def _validate_output(Output: str | Path) -> tuple[Path, bool]:
    OutputPath = Path(Output)
    HasHeader = OutputPath.exists() and OutputPath.stat().st_size > 0
    if HasHeader:
        with OutputPath.open("r", newline="", encoding="utf-8-sig") as Handle:
            Header = next(csv.reader(Handle), [])
        if Header != list(CsvFields):
            raise ValueError(f"CSV 表头不兼容，未追加：{OutputPath}")
    if OutputPath.parent.exists() and not OutputPath.parent.is_dir():
        raise NotADirectoryError(f"CSV 上级路径不是文件夹：{OutputPath.parent}")
    return OutputPath, HasHeader


def append_summary(Summary: dict, Output: str | Path = DefaultResultCsv) -> Path:
    """每次仅追加一行最终汇总，兼容模板通用字段及特色字段。"""
    Missing = set(CsvFields) - set(Summary)
    if Missing:
        raise ValueError(f"汇总缺少 CSV 字段：{sorted(Missing)}")
    OutputPath, HasHeader = _validate_output(Output)
    OutputPath.parent.mkdir(parents=True, exist_ok=True)
    with OutputPath.open("a", newline="", encoding="utf-8") as Handle:
        Writer = csv.DictWriter(Handle, fieldnames=CsvFields, extrasaction="ignore")
        if not HasHeader:
            Writer.writeheader()
        Writer.writerow(Summary)
    return OutputPath


def _parse_choices(Value: str) -> list[int]:
    try:
        Items = Value.split(",")
        if any(not Item.strip() for Item in Items):
            raise ValueError
        return [int(Item.strip()) for Item in Items]
    except ValueError as Error:
        raise argparse.ArgumentTypeError("配置列表须为逗号分隔的整数，例如 0,1") from Error


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="超级英雄 Lines 模板仿真，当前轴带用于流程验证。")
    parser.add_argument("--spins", type=int, default=SPIN_TIMES)
    IndexGroup = parser.add_mutually_exclusive_group()
    IndexGroup.add_argument("--index", type=int, default=INDEX)
    IndexGroup.add_argument("--indexes", dest="Indexes", type=_parse_choices)
    GeneralGroup = parser.add_mutually_exclusive_group()
    GeneralGroup.add_argument("--general", "--general-index", dest="general", type=int, default=GENERAL_INDEX)
    GeneralGroup.add_argument("--generals", dest="Generals", type=_parse_choices)
    FreeGeneralGroup = parser.add_mutually_exclusive_group()
    FreeGeneralGroup.add_argument("--free-general", "--free-general-index", dest="free_general", type=int, default=None)
    FreeGeneralGroup.add_argument("--free-generals", dest="FreeGenerals", type=_parse_choices)
    parser.add_argument("--report-interval", type=int, default=REPORT_INTERVAL)
    parser.add_argument("--base-bet", dest="BaseBet", type=int, default=100000)
    parser.add_argument("--seed", dest="Seed", type=int, default=None)
    parser.add_argument("--no-print-updates", dest="PrintUpdates", action="store_false")
    parser.add_argument("--output", dest="Output", type=Path, default=DefaultResultCsv)
    return parser


def parse_args(Args: Sequence[str] | None = None) -> argparse.Namespace:
    return _argument_parser().parse_args(Args)


def main(Args: Sequence[str] | None = None) -> int:
    Parser = _argument_parser()
    Options = Parser.parse_args(Args)
    FinalRows = []
    try:
        Indexes = Options.Indexes if Options.Indexes is not None else [Options.index]
        Generals = Options.Generals if Options.Generals is not None else [Options.general]
        FreeGenerals = Options.FreeGenerals if Options.FreeGenerals is not None else [Options.free_general]
        for Value, Name in ((Options.spins, "spins"), (Options.report_interval, "report_interval")):
            _nonnegative_integer(Value, Name)
        _nonnegative_integer(Options.BaseBet, "BaseBet", AllowZero=False)
        for Values, Name in ((Indexes, "index"), (Generals, "general"), (FreeGenerals, "free_general")):
            for Value in Values:
                if Value is not None:
                    _nonnegative_integer(Value, Name)
        _validate_output(Options.Output)
        for Index in Indexes:
            for General in Generals:
                for FreeGeneral in FreeGenerals:
                    Rows = simulation(
                        Options.spins, Index, General, FreeGeneral, Options.report_interval,
                        BaseBet=Options.BaseBet, Seed=Options.Seed, PrintUpdates=Options.PrintUpdates,
                    )
                    append_summary(Rows[-1], Options.Output)
                    FinalRows.append(Rows[-1])
        status_handler.print_table(FinalRows)
    except (ValueError, OSError) as Error:
        if FinalRows:
            status_handler.print_table(FinalRows)
        Parser.error(str(Error))
    print(f"最终汇总已追加：{Options.Output}")
    print("当前轴带用于流程验证，不表示 RTP 目标已达标。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
